"""ForgeClip's external ffmpeg worker. Python stdlib + ffmpeg; no provider SDKs."""
import concurrent.futures
import hashlib
import hmac
import http.server
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

MAX_INPUT = int(os.getenv('MAX_INPUT_BYTES', str(2 * 1024**3)))
MAX_AUDIO = 24 * 1024**2
MAX_DURATION = int(os.getenv('MAX_DURATION_SECONDS', '1800'))
DATA = Path(os.getenv('DATA_DIR', '/data'))
STOP = threading.Event()

class InvalidRequest(ValueError):
    pass

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise InvalidRequest('Redirects are not accepted for signed media URLs.')

def exact_https_url(value, host, prefix=None):
    parsed = urllib.parse.urlsplit(value)
    try:
        valid_port = parsed.port in (None, 443)
    except ValueError:
        valid_port = False
    if parsed.scheme != 'https' or parsed.hostname != host or parsed.username or parsed.password or parsed.fragment or not valid_port:
        raise InvalidRequest('URL does not match the configured HTTPS destination.')
    if prefix and not parsed.path.startswith(prefix):
        raise InvalidRequest('Unexpected storage destination path.')
    return parsed

def validate(payload):
    host = os.environ.get('SUPABASE_STORAGE_HOST', '')
    origin = os.environ.get('FORGECLIP_APP_ORIGIN', '').rstrip('/')
    secret = os.environ.get('EXTRACTOR_WEBHOOK_SECRET', '')
    if not host or not origin or len(secret) < 32:
        raise InvalidRequest('Extractor deployment configuration is incomplete.')
    if not isinstance(payload, dict):
        raise InvalidRequest('Expected an object.')
    for key in ('jobId', 'assetId'):
        try:
            uuid.UUID(payload[key])
        except (KeyError, ValueError, TypeError, AttributeError):
            raise InvalidRequest('Invalid asset or job identifier.') from None
    callback_secret = payload.get('callbackSecret')
    if not isinstance(callback_secret, str) or not hmac.compare_digest(callback_secret, secret):
        raise InvalidRequest('Callback authentication does not match.')
    exact_https_url(payload.get('inputUrl', ''), host, '/storage/v1/object/sign/uploads/')
    target = exact_https_url(payload.get('outputUrl', ''), host, '/storage/v1/object/upload/sign/audio-extracts/')
    callback = origin + '/api/public/jobs/extractor-callback'
    if payload.get('callbackUrl') != callback:
        raise InvalidRequest('Callback destination does not match the configured app.')
    fmt = payload.get('format')
    if fmt not in ('mp3', 'm4a', 'webm'):
        raise InvalidRequest('Unsupported audio format.')
    bitrate = payload.get('bitrateKbps')
    if not isinstance(bitrate, int) or isinstance(bitrate, bool) or not 32 <= bitrate <= 128:
        raise InvalidRequest('Bitrate must be between 32 and 128 kbps.')
    audio_path = urllib.parse.unquote(target.path.split('/audio-extracts/', 1)[1])
    parts = audio_path.split('/')
    if len(parts) != 2 or any(p in ('', '.', '..') for p in parts) or parts[1] != payload['assetId'] + '.' + fmt:
        raise InvalidRequest('Output path does not match the supplied asset.')
    try:
        uuid.UUID(parts[0])
    except ValueError:
        raise InvalidRequest('Invalid storage owner path.') from None
    result = {key: payload[key] for key in ('jobId', 'assetId', 'inputUrl', 'outputUrl', 'format', 'bitrateKbps')}
    result['callbackUrl'] = callback
    result['audioPath'] = audio_path
    # The shared secret is supplied from the environment, never persisted in job JSON.
    return result

def connection():
    DATA.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DATA / 'queue.sqlite3', timeout=30)
    db.row_factory = sqlite3.Row
    return db

def initialize():
    with connection() as db:
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, status TEXT NOT NULL, payload TEXT NOT NULL, result TEXT, attempts INTEGER NOT NULL DEFAULT 0, updated REAL NOT NULL)')
        db.execute("UPDATE jobs SET status='queued' WHERE status='running'")

def enqueue(payload):
    with connection() as db:
        count = db.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','running','callback')").fetchone()[0]
        existing = db.execute('SELECT status FROM jobs WHERE id=?', (payload['jobId'],)).fetchone()
        if existing:
            return existing['status']
        if count >= 100:
            raise InvalidRequest('The extraction queue is full. Retry later.')
        db.execute('INSERT INTO jobs (id,status,payload,updated) VALUES (?,?,?,?)', (payload['jobId'], 'queued', json.dumps(payload), time.time()))
    return 'queued'

def extract(source, output, fmt, bitrate):
    result = subprocess.run(['ffprobe', '-v', 'error', '-protocol_whitelist', 'file,pipe', '-format_whitelist', 'mov,matroska,webm', '-show_entries', 'format=duration:stream=codec_type', '-of', 'json', str(source)], capture_output=True, text=True, timeout=60, check=True)
    info = json.loads(result.stdout)
    duration = float(info.get('format', {}).get('duration', 0))
    if not 0 < duration <= MAX_DURATION:
        raise InvalidRequest('This worker supports recordings up to its configured duration limit.')
    if not any(s.get('codec_type') == 'audio' for s in info.get('streams', [])):
        raise InvalidRequest('The source video has no audio stream.')
    codec = {'mp3': 'libmp3lame', 'm4a': 'aac', 'webm': 'libopus'}[fmt]
    subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-protocol_whitelist', 'file,pipe', '-format_whitelist', 'mov,matroska,webm', '-i', str(source), '-map', '0:a:0', '-vn', '-ac', '1', '-ar', '16000', '-c:a', codec, '-b:a', str(bitrate)+'k', '-threads', '1', '-y', str(output)], capture_output=True, timeout=min(1800, max(120, int(duration * 2))), check=True)
    size = output.stat().st_size
    if not 0 < size <= MAX_AUDIO:
        raise InvalidRequest('Extracted audio exceeds the supported single-file transcription limit.')
    return duration, size

