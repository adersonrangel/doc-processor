# doc-processor-prototype

End-to-end prototype of a document-processing pipeline: Next.js client -> FastAPI API -> Redis + Celery worker -> AI agent -> Postgres (state) + local disk (files). Agent logic is intentionally minimal for now (returns the uploaded filename); the full architecture (extractor -> agent loop -> validator) is in place to be extended later.

## Specs

S1. (user, verbatim) "La idea por ahora es que solo se guarde los datos basicos del documento subido. No vamos a extraer nada, solo validar que el prototipo funciona."
S2. (user, verbatim) "solo el nombre del archivo" — the agent's only output is the original filename.
S3. (user, verbatim) "el motor clasificador dejalo limpio sin tocar. si requieres crea uno nuevo especifico para este proyecto pero no los mescles." — do NOT modify the existing `/home/arangel/GitHub/python/motor-clasificador`; build anything new here, separate.
S4. (user, verbatim) "OpenRouter (como el motor)" — the agent uses OpenRouter (same provider as the existing motor). Default backend is `deterministic` so the prototype runs without a key; `openrouter` activates when `OPENROUTER_API_KEY` is set.
S5. (user, verbatim) "Cliente Next.js completo" — the frontend is a full Next.js client (upload + live status + job list).
S6. (architecture) Four pieces in a line: web client (uploads the file, shows status) -> API (validates type/size/user, stores the file, creates the job, returns job_id in milliseconds) -> queue (Redis; decouples reception from processing so N files queue instead of crashing) -> worker (runs the agent; scale by duplicating workers without touching the API).
S7. (architecture) Three shared services: file storage (on disk, never in the DB), Postgres (state of each job: pending/processing/ready/error), and the AI model.
S8. (architecture) The API responds with job_id without waiting for the agent; the browser learns the result by polling every 2-3 s (chosen for the MVP over SSE/WebSocket).
S9. (architecture) Worker = pipeline with a loop in the middle: extractor (for now NO extraction; only reads/verifies the file and basic metadata) -> agent (decides what to do, calls a tool, observes the result, repeats until done; tools can be Python, an API call, or business rules) -> validator (checks the output matches the expected format and produces the deliverable).
S10. (architecture) Limits and max times: fix a max file size, a max number of agent iterations, and a max time per job, or a weird file can loop and waste money.
S11. (architecture) File security: scan uploaded files, isolate the worker, use temporary download links, and define how long documents are kept.
S12. (architecture) Idempotency and retries: if the worker dies mid-job, the job must be retryable without duplicating results.
S13. (architecture) Traceability: store what the agent did at each step (useful for debugging and, for sensitive domains, auditing).
S14. (constraint) Files are stored on local disk for now (not S3, never in the DB).
S15. (constraint) Postgres is already up in a container (`postgres-remoto`, port 5432). Use the dedicated DB `prototipo` (already created; user `arangel`, pass in `.env`). Do NOT start a new Postgres.
S16. (constraint) Redis runs in a container (`redis-prototipo`, port 6379). Use it as the Celery broker.

### API contract (shared by backend + frontend)

Base URL: `http://localhost:8000` (the client overrides it with `NEXT_PUBLIC_API_URL`).

- `POST /api/jobs`
  - `multipart/form-data`, field `file` (required).
  - Validates: allowed extensions (`pdf`, `xlsx`, `docx`, `txt`), max size `MAX_FILE_SIZE_MB` (default 10).
  - On success: stores the file on disk, creates the job (status `pending`), enqueues the Celery task.
  - Returns `202`: `{ "job_id": "<uuid>", "status": "pending" }`.
  - On invalid type/size: `400` with `{ "detail": "..." }`.
- `GET /api/jobs/{job_id}`
  - Returns `200`: `{ "job_id": "<uuid>", "status": "pending|processing|ready|error", "original_filename": "a.pdf", "content_type": "application/pdf", "size_bytes": 123, "result": "a.pdf" | null, "error": null | "msg", "created_at": "<iso8601>", "updated_at": "<iso8601>" }`.
  - Unknown id: `404`.
