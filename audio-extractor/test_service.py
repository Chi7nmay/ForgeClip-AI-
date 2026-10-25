import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import uuid
import service

class ExtractorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.previous_data = service.DATA
        service.DATA = Path(self.temp.name)
        self.secret = 'test-only-never-a-deployment-secret-0000000'
        self.env = patch.dict(os.environ, {'EXTRACTOR_WEBHOOK_SECRET': self.secret, 'SUPABASE_STORAGE_HOST': 'example.supabase.co', 'FORGECLIP_APP_ORIGIN': 'https://forgeclipai.lovable.app'})
        self.env.start()
        asset, owner = str(uuid.uuid4()), str(uuid.uuid4())
        self.payload = {'jobId': str(uuid.uuid4()), 'assetId': asset, 'inputUrl': 'https://example.supabase.co/storage/v1/object/sign/uploads/source.mp4?token=test', 'outputUrl': f'https://example.supabase.co/storage/v1/object/upload/sign/audio-extracts/{owner}/{asset}.mp3?token=test', 'callbackUrl': 'https://forgeclipai.lovable.app/api/public/jobs/extractor-callback', 'callbackSecret': self.secret, 'format': 'mp3', 'bitrateKbps': 64}
        service.initialize()
    def tearDown(self):
        self.env.stop()
        service.DATA = self.previous_data
        self.temp.cleanup()
    def test_dispatch_contract_and_secret_not_persisted(self):
        result = service.validate(self.payload)
        self.assertTrue(result['audioPath'].endswith(self.payload['assetId']+'.mp3'))
        self.assertNotIn('callbackSecret', result)
        self.assertNotIn(self.secret, json.dumps(result))
    def test_rejects_untrusted_media_or_callback_destinations(self):
        cases = [('inputUrl', 'https://127.0.0.1/private'), ('inputUrl', 'http://example.supabase.co/storage/v1/object/sign/uploads/source.mp4'), ('inputUrl', 'https://example.supabase.co.evil.example/storage/v1/object/sign/uploads/source.mp4'), ('callbackUrl', 'https://elsewhere.example/callback'), ('outputUrl', self.payload['outputUrl'].replace(self.payload['assetId'], str(uuid.uuid4()))), ('callbackSecret', 'wrong-secret')]
        for field, value in cases:
            with self.subTest(field=field, value=value):
                payload = {**self.payload, field: value}
                with self.assertRaises(service.InvalidRequest): service.validate(payload)
    def test_queue_deduplicates_dispatch_and_survives_restart(self):
        payload = service.validate(self.payload)
        service.enqueue(payload); service.enqueue(payload)
        with service.connection() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM jobs').fetchone()[0], 1)
            db.execute("UPDATE jobs SET status='running'")
        service.initialize()
        with service.connection() as db:
            self.assertEqual(db.execute('SELECT status FROM jobs').fetchone()[0], 'queued')
    def test_real_local_mp4_audio_extraction(self):
        source, output = service.DATA/'source.mp4', service.DATA/'audio.mp3'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=black:s=160x90:r=24:d=1','-f','lavfi','-i','sine=frequency=440:duration=1','-c:v','libx264','-c:a','aac','-shortest','-y',str(source)], check=True)
        duration, size = service.extract(source, output, 'mp3', 64)
        self.assertAlmostEqual(duration, 1, places=1)
        self.assertGreater(size, 0)
    def test_silent_video_fails_explicitly(self):
        source, output = service.DATA/'silent.mp4', service.DATA/'audio.mp3'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=black:s=160x90:r=24:d=1','-c:v','libx264','-an','-y',str(source)], check=True)
        with self.assertRaisesRegex(service.InvalidRequest, 'no audio stream'):
            service.extract(source, output, 'mp3', 64)

if __name__ == '__main__': unittest.main()
