# AI Camera Surveillance

> Real-time face recognition + people tracking on local IP cameras. Packaged as a Windows desktop application with zero-prerequisite install — no cloud, no manual config, no DevOps.

[![Made with FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Next.js](https://img.shields.io/badge/Next.js-15-black?logo=next.js&logoColor=white)](https://nextjs.org/)
[![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)](https://python.org)
[![InsightFace](https://img.shields.io/badge/InsightFace-buffalo__l-FF6B35)](https://github.com/deepinsight/insightface)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791?logo=postgresql&logoColor=white)](https://postgresql.org)

---

## What it does

Connects to **any RTSP IP camera** (Hikvision, Dahua, CP Plus, Axis, Reolink, generic ONVIF) and turns it into a smart surveillance station that:

- **Streams live in real time** — sub-200 ms end-to-end latency via a custom event-driven worker architecture with continuous-drain FFmpeg pipeline
- **Recognises faces** — InsightFace `buffalo_l` (512-D embeddings, ~98% accuracy on LFW)
- **Logs every entry / exit / unknown** — multi-break state machine, manual correction, audit trail
- **Auto-discovers cameras** — ONVIF WS-Discovery + parallel TCP scan finds cameras on the LAN
- **Installs like a game** — single `Setup.exe` bundles Python, Node, Postgres, models. Double-click → 5 minutes later you have a native desktop app with custom icon

## Live preview architecture

The hardest engineering problem in this project: keep a 20 fps RTSP stream flowing to the browser at sub-200 ms latency, with face recognition running on the same machine, without dropping frames or accumulating buffer lag.

```
┌──────────────┐    ┌──────────────────────┐    ┌─────────────────────────┐
│              │    │  RTSP Reader         │    │  Camera Worker          │
│  IP Camera   │───▶│  (continuous-drain   │───▶│  ┌─────────────────┐    │
│  (Hikvision) │    │   thread, never      │    │  │ FAST THREAD     │    │
│  20 fps      │    │   blocks, keeps      │    │  │ - publishes     │    │
│  RTSP/H.264  │    │   only freshest      │    │  │   frame to WS   │    │
└──────────────┘    │   frame in a slot)   │    │  │ - pre-encodes   │    │
                    └──────────────────────┘    │  │   JPEG once     │    │
                                                │  │   (shared by N  │    │
                                                │  │   browsers)     │    │
                                                │  └─────────────────┘    │
                                                │  ┌─────────────────┐    │
                                                │  │ DETECTION       │    │
                                                │  │ THREAD          │    │
                                                │  │ - InsightFace   │    │
                                                │  │   detect+match  │    │
                                                │  │ - attendance    │    │
                                                │  │   pipeline      │    │
                                                │  │ - 1 Hz rate     │    │
                                                │  └─────────────────┘    │
                                                └────────────┬────────────┘
                                                             │
                                                             ▼
                                              ┌──────────────────────────┐
                                              │  WebSocket /preview.ws   │
                                              │  - backpressure-aware    │
                                              │  - single-encode shared  │
                                              │  - wall-clock timestamps │
                                              │  - browser drops frames  │
                                              │    older than 300ms      │
                                              └────────────┬─────────────┘
                                                           │
                                                           ▼
                                              ┌──────────────────────────┐
                                              │  Browser canvas          │
                                              │  - createImageBitmap     │
                                              │    (off main thread)     │
                                              │  - face overlay rendered │
                                              │  - measured live lag     │
                                              └──────────────────────────┘
```

**Key wins from the architecture:**

- **Continuous-drain reader thread** — solved the classic RTSP problem where `cap.read()` returns oldest queued frame. Drains FFmpeg in a tight loop, only the latest frame is ever served. Fixed accumulating buffer lag (5 s → 100 ms).
- **Fast + detection thread split** — face recognition runs at 1 Hz in a dedicated thread; the fast thread publishes frames at the camera's native rate (20 fps) and never blocks. Fixed the live preview being capped at 1.2 fps.
- **Pre-encoded JPEG sharing** — the worker fast thread encodes once per camera frame. All WebSocket clients (multiple browser tabs / operators) share the bytes. 4 viewers = same CPU cost as 1.
- **WebSocket backpressure** — `await ws.send_bytes()` naturally paces the producer to consumer speed. No buffer build-up possible.
- **Event-driven everywhere** — `threading.Condition` instead of polling sleeps means producer→consumer wakeup in ~1 ms.

## Production deployment

Single-machine local deployment, designed to run unattended for years. The installer pipeline turns this monorepo into a single `Setup.exe`:

```
deploy/build.cmd  →  AICameraSurveillance-Setup-1.0.0.exe (~900 MB)
                            │
                            ▼
            ┌─────────────────────────────────┐
            │   End user double-clicks        │
            │   Right-click → Run as admin    │
            │   Click Next × 4 → Install      │
            │                                 │
            │   Setup.exe silently installs:  │
            │   ✓ Visual C++ 2015-2022 redist │
            │   ✓ PostgreSQL 16 on port 55432 │
            │   ✓ Backend + venv + models     │
            │   ✓ Frontend production build   │
            │   ✓ Node.js portable runtime    │
            │   ✓ go2rtc WebRTC bridge        │
            │   ✓ NSSM Windows Services       │
            │   ✓ Native app launcher         │
            │                                 │
            │   Auto-generates JWT secret     │
            │   Auto-creates database         │
            │   Auto-runs Alembic migrations  │
            │                                 │
            │   Click Finish → browser opens  │
            │   to chromeless desktop app     │
            └─────────────────────────────────┘
```

## Tech stack

| Layer | Technology |
|---|---|
| **Backend** | FastAPI · SQLAlchemy 2 · Alembic · PostgreSQL 16 · psycopg2 |
| **Computer vision** | InsightFace (`buffalo_l`) · ONNX Runtime · OpenCV 4 · FFmpeg |
| **Live streaming** | Custom WebSocket protocol · go2rtc WebRTC bridge · pre-encoded JPEG sharing |
| **Frontend** | Next.js 15 (App Router) · TypeScript · Tailwind CSS · ShadCN UI · TanStack Query 5 · React 19 |
| **Auth** | JWT bearer · bcrypt · RBAC (SUPER_ADMIN / ADMIN / VIEWER) · force password rotation |
| **Process supervision** | NSSM (Windows Service) · auto-restart on crash · log rotation |
| **Installer** | Inno Setup 6 with Pascal-Script `[Code]` for runtime PG password generation |
| **Observability** | Per-camera fps regression detection · self-reporting workers · `/health/ready` deep checks |

## Engineering highlights

- **234-agent automated audit** — multi-stage workflow (15 parallel auditors → 3-skeptic adversarial verification → autonomous fix → reverify) caught 24 confirmed bugs across security / threading / race conditions and applied 48 in-tree fixes
- **17-check post-install smoke test** — verifies PG running, backend health, model loaded, frontend serving, end-to-end login flow; exit code 0/1 for monitoring
- **DPDP Act 2023 Section 8 compliance** — uninstall flow prompts for biometric data purge, preserves audit subtree, writes timestamped audit log
- **Self-healing first boot** — JWT secret auto-generates, database auto-creates if missing, Alembic auto-runs migrations, paths anchored to backend dir (CWD-independent)
- **Performance regression alerting** — `/health/ready` reports per-camera `actual_fps / expected_fps` ratio; worker self-reports drift to logs every 30 s
- **Zero-prerequisite installer** — Postgres, VC++ redist, Node, NSSM, go2rtc all bundled; auto-detects + skips if already present
- **Native desktop UX** — Edge `--app=` mode wrapped in a VBS launcher with custom icon, splash screen during NSSM boot, isolated browser profile

## Repository layout

```
ai-camera-attendance-system/
├── backend/                    FastAPI + computer vision
│   ├── app/
│   │   ├── api/v1/             REST endpoints (cameras, employees, attendance, …)
│   │   ├── services/           Business logic (face, attendance, snapshots, …)
│   │   ├── workers/            Camera pipeline (RTSP reader, worker, manager)
│   │   ├── models/             SQLAlchemy ORM
│   │   └── schemas/            Pydantic IO
│   └── migrations/             Alembic
│
├── frontend/                   Next.js 15 admin dashboard
│   ├── app/(auth)/             Login / change-password
│   ├── app/(dashboard)/        Live View / People Now / Cameras / Activity / etc.
│   ├── components/cameras/     WebSocket + WebRTC stream components
│   └── lib/                    API clients, hooks, types
│
└── deploy/
    ├── build.cmd               One-command installer build pipeline
    ├── installer/              Inno Setup .iss + Pascal-Script + asset staging
    ├── runtime/                NSSM service install/uninstall + smoke test
    └── PRODUCTION_GUARANTEES.md
```

## Quick start (development)

```bash
# Backend
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # edit DATABASE_URL, leave JWT_SECRET_KEY blank (auto-generated)
uvicorn app.main:app --reload    # http://localhost:8000

# Frontend (separate terminal)
cd frontend
npm install
cp .env.local.example .env.local
npm run dev                      # http://localhost:3000

# Login: admin / ChangeMe@123 → forced password change on first login
```

## Quick start (production install on Windows)

```cmd
:: 1. On the build machine, produce Setup.exe (one-time)
cd deploy
build.cmd

:: 2. Copy deploy\installer\output\AICameraSurveillance-Setup-1.0.0.exe to target machine
:: 3. Right-click → Run as administrator → Next, Next, Install, Finish
:: 4. Browser opens to the dashboard
```

## Documentation

- [`ENGINEERING_POSTMORTEM.md`](./ENGINEERING_POSTMORTEM.md) — **the realtime live preview journey: cutting RTSP lag from 5 s to ~100 ms across four architectural iterations.** The hardest engineering problem in the project, written up as a postmortem with numbers and code snippets.
- [`deploy/PRODUCTION_GUARANTEES.md`](./deploy/PRODUCTION_GUARANTEES.md) — what's bundled, what's auto-handled, failure modes
- [`deploy/installer/README.md`](./deploy/installer/README.md) — Setup.exe build procedure
- [`DEPLOYMENT.md`](./DEPLOYMENT.md) — full operator runbook
- [`PRODUCTION_AUDIT_PUNCHLIST.md`](./PRODUCTION_AUDIT_PUNCHLIST.md) — 135 verified audit findings, severity-categorised
- [`backend/README.md`](./backend/README.md) — backend design + service responsibilities
- [`frontend/README.md`](./frontend/README.md) — frontend architecture + dashboard layout

## Status

Built as a single-developer project over several iterations. Currently production-ready for LAN-only deployment. Internet-exposed deployment requires the HttpOnly cookie migration (documented as deferred in the audit report).

## License

Source-Available Portfolio License — see [`LICENSE`](./LICENSE). The code is publicly viewable for evaluation and educational purposes; redistribution, commercial use, and derivative products require written permission.