- `GET /api/jobs`
  - Returns `200`: `{ "jobs": [ { "job_id", "status", "original_filename", "created_at" } ] }`, newest first, capped at 50.
- `GET /api/health`
  - Returns `200`: `{ "ok": true }`.

CORS: allow `http://localhost:3000` and `http://127.0.0.1:3000`.

### Data model (Postgres DB `prototipo`)

Table `jobs`:
- `id` UUID PK (default `gen_random_uuid()`)
- `status` TEXT NOT NULL (one of: `pending`, `processing`, `ready`, `error`)
- `original_filename` TEXT NOT NULL
- `content_type` TEXT
- `size_bytes` BIGINT
- `file_path` TEXT (path on local disk)
- `file_sha256` TEXT (idempotency / dedupe)
- `result` TEXT NULL (the produced deliverable; for now the original filename)
- `error_message` TEXT NULL
- `created_at` TIMESTAMPTZ NOT NULL default now()
- `updated_at` TIMESTAMPTZ NOT NULL default now()

Table `job_steps` (traceability, S13):
- `id` UUID PK
- `job_id` UUID FK -> jobs.id (ON DELETE CASCADE)
- `step` TEXT NOT NULL (e.g. `extract`, `agent.iteration.1`, `agent.tool.<name>`, `validate`)
- `detail` TEXT (free text, may be JSON)
- `created_at` TIMESTAMPTZ NOT NULL default now()

### Agent design

An `AgentRunner` with a pluggable backend selected by env `AGENT_BACKEND` (`deterministic` default, or `openrouter`).
- Both backends receive the job's file metadata and must produce a `result` string. For the prototype the expected result is the `original_filename`.
- `deterministic`: no network. Reads the filename, records an agent step, returns it. Used when no key is configured so the prototype always runs.
- `openrouter`: a real tool-use agent via the OpenRouter SDK (same provider as the existing motor). For the prototype the single tool is trivial (returns the file metadata); the model is instructed to output the filename. Used when `OPENROUTER_API_KEY` is set and `AGENT_BACKEND=openrouter`. If the call fails, mark the job `error` with the message (do not silently fall back).
- Limits (S10): `MAX_AGENT_ITERATIONS` (default 5) and a per-job timeout via Celery `time_limit` (default 120 s).
- Every agent iteration / tool call is recorded in `job_steps` (S13).

### File storage (S14)

- Storage dir: `api/storage/uploads/` (gitignored). Layout: `{job_id}/{uuid8}_{safe_original_filename}`.
- On upload: validate extension + (best-effort) MIME, size <= cap; stream to disk; compute sha256.
- The worker never re-writes the file; it only reads metadata.
- Retention: define `FILE_RETENTION_DAYS` (default 7) as config; no cleanup job required for the MVP (note only).

### Config (backend, via env / `.env`)

- `DATABASE_URL=postgresql+psycopg://arangel:Qazw5xedc@localhost:5432/prototipo`
- `REDIS_URL=redis://localhost:6379/0`
- `STORAGE_DIR=api/storage/uploads`
- `MAX_FILE_SIZE_MB=10`
- `ALLOWED_EXTENSIONS=pdf,xlsx,docx,txt`
- `AGENT_BACKEND=deterministic` (or `openrouter`)
- `OPENROUTER_API_KEY=` (optional; if empty only deterministic works)
- `OPENROUTER_MODEL=` (optional; provider default)
- `MAX_AGENT_ITERATIONS=5`
- `JOB_TIMEOUT_SECONDS=120`
- `FILE_RETENTION_DAYS=7`
- `CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000`

No API-key auth for the prototype (open endpoints). The existing motor's `X-API-Key` pattern is NOT required here.

### Backend file layout (`api/`)

