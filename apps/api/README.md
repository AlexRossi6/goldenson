# GoldenSon API

FastAPI backend application for GoldenSon.

## Development

```bash
uv sync
uv run uvicorn goldenson_api.main:app --app-dir src --reload
```

The API health endpoint is available at `/api/health`.
