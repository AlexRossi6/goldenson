# GoldenSon Web

React and TypeScript frontend for the GoldenSon local AI knowledge workspace.

The application provides the page tree, same-surface block editor, local file UI,
workspace search and source navigation, indexing health and recovery,
evidence-based related content with matching passages, Ollama model management,
streaming grounded assistant answers with navigable page/block sources, and approval
flow for agent changes. Server state uses
TanStack Query; lightweight selection and layout state uses Zustand.

## Development

Start the API first, then run:

```bash
pnpm install
pnpm dev
```

Vite proxies `/api` to `http://127.0.0.1:8000`.

## Checks

```bash
pnpm lint
pnpm typecheck
pnpm test
pnpm build
```