- `pyproject.toml` (deps: `fastapi`, `uvicorn[standard]`, `celery`, `redis`, `sqlalchemy`, `psycopg[binary]`, `pydantic-settings`, `python-multipart`; dev: `pytest`, `httpx`)
- `.env`, `.env.example`, `.gitignore`
- `app/__init__.py`
- `app/config.py` — pydantic-settings `Settings`
- `app/db.py` — SQLAlchemy engine + session factory
- `app/models.py` — `Job`, `JobStep` (declarative)
- `app/schemas.py` — Pydantic request/response models
- `app/storage.py` — safe filename, stream-to-disk, sha256
- `app/validation.py` — extension / MIME / size checks
- `app/agent/__init__.py`
- `app/agent/base.py` — `AgentRunner` interface + limits + trace helper
- `app/agent/deterministic.py`
- `app/agent/openrouter.py`
- `app/worker.py` — Celery app (`celery_app`) + `process_job(job_id)` task
- `app/main.py` — FastAPI app, endpoints, CORS, create tables on startup
- `tests/test_validation.py`, `tests/test_agent.py`, `tests/test_api.py` (API tests use `TestClient` + temp storage + a throwaway DB or SQLite fallback)

Run:
- API: `uvicorn app.main:app --host 0.0.0.0 --port 8000`
- Worker: `celery -A app.worker.celery_app worker --loglevel=info`

### Frontend file layout (`web/`) — Next.js (App Router, TypeScript)

Scaffold manually (do NOT run interactive `create-next-app`):
- `package.json`, `next.config.mjs`, `tsconfig.json`, `.env.local` (`NEXT_PUBLIC_API_URL=http://localhost:8000`), `.gitignore`
- `app/layout.tsx`, `app/page.tsx`, `app/globals.css`
- `components/UploadForm.tsx` — file picker / drag-drop; `POST /api/jobs`; then start polling.
- `components/JobStatus.tsx` — shows status + result for one job; poll every 2.5 s until `ready`/`error`.
- `components/JobList.tsx` — `GET /api/jobs` list.
- `lib/api.ts` — typed fetch helpers.

### Tasks

- T1 [backend] S1-S16 — backend scaffold: config, db, models, schemas, storage, validation, agent (deterministic + openrouter), worker, main, tests. Writer: `gentle-ai-worker`.
- T2 [frontend] S5, S8 — Next.js client: upload, poll status, job list. Writer: `gentle-ai-worker`.
- T3 [integration] — run API + worker + web; end-to-end upload -> status -> result; verify polling works. Parent inline.

## Log

L1. (user, original) "Utiliza este enlace para entender los requerimientos de lo que vamos a construir. https://claude.ai/share/07f62110-801e-4bfa-8fc6-adde373052c6. Utiliza Redis + celerity como opcion de comunicación Cola y workers. Para los archivos almacenalos en local por ahora. En Estado el Postgres ya esta levantado en forma de contenedor asi que no necesitas levantarlo de nuevo. Valida y haceme cualqueir prgutna que requieras"
L2. (user) Pasted the three-diagram architecture: general web client -> API -> queue -> worker + shared storage/DB/AI; sequence (API returns job_id in ms; polling vs SSE/WebSocket); worker interior (extractor -> agent loop -> validator); key design decisions (deterministic where possible, limits, file security, idempotency, traceability); reference stack (Next.js / FastAPI / Redis+Celery or RQ / S3 / Postgres / Claude API with tool use); MVP can run on one server.
L3. (user) Redis: start a container. Target DB: a new dedicated DB. Motor: leave the existing `motor-clasificador` clean and untouched; if a new one is needed create it specific to this project, do not mix them.
L4. (user) Document type: for now only store the basic data of the uploaded document, no extraction, just validate the prototype works. Agent output: only the filename. AI: OpenRouter (same as the motor). Frontend: full Next.js client.
L5. (verification) E2E validated end-to-end: uploaded `hola.txt` -> `pending -> processing -> ready`, `result: "hola.txt"`, 4 `job_steps` recorded (extract / agent.iteration.1 / agent.tool.get_file_metadata / validate), file stored on disk at `api/storage/uploads/{job_id}/...`. Error paths return 400 (extension `.exe`; 11 MB size). 51/51 backend tests pass. Next.js client starts and serves (HTTP 200). Work-unit commits: `4fb7ef2` (spec), `89aedcf` (api data layer), `87c3d5e` (api endpoints+worker+agent), `6a8f274` (api tests), `3830e25` (web). Risk: none.
