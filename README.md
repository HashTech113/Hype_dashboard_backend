# AI CCTV Attendance System

Production-grade CCTV-based office attendance system. Local deployment, no cloud dependencies.

Monorepo:

| Path | Description |
|---|---|
| [`backend/`](./backend/) | FastAPI + PostgreSQL + InsightFace + OpenCV — camera pipeline, recognition, attendance logic, admin APIs |
| [`frontend/`](./frontend/) | Next.js 15 (App Router) + TypeScript + Tailwind + ShadCN — admin dashboard |

## Quick start

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate                # Windows (or: source .venv/bin/activate)
pip install -r requirements.txt
cp .env.example .env                   # edit DATABASE_URL, JWT_SECRET_KEY, RTSP URLs, etc.
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

On first boot a super-admin is seeded from `BOOTSTRAP_ADMIN_USERNAME` / `BOOTSTRAP_ADMIN_PASSWORD` — **change the password immediately**.

### Frontend

```bash
cd frontend
npm install
cp .env.local.example .env.local       # defaults to http://localhost:8000/api/v1
npm run dev                             # http://localhost:3000
```

Sign in with the bootstrapped super-admin credentials.

## Feature summary

- 4 RTSP cameras (2 ENTRY + 2 EXIT), one dedicated thread per camera at 1 FPS
- InsightFace `buffalo_l` face detection + recognition (CPU inference by default)
- Multi-break attendance state machine: `IN → (BREAK_OUT → BREAK_IN)* → OUT`
- Global 5-second cooldown per employee (runtime-tunable)
- Event-based snapshot storage — face crop only, `YYYY-MM-DD/EMP_ID/` layout
- Unknown faces silently dropped (no DB write, no snapshot)
- Late entry / early exit tracking with configurable grace windows (default 09:30–18:30)
- Auto-update embeddings on high-confidence recognition (opt-in)
- Manual correction (add/edit/delete events) with full audit trail
- Day-close job converts trailing `BREAK_OUT` to `OUT`
- Excel reports: daily, monthly, date range, per-employee
- Admin dashboard with live stats, presence breakdown, event timeline
- JWT-authenticated APIs with role-based access (`SUPER_ADMIN`, `ADMIN`, `VIEWER`)
- Runtime-tunable settings (threshold, cooldown, office hours, grace) — no restart needed

## Architecture

See [`backend/README.md`](./backend/README.md) for backend design and [`frontend/README.md`](./frontend/README.md) for frontend layout.