def process(row):
    payload = json.loads(row['payload'])
    opener = urllib.request.build_opener(NoRedirect())
    try:
        with tempfile.TemporaryDirectory(prefix='forgeclip-') as directory:
            source = Path(directory) / 'source.bin'
            output = Path(directory) / ('audio.' + payload['format'])
            request = urllib.request.Request(payload['inputUrl'], headers={'User-Agent': 'ForgeClip-Extractor/1.0'})
            with opener.open(request, timeout=120) as response, source.open('wb') as file:
                size = 0
                while chunk := response.read(1024 * 1024):
                    size += len(chunk)
                    if size > MAX_INPUT:
                        raise InvalidRequest('Source exceeds the worker input limit.')
                    file.write(chunk)
            duration, size = extract(source, output, payload['format'], payload['bitrateKbps'])
            content_type = {'mp3': 'audio/mpeg', 'm4a': 'audio/mp4', 'webm': 'audio/webm'}[payload['format']]
            upload = urllib.request.Request(payload['outputUrl'], data=output.read_bytes(), method='PUT', headers={'Content-Type': content_type, 'x-upsert': 'true'})
            with opener.open(upload, timeout=120) as response:
                if not 200 <= response.status < 300:
                    raise InvalidRequest('Audio upload was not accepted.')
            result = {'jobId': payload['jobId'], 'ok': True, 'audioPath': payload['audioPath'], 'audioFormat': payload['format'], 'durationSeconds': duration, 'sizeBytes': size}
    except Exception as error:
        # Provider errors may contain signed URLs; they never enter logs or callbacks.
        message = str(error) if isinstance(error, InvalidRequest) else 'Media extraction or storage transfer failed.'
        result = {'jobId': payload['jobId'], 'ok': False, 'error': message, 'errorKind': 'extractor_rejected'}
    with connection() as db:
        # Clear expiring signed media URLs after processing; keep only callback data.
        callback = json.dumps({'callbackUrl': payload['callbackUrl']})
        db.execute("UPDATE jobs SET status='callback',payload=?,result=?,updated=? WHERE id=?", (callback, json.dumps(result), time.time(), row['id']))

def callback(row):
    payload = json.loads(row['payload'])
    request = urllib.request.Request(payload['callbackUrl'], data=row['result'].encode(), method='POST', headers={'Content-Type': 'application/json', 'x-extractor-secret': os.environ['EXTRACTOR_WEBHOOK_SECRET']})
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=60) as response:
            if not 200 <= response.status < 300:
                return False
    except Exception:
        return False
    with connection() as db:
        db.execute("UPDATE jobs SET status='delivered',payload='{}',result=NULL,updated=? WHERE id=?", (time.time(), row['id']))
    return True

def work_once():
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY updated LIMIT 1").fetchone()
        if row:
            db.execute("UPDATE jobs SET status='running',updated=? WHERE id=?", (time.time(), row['id']))
    if row:
        process(row)
        return True
    with connection() as db:
        row = db.execute("SELECT * FROM jobs WHERE status='callback' AND updated < ? ORDER BY updated LIMIT 1", (time.time() - 10,)).fetchone()
        if row:
            db.execute('UPDATE jobs SET updated=?,attempts=attempts+1 WHERE id=?', (time.time(), row['id']))
    if row:
        callback(row)
        return True
    return False

def worker():
    while not STOP.is_set():
        try:
            if not work_once():
                STOP.wait(1)
        except Exception:
            # Keep the dispatcher alive; durable jobs are recoverable on restart.
            STOP.wait(3)

class Handler(http.server.BaseHTTPRequestHandler):
    server_version = 'ForgeClipExtractor/1'
    def log_message(self, *_):
        pass
    def respond(self, code, value):
        data = json.dumps(value).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)
    def do_GET(self):
        if self.path != '/health':
            return self.respond(404, {'error': 'not_found'})
        return self.respond(200, {'ok': True})
    def do_POST(self):
        secret = os.environ.get('EXTRACTOR_WEBHOOK_SECRET', '')
        if len(secret) < 32:
            return self.respond(503, {'error': 'worker_not_configured'})
        received = self.headers.get('x-extractor-secret', '')
        if not hmac.compare_digest(received, secret):
            return self.respond(401, {'error': 'unauthorized'})
        if self.path not in ('/', '/extract'):
            return self.respond(404, {'error': 'not_found'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 16384:
                raise InvalidRequest('Invalid request length.')
            if self.headers.get_content_type() != 'application/json':
                raise InvalidRequest('Expected application/json.')
            payload = validate(json.loads(self.rfile.read(length)))
            status = enqueue(payload)
        except (InvalidRequest, ValueError, KeyError, TypeError):
            return self.respond(400, {'error': 'invalid_dispatch_request'})
        self.respond(202, {'ok': True, 'jobId': payload['jobId'], 'status': status})

if __name__ == '__main__':
    for key in ('SUPABASE_STORAGE_HOST', 'FORGECLIP_APP_ORIGIN', 'EXTRACTOR_WEBHOOK_SECRET'):
        if not os.environ.get(key):
            raise SystemExit('Missing required worker deployment configuration: '+key)
    initialize()
    threading.Thread(target=worker, daemon=True).start()
    server = http.server.ThreadingHTTPServer(('0.0.0.0', int(os.getenv('PORT', '8080'))), Handler)
    server.serve_forever()
