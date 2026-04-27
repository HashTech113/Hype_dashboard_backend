# AI CCTV Attendance System

Local production-grade CCTV-based office attendance system. FastAPI + PostgreSQL + InsightFace + OpenCV. No cloud, no paid services.

## Features
- 4 RTSP cameras (2 ENTRY + 2 EXIT), one dedicated thread per camera, 1 FPS processing
- InsightFace (buffalo_l) face detection + recognition, CPU inference by default
- Attendance state machine: `IN → BREAK_OUT → BREAK_IN → OUT` per employee per day
- Global 5-second cooldown per employee to prevent duplicate detections
- Event-based snapshot storage (only on real state transitions)
- Unknown faces silently dropped (no DB, no snapshot)
- Admin panel APIs (JWT-authenticated), role-based access
- Manual correction (add/edit/delete events) with full audit flag (`is_manual`, `corrected_by`)
- Excel reports: daily, monthly, per-employee date range
- Automatic camera health monitoring and self-healing workers

## Requirements
- Python 3.11
- PostgreSQL 14+
- Windows 10 / Linux (tested on Windows 10)

## Install

```bash
python -m venv .venv
.venv\Scripts\activate           # Windows
pip install -r requirements.txt
cp .env.example .env              # then edit credentials / RTSP URLs
```

## Database
Create a PostgreSQL database matching `DATABASE_URL` in `.env`, then:

```bash
alembic upgrade head
```

## Run

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

On first boot, a super-admin is created from `BOOTSTRAP_ADMIN_USERNAME` / `BOOTSTRAP_ADMIN_PASSWORD` (env). Log in and change the password immediately.

## First-time setup flow
1. `POST /api/v1/auth/login` — obtain JWT.
2. `POST /api/v1/cameras` — register 4 cameras (2 ENTRY + 2 EXIT) with their RTSP URLs.
3. `POST /api/v1/employees` — create employees.
4. `POST /api/v1/employees/{id}/training/images` — upload 5–20 face images per employee (multipart).
5. Done. Workers automatically recognize faces and create attendance events.

## API overview (all under `/api/v1`)
- `auth` — login, current admin
- `employees` — CRUD
- `employees/{id}/training` — upload images, list/delete embeddings, rebuild cache
- `cameras` — CRUD + restart + health
- `attendance` — list events, list sessions, manual create/update/delete
- `snapshots` — list + fetch image
- `reports` — daily / monthly / employee Excel
- `admin` — stats, live-status

## Architecture
See the design notes. Clean architecture: `api → services → repositories → models`. Recognition model and embedding cache are process-wide singletons shared between the API and camera threads. Each camera runs in a dedicated thread with resilient RTSP reconnect.

## Storage layout
```
storage/
  models/                         (InsightFace model cache)
  training_images/{code}/*.jpg    (raw training images)
  snapshots/YYYY/MM/DD/*.jpg      (event snapshots)
logs/
  app.log                         (rotating)
```

## Notes
- Change `JWT_SECRET_KEY` in production.
- Recognition threshold `FACE_MATCH_THRESHOLD=0.45` is a safe default for `buffalo_l` cosine similarity; tune per site.
- The cooldown is global per employee — any detection within 5 s of the last registered event is ignored.
- Manual events still participate in the day's state machine via session recomputation.
