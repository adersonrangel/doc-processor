# Doc Processor — Prototype

End-to-end prototype of a document-processing pipeline:

```
Next.js client  ->  FastAPI API  ->  Redis (queue)  ->  Celery worker  ->  AI agent
      |                                                        |
      +-----------<---- polling (status) <---- Postgres (state) + local disk (files)
```

The API receives an uploaded file, validates it, stores it on local disk, and immediately
returns a `job_id`. A Celery worker (decoupled via Redis) runs a minimal agent that, for now,
just returns the uploaded filename. Job state lives in Postgres; files never go into the
database.

> This is a **prototype**. The agent logic is intentionally minimal (no extraction) to validate
> the full pipeline. The architecture (`extractor -> agent loop -> validator`) is in place to be
> extended later.

## Architecture

- **Web client** (`web/`) — Next.js (App Router, TypeScript). Uploads the file, polls status.
- **API** (`api/`) — FastAPI. Validates (type/size), stores the file on disk, creates the job,
  enqueues it, and responds in milliseconds with the `job_id`.
- **Queue** — Redis. Decouples reception from processing (many files queue instead of crashing).
- **Worker** — Celery. Runs the agent pipeline `extract -> agent -> validate`. Idempotent.
- **State** — PostgreSQL (dedicated DB `prototipo`). Job status `pending/processing/ready/error`
  plus `job_steps` traceability.
- **Files** — local disk (`api/storage/uploads/`), never in the DB.
- **Agent** — pluggable: `deterministic` (default, no key) or `openrouter` (real tool-use agent).

## Prerequisites

- Python 3.12+
- Node.js 20+
- PostgreSQL on `localhost:5432` with a dedicated database `prototipo` (e.g. a `postgres:16` container).
- Redis on `localhost:6379` as the Celery broker (e.g. a `redis:7` container).

## Setup

### 1. Configure the backend environment

Create `api/.env` (it is gitignored — do **not** commit it):

```ini
DATABASE_URL=postgresql+psycopg://<user>:<pass>@localhost:5432/prototipo
REDIS_URL=redis://localhost:6379/0
STORAGE_DIR=<absolute path to this repo>/api/storage/uploads
MAX_FILE_SIZE_MB=10
ALLOWED_EXTENSIONS=pdf,xlsx,docx,txt
FILE_RETENTION_DAYS=7
AGENT_BACKEND=deterministic        # or: openrouter
OPENROUTER_API_KEY=                # only needed when AGENT_BACKEND=openrouter
OPENROUTER_MODEL=
MAX_AGENT_ITERATIONS=5
JOB_TIMEOUT_SECONDS=120
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
```

> Every value above is also a built-in default in `api/app/config.py`, so the app runs without
> `.env` for the local prototype. Set `.env` to override (especially `OPENROUTER_API_KEY`).

### 2. Install the backend

```bash
cd api
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### 3. Install the frontend

```bash
cd web
npm install
```

(Optional) create `web/.env.local` to override the API base URL:

```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

It defaults to `http://localhost:8000`, so this file is optional.

## Run

Three processes (one per terminal):

```bash
# 1. API (FastAPI) — http://localhost:8000
cd api && .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000

# 2. Worker (Celery) — consumes the Redis queue
cd api && .venv/bin/celery -A app.worker.celery_app worker --loglevel=info

# 3. Web client (Next.js) — http://localhost:3000
cd web && npm run dev
```

Then open `http://localhost:3000`, upload a file, and watch it go `pending -> processing -> ready`.

Production-like web:

```bash
cd web && npm run build && npm start
```

### Optional: monitoring dashboard (Flower)

Flower is a real-time web UI for the Celery cluster (workers, queue, task rates, and task
revocation). Run it in a fourth terminal once the API and worker are up:

```bash
cd api && .venv/bin/celery -A app.worker.celery_app flower --port=5555 --address=127.0.0.1
```

Then open `http://localhost:5555`. It connects to the same Redis broker and shows the
`process_job` tasks and any running workers. It is optional — stop it when you don't need
the dashboard.

## API

Base URL `http://localhost:8000` (CORS allows the dev client on `:3000`).

| Method | Path                 | Description                                              |
|--------|----------------------|----------------------------------------------------------|
| POST   | `/api/jobs`          | Upload a file (multipart, field `file`). Returns `202 { job_id, status }`. |
| GET    | `/api/jobs/{job_id}` | Job state (incl. `result` / `error`). `404` if unknown.   |
| GET    | `/api/jobs`          | Recent jobs, newest first, capped at 50.                  |
| GET    | `/api/health`        | Liveness. Returns `{ "ok": true }`.                       |

Upload validation: allowed extensions `pdf, xlsx, docx, txt` and a max size of
`MAX_FILE_SIZE_MB` (default 10). Violations return `400`.

## Tests

```bash
cd api
.venv/bin/python -m pytest tests/ -q
```

Tests run against a throwaway database and a temp storage dir, so they never touch the real
`prototipo` DB or the local upload directory.

## Project layout

```
.
├── api/            # FastAPI + Celery backend
│   ├── app/        #   config, db, models, schemas, storage, validation,
│   │   └── agent/  #   agent backends (deterministic, openrouter)
│   └── tests/
├── web/            # Next.js client (App Router, TypeScript)
├── odd/            # ODD spec + task tracking
└── .gitignore
```

## Security & limits (by design)

- Files are stored on local disk, never in the database.
- The worker is **idempotent**: re-running a job updates it instead of duplicating results.
- The agent is bounded by `MAX_AGENT_ITERATIONS` and a per-job timeout (`JOB_TIMEOUT_SECONDS`
  via Celery `time_limit`).
- Every agent step is recorded in `job_steps` (traceability / auditing).
