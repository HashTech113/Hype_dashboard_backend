# AI Attendance — Frontend

Next.js 15 (App Router) + TypeScript + Tailwind CSS + ShadCN UI.

Connects to the FastAPI backend at `NEXT_PUBLIC_API_URL`.

## Quick start

```bash
cd frontend
npm install
cp .env.local.example .env.local      # or set NEXT_PUBLIC_API_URL manually
npm run dev                            # http://localhost:3000
```

Make sure the backend is running at `http://localhost:8000` (or update `.env.local`).

## Project layout

```
frontend/
├── app/                              # Next.js App Router
│   ├── (auth)/login/                 # public — login page
│   ├── (dashboard)/                  # protected shell (sidebar + topbar)
│   │   ├── layout.tsx                # auth gate + chrome
│   │   └── dashboard/page.tsx        # live stats + timeline
│   ├── layout.tsx                    # root layout (providers)
│   ├── globals.css                   # Tailwind + design tokens
│   ├── page.tsx                      # redirects to /dashboard
│   └── not-found.tsx
│
├── components/
│   ├── ui/                           # ShadCN primitives (button, card, input, …)
│   ├── layout/                       # sidebar, topbar, theme toggle, user menu
│   ├── auth/                         # login form
│   ├── dashboard/                    # stats grid, timeline feed
│   ├── shared/                       # reusable (stat-card)
│   └── providers.tsx                 # Theme + React Query + Auth + Toaster
│
├── lib/
│   ├── api/                          # client + per-module fetchers (auth, dashboard)
│   ├── auth/                         # session cookie helpers + React context
│   ├── hooks/                        # TanStack Query hooks
│   ├── types/                        # TS mirrors of backend schemas
│   ├── query-client.ts               # QueryClient factory
│   └── utils.ts                      # cn(), formatters
│
├── middleware.ts                     # route guard (redirects /login for unauth)
├── tailwind.config.ts
├── tsconfig.json
├── components.json                   # ShadCN config
└── package.json
```

## Architecture notes

- **Auth**: JWT stored in an `aa_token` cookie (not httpOnly because the SPA reads it to inject `Authorization: Bearer …`). Middleware checks the cookie on every request; unauthenticated hits get redirected to `/login`. The `AuthProvider` calls `/api/v1/auth/me` to resolve the current admin.
- **HTTP**: Axios with a single instance (`lib/api/client.ts`) — baseURL from `NEXT_PUBLIC_API_URL`, request interceptor injects the JWT, response interceptor maps errors to `ApiError` and clears the token on 401.
- **Data fetching**: TanStack Query on top of Axios. Dashboard polls every 15 s (stats) / 10 s (timeline).
- **Theming**: `next-themes` with CSS variables. Dark mode via `class` strategy.
- **Forms**: `react-hook-form` + `zod` resolver. Strict validation.
- **Toasts**: `sonner`.
- **Icons**: `lucide-react`.
- **Charts**: `recharts` (installed; used in future modules).

## Feature pages

The following routes are reserved in the sidebar but will be built in subsequent prompts:

- `/employees` — employee CRUD
- `/training` — face training (upload + live capture)
- `/cameras` — camera CRUD + health + probe
- `/attendance` — events, sessions, manual correction
- `/snapshots` — event snapshots gallery
- `/reports` — Excel report downloads
- `/settings` — runtime-tunable settings

Each uses the same shell; feature components live under `components/<feature>/`.

## Scripts

```
npm run dev          # dev server with Turbopack
npm run build        # production build
npm run start        # serve production build
npm run lint         # next lint
npm run type-check   # tsc --noEmit
```
