# ForgeClip audio-extractor deployment

This is deployable source for the external worker contract currently implemented in `src/lib/jobs/extractor.server.ts`. It has not been deployed to a hosting account. It accepts authenticated extraction jobs, downloads only from the configured Supabase storage host, extracts speech-optimised mono audio using ffmpeg, uploads through the supplied signed URL, and sends the exact callback payload expected by the existing application.

Required environment variables (values belong in the hosting provider's secret/configuration interface):

- `EXTRACTOR_WEBHOOK_SECRET`: a random shared secret of at least 32 characters, identical in the app and worker.
- `SUPABASE_STORAGE_HOST`: the exact hostname from the existing Supabase project URL. Host only, with no scheme or path.
- `FORGECLIP_APP_ORIGIN`: `https://forgeclipai.lovable.app`, unless the app's production origin changes.
- `DATA_DIR`: a writable **persistent volume**, mounted at `/data` by default. One service replica owns this SQLite queue. Use a managed durable queue before scaling to multiple replicas.

Deploy the Dockerfile behind your host's managed HTTPS endpoint, with an always-running worker and a persistent volume. Cloud Run-style CPU suspension after the HTTP response is not compatible with this background-worker design unless CPU is allocated continuously. Configure `EXTRACTOR_ENDPOINT` in ForgeClip to `https://<worker-host>/extract`. Set the same webhook secret on both sides. `/health` is the unauthenticated liveness endpoint; it exposes no job metadata.

The default worker input limit is 2 GiB and recording duration limit is 30 minutes. This matches the current backend's single-audio-file path. The app's longer-recording chunking path still needs a separate per-chunk upload contract and integration; raising this worker limit alone does not implement long-video chunking. Maximum extracted audio is 24 MiB, below the transcription gateway's documented 25 MiB bound.

Dispatch job IDs are idempotent while retained in the durable queue. Interrupted extraction jobs are requeued on restart. Callback deliveries retry from durable storage; signed media URLs are removed after processing. The current app callback handler should also be made idempotent before enabling automatic callback retries in a live environment, because duplicate successful callbacks must not enqueue duplicate transcription work. No paid transcription/render jobs have been triggered by the local worker checks.

The worker intentionally uses the existing Supabase signed URLs rather than storing a Supabase service-role key. It rejects redirects, non-HTTPS URLs, arbitrary storage hosts, mismatched asset paths and callback origins. Source and output URLs are never printed in logs. Configure appropriate host request/connection limits, log retention, disk capacity and callback alerting before public production activation.
