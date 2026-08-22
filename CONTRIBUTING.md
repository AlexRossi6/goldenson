# Contributing

Thanks for contributing to GoldenSon.

## Development principles

- Keep changes minimal and focused.
- Follow local and privacy requirements in `docs/vision.md`.
- Do not add product features unless explicitly requested.

## Setup

1. Backend setup:

```bash
cd apps/api
uv sync
```

2. Frontend setup:

```bash
cd apps/web
pnpm install --store-dir ~/Library/pnpm/store/v11
```

## Before opening a PR

Run checks locally:

Backend:

```bash
cd apps/api
uv run ruff check .
uv run mypy .
uv run pytest
```

Frontend:

```bash
cd apps/web
pnpm lint
pnpm typecheck
pnpm build
```

## Pull requests

- Explain what changed and why.
- Include any follow-up work that should happen later.
- Keep unrelated refactors out of the same PR.
