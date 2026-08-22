# GoldenSon

Monorepo foundation for a local AI knowledge workspace.

This repository currently contains only development and tooling setup.
No product features are implemented yet.

## Repository layout

- `apps/api` - FastAPI backend (Python 3.12+, uv, Ruff, mypy, pytest)
- `apps/web` - React + TypeScript + Vite frontend (pnpm, TanStack Query, Zustand)
- `docs` - product vision and design documents

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- Node.js 20+
- [pnpm](https://pnpm.io/)

## Run backend

```bash
cd apps/api
uv sync
uv run uvicorn goldenson_api.main:app --app-dir src --reload --host 127.0.0.1 --port 8000
```

Health endpoint:

- `GET http://127.0.0.1:8000/api/health`

## Run frontend

```bash
cd apps/web
pnpm install --store-dir ~/Library/pnpm/store/v11
pnpm dev
```

The Vite dev server proxies `/api/*` requests to `http://127.0.0.1:8000`.

## Verify frontend to backend

1. Start backend and frontend.
2. Open the frontend URL shown by Vite.
3. Click **Check backend health**.
4. Confirm the status card shows `ok` from `/api/health`.

## Backend checks

```bash
cd apps/api
uv run ruff check .
uv run ruff format --check .
uv run mypy .
uv run pytest
```

## Migrations and seed data

```bash
cd apps/api
uv run alembic upgrade head
uv run python -m goldenson_api.scripts.seed
```

## Frontend checks

```bash
cd apps/web
pnpm lint
pnpm typecheck
pnpm build
```

## CI

A GitHub Actions workflow is available at `.github/workflows/ci.yml` and runs backend and frontend checks on pull requests and pushes to `main`.
