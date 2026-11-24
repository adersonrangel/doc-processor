# Doc Processor — web client (Next.js)

Full Next.js (App Router, TypeScript) client for the doc-processor prototype: upload a
document, follow its live status by polling, and browse the most recent jobs.

## Requirements

- Node.js 20+
- The backend API running at `http://localhost:8000` (see `../api/`)

## Setup

```bash
npm install
npm run dev      # http://localhost:3000
```

The API base URL is read from `NEXT_PUBLIC_API_URL` and defaults to
`http://localhost:8000`. To point the client somewhere else, create `web/.env.local`
with:

```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

> `.env.local` is intentionally not gitignored in this project (it only carries the
> public API base URL, no secrets). It is not committed yet because the scaffold has
> no backend-specific config.

## Scripts

- `npm run dev` — development server on port 3000
- `npm run build` — production build
- `npm start` — serve the production build
- `npm run typecheck` — `tsc --noEmit`

## API contract used

- `POST /api/jobs` — multipart, field `file`; returns `202 { job_id, status }`
- `GET /api/jobs/{job_id}` — returns the job state, polled every 2.5 s until
  `ready` or `error`
- `GET /api/jobs` — returns `{ jobs: [...] }`, newest first
