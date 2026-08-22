# GoldenSon API

FastAPI backend for GoldenSon's local workspace, retrieval, managed Ollama, and
approval-gated agent.

## Development

```bash
uv sync
uv run alembic upgrade head
uv run uvicorn goldenson_api.main:app --app-dir src --reload
```

The `--app-dir src` option is required when the package is not installed in editable
mode. The API health endpoint is available at `/api/health`; OpenAPI documentation
is available at `/docs`.

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

## Checks

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy .
uv run pytest
```

Agent runs and tool calls are persisted in SQLite. READ tools execute directly;
WRITE and DESTRUCTIVE tools require explicit approval and resume the persisted run
after the decision. Tool inputs are validated and agent access remains restricted
to workspace-scoped services.
