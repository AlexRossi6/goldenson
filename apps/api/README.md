# GoldenSon API

FastAPI backend application for GoldenSon.

## Development

```bash
uv sync
uv run uvicorn goldenson_api.main:app --app-dir src --reload
```

The API health endpoint is available at `/api/health`.

## Database

Run migrations:

```bash
uv run alembic upgrade head
```

Create a new migration after model changes:

```bash
uv run alembic revision --autogenerate -m "describe change"
```

Seed development data:

```bash
uv run python -m goldenson_api.scripts.seed
```
