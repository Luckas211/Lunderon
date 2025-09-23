### Quick context

This repository is a Django 4.2 app (project: `gerador_videos`) that powers a short-form vertical video generator (Lunderon). Major features:
- Single Django app `core/` contains models, views, forms and business logic.
- Uses Cloudflare R2 via `django-storages` (S3Boto3Storage) for media; custom storage in `core/storage.py` and storage-backed FileFields in `core/models.py`.
- Video/audio processing uses system `ffmpeg` (invoked via subprocess), `faster-whisper` (in `core/transcription_utils.py`) for transcription and per-word timestamps, and a Kokoro TTS pipeline (`KPipeline`) in `core/views.py`.
- Payments handled via Stripe (webhook logic in `core/views.py`) and Stripe Price IDs stored on `Plano.stripe_price_id`.
- YouTube metadata extraction uses `yt_dlp` (see `core/views.py::get_youtube_segments`).

### Files & locations you should read first
- `gerador_videos/settings.py` — env configuration (.env read with `django-environ`), Cloudflare R2 and Stripe keys, `DEFAULT_FILE_STORAGE` override.
- `core/models.py` — domain models (Usuario, Plano, Assinatura, VideoGerado, VideoBase, MusicaBase) and R2 object_key conventions (e.g. `media/videos_base/...`).
- `core/views.py` — the heart of the generator: ffmpeg command construction, R2 helpers (download/upload/delete), Stripe webhook handling, Kokoro usage, and form handling (large file — scan top-level helpers first).
- `core/transcription_utils.py` — Whisper model usage (faster-whisper), extraction helpers: `extract_audio_from_video`, `transcribe_audio_to_srt`, `get_word_timestamps` (used by precise/karaoke ASS subtitle generation).
- `core/storage.py` — custom `MediaStorage` (public URL via `CLOUDFLARE_R2_PUBLIC_URL`).
- `requirements.txt` — canonical runtime dependencies.

### Environment & dev workflows (how to run / common tasks)
- The project expects a Python virtualenv and the packages in `requirements.txt`.
- Environment variables are loaded from a `.env` at project root. Critical vars:
  - `SECRET_KEY`, `DEBUG`, `DATABASE_URL` (or DB-specific vars), Stripe keys (`STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET`), Cloudflare R2 keys (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_STORAGE_BUCKET_NAME`, `AWS_S3_ENDPOINT_URL`).
- Common developer commands (powershell examples):
  - Install deps (create venv first): powershell: python -m venv .venv; .\.venv\Scripts\Activate.ps1; pip install -r requirements.txt
  - Run migrations: python manage.py migrate
  - Create superuser: python manage.py createsuperuser
  - Run dev server: python manage.py runserver
  - Run tests: python manage.py test

Notes: ffmpeg must be installed on the host and available on PATH. Whisper relies on `faster-whisper` and will load models on CPU by default (see `core/transcription_utils.py`), which may be heavy locally.

### Runtime/integration details AI agents need to know
- Storage / object_keys: `VideoBase` and `MusicaBase` save an `object_key` like `media/videos_base/{categoria.pasta}/{filename}`. Helpers in `core/views.py` expect either a public URL or an object_key and will generate presigned URLs when needed (`generate_presigned_url`). Use boto3 with the `AWS_S3_ENDPOINT_URL` to access R2.
- Media URLs: `core/storage.py` sets `custom_domain = CLOUDFLARE_R2_PUBLIC_URL`. Public URLs may be returned without signatures (this is intentional).
- ffmpeg usage: The project builds long `ffmpeg` filter_complex strings in `core/views.py::pagina_gerador`. When editing, preserve how inputs are indexed and how indices shift when text-image overlays or narrator audio are present. Check how `music_input_index` and `narrator_input_index` are computed.
- Subtitles: Precise (karaoke) subtitles are created by `core/views.py::gerar_legenda_karaoke_ass`, which consumes the per-word timestamps from `core/transcription_utils.get_word_timestamps()` and produces a `.ass` file in `MEDIA_ROOT/legenda_temp`.
- TTS: Kokoro `KPipeline` is invoked in `core/views.py::gerar_audio_e_tempos` and `preview_voz`. Handle fallback logic (voice fallback to `pf_dora`).
- Stripe: Webhook handling accepts `checkout.session.completed`, `invoice.paid`, `invoice.payment_failed`, and `customer.subscription.deleted`. `Plano` must have `stripe_price_id` set to create checkout sessions.

### Coding patterns & conventions (project-specific)
- Single app-centric design: Most logic lives in `core/` rather than splitting into many apps; prefer adding helpers in `core/` for cross-cutting concerns.
- File cleanup: Temporary files are written under `MEDIA_ROOT` in subfolders (`audio_temp`, `text_temp`, `legenda_temp`, `videos_gerados`) and explicitly removed in `finally` blocks — keep that cleanup discipline when adding code.
- Storage access: Prefer using `object_key` fields and the provided helpers `generate_presigned_url`, `download_from_cloudflare`, `upload_to_r2`, `delete_from_r2` in `core/views.py` rather than calling boto3 directly.
- DB patterns: `Assinatura.save()` updates `usuario.plano_ativo` (side-effect). Prefer using `Assinatura.objects.update_or_create()` or `select_related`/`prefetch_related` for optimized queries as done in `admin_usuarios`.

### Tests, debugging and safety notes
- Tests: `manage.py test` runs Django tests — see `core/tests.py` for existing cases. Running tests may require environment variables and an accessible DB; prefer setting `DEBUG=True` and using sqlite for local test runs.
- Debugging ffmpeg errors: Many FFmpeg calls run with capture_output; when a CalledProcessError is caught the code prints `e.stderr`. If you change ffmpeg invocation, add robust logging of the constructed command and stderr to speed debugging.
- Resource heavy ops: Whisper model loading and ffmpeg rendering are CPU/memory intensive. When iterating locally, use small test inputs or mock calls to the ffmpeg subprocess or faster-whisper to avoid long runs.

### Quick examples an agent can use
- To find the code path that generates final videos: read `core/views.py` — `pagina_gerador` (form handling) → ffmpeg subprocess → `upload_to_r2` → `VideoGerado.objects.create(status='CONCLUIDO', arquivo_final=object_key)`.
- To add a new storage-backed field, follow pattern in `VideoBase.arquivo_video` and set `object_key` in `save()`.

### If you need more info
- Ask for: (1) a sample `.env` (do not share secrets), (2) whether CI runs migrations and where hosting is (Cloud Run/VM), (3) whether Kokoro is a licensed internal service or should be stubbed locally.

If anything here is unclear or you'd like more detail on a specific area (FFmpeg filter construction, Stripe webhook flows, or R2 presigned URL usage), tell me which area to expand and I'll iterate.
