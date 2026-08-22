# Copilot Instructions

## Project

This repository contains an open-source, fully local AI knowledge workspace.

The product vision is documented in:

docs/vision.md

Do not treat future roadmap features as requirements for the current task.

Implement only the scope explicitly requested by the current task.

---

## Core principles

### Fully local by default

GoldenSon's core functionality must work entirely on the user's device without an internet connection, cloud account, external API, or external service.

Workspace data, files, database contents, search indexes, embeddings, AI conversations, and local AI inference must remain on the user's machine by default.

External services may be supported as explicit, opt-in integrations in the future, but they must never be required for core functionality.

Never silently send workspace content to an external service.

Never silently fall back from a local AI provider to a cloud provider.

Do not introduce telemetry in the MVP.

### Privacy

Treat workspace content as private user data.

Never expose:

- API keys
- credentials
- secrets
- unrestricted filesystem access
- unrestricted SQL execution

to the LLM or frontend.

### Simplicity

Do not over-engineer.

Prefer the smallest implementation that satisfies the current requirement.

Do not implement future roadmap features unless explicitly requested.

Do not add dependencies without a concrete reason.

Do not rewrite unrelated code.

---

# Technology stack

## Backend

- Python 3.12+
- FastAPI
- Pydantic
- Pydantic Settings
- SQLAlchemy
- Alembic
- SQLite
- aiosqlite
- HTTPX

Development tooling:

- uv
- Ruff
- mypy
- pytest
- pytest-asyncio

## Frontend

- React
- TypeScript
- Vite
- pnpm
- TanStack Query
- Zustand

Use TanStack Query for server state.

Use Zustand for lightweight client/UI state.

Do not introduce another global state-management solution without a strong reason.

---

# Dependency management

## Python

Use uv exclusively.

Use:

uv sync

uv add <package>

uv add --dev <package>

uv run <command>

Do not use:

- pip
- Poetry
- Pipenv
- manually maintained requirements.txt

The Python source of truth is:

pyproject.toml
uv.lock

Do not manually edit uv.lock.

## Frontend

Use pnpm exclusively.

The source of truth is:

package.json
pnpm-lock.yaml

Do not use npm as the project's package manager.

---

# Code quality

Python must use:

- type hints
- Pydantic validation
- Ruff
- mypy
- pytest

Avoid unnecessary `Any`.

Do not disable type checking globally.

Run:

uv run ruff check .
uv run ruff format .
uv run mypy .
uv run pytest

Frontend should have appropriate linting, type checking, tests, and production builds.

---

# Architecture boundaries

Keep these concerns separate:

- API
- services/business logic
- database/repositories
- storage
- search/retrieval
- embeddings
- inference
- agent
- frontend

API routes should remain thin.

Prefer:

API route
→ service
→ repository/provider
→ underlying system

Do not put substantial business logic in route handlers.

---

# AI architecture

The application must not directly depend on a specific inference runtime.

Use an abstraction such as:

LLMProvider

The core application must support local inference without requiring an external service.

Use an abstraction such as LLMProvider.

Initial local inference runtimes may include:

llama.cpp
Ollama
other local OpenAI-compatible runtimes

vLLM may be supported later as an optional local inference provider, but must not be a required application dependency.

Cloud LLM providers may eventually be implemented as explicit opt-in integrations.

Never silently fall back from local inference to cloud inference.

Do not install models automatically as part of normal application setup.

Do not make vLLM a required dependency.

Do not install models automatically as part of normal application setup.

The user explicitly configures external/cloud AI providers.

---

# Storage

Use a StorageProvider abstraction.

The initial implementation is local filesystem storage.

Do not allow the agent unrestricted filesystem access.

All agent file operations must go through the storage abstraction.

---

# Search

Search should support semantic retrieval.

The MVP vector storage implementation is:

sqlite-vec

Use the existing SQLite database rather than introducing a separate vector database.

If sqlite-vec creates serious cross-platform loading problems, use a simple fallback based on stored vectors and NumPy cosine similarity rather than introducing a networked vector database.

Do not add PostgreSQL or another external database just for vector search in the MVP.

---

# Embeddings

Embeddings must be versioned.

Every stored embedding must record at least:

- embedding model identifier
- embedding model version/configuration
- vector dimensions
- source content/chunk identifier

Vectors from different embedding models or incompatible dimensions must never be treated as interchangeable.

Changing the configured embedding model must trigger a required re-index.

Never silently mix vectors from different embedding models.

---

# Chunking

Preserve block-level source information.

Chunks should retain metadata identifying their source page/block/file.

Use reasonable overlap between adjacent chunks.

Do not create an unnecessarily complicated chunking system for the MVP.

---

# AI context

Never send the entire workspace to the LLM by default.

Use:

user request
→ retrieval
→ relevant content
→ context construction
→ LLM

Retrieved content must preserve source references so responses can eventually cite the originating pages/files.

---

# Agent

The assistant and agent are separate concepts.

Assistant:

- retrieves information
- answers questions
- analyzes workspace

Agent:

- uses tools
- modifies workspace
- performs multi-step operations

All agent capabilities must be explicit tools.

Initial tools:

READ:

- search_workspace
- get_page
- list_pages
- query_database
- read_file

WRITE:

- create_page
- update_page
- create_task
- move_page
- create_file

DESTRUCTIVE:

- delete_page

---

# Agent tool security

Never allow the LLM to directly:

- execute shell commands
- execute arbitrary Python/code
- execute arbitrary SQL
- access arbitrary filesystem paths
- make arbitrary HTTP requests
- access credentials/secrets

All tool arguments must be validated with Pydantic.

All filesystem operations must be restricted to configured workspace storage.

Database queries must use structured query models rather than model-generated raw SQL.

---

# Agent permissions

Every tool must declare:

- permission level
- input schema
- side effects
- approval requirement

Permission levels:

READ
WRITE
DESTRUCTIVE
EXTERNAL

All WRITE, DESTRUCTIVE, and EXTERNAL operations require user approval in the MVP.

READ operations do not require approval.

---

# Agent circuit breakers

Every agent run must have explicit limits.

At minimum:

- maximum tool calls per run
- maximum execution duration
- maximum individual tool execution duration

These limits must be configurable.

If a limit is reached:

1. stop the agent
2. preserve the audit trail
3. report why execution stopped
4. do not continue automatically

The agent must never run indefinitely.

Avoid implementing recursive or unbounded agent loops.

---

# Agent approvals

Group proposed modifications into change sets.

Do not require approval for every individual low-level read.

For modifications, show:

- intended action
- target
- relevant arguments
- expected effect

Where practical, show diffs for content changes.

Do not execute WRITE or DESTRUCTIVE operations before approval.

---

# Agent audit trail

Record agent runs and tool calls.

The audit trail may include:

- run ID
- timestamp
- user request
- tool name
- sanitized arguments
- result summary
- approval state
- user decision
- errors

IMPORTANT:

Never store secrets, credentials, API keys, authorization headers, tokens, or sensitive authentication material in the audit trail.

Tool arguments and results must be sanitized before persistence.

Do not log raw provider responses if they may contain secrets.

---

# Streaming

Use Server-Sent Events (SSE) for MVP AI response streaming.

Do not introduce WebSockets unless a concrete MVP requirement requires bidirectional communication.

The frontend should support:

- streaming text
- loading state
- errors
- completion
- cancellation where practical

---

# Concurrency

Use optimistic concurrency for mutable workspace entities.

At minimum, Page and Block updates should use `updated_at` or an equivalent version mechanism.

An update should fail safely if the entity has changed since it was read.

Never silently overwrite a newer user change.

Return a conflict that the frontend can handle.

This will make future synchronization substantially easier.

---

# Testing

Critical behavior must have automated tests.

Especially test:

- agent permissions
- approval requirements
- rejected changes
- destructive operations
- tool argument validation
- filesystem boundaries
- SQL/query boundaries
- provider failures
- embedding version mismatches
- concurrency conflicts
- indexing failures

Never consider a feature complete if critical security behavior is untested.

---

# Development workflow

Before modifying code:

1. Inspect the repository.
2. Read relevant existing code.
3. Identify existing abstractions.
4. Determine the smallest implementation needed.
5. Implement only the requested task.
6. Add/update tests.
7. Run relevant checks.
8. Update documentation if behavior changed.

Do not implement future roadmap items merely because they are documented in `docs/vision.md`.

If an architectural decision is ambiguous and materially affects the implementation, stop and explain the ambiguity rather than inventing a large architecture.

---

# Never do these things without explicit instruction

- add cloud AI as a fallback
- add telemetry
- add authentication/accounts
- add SaaS/billing
- add PostgreSQL
- add a vector database server
- add vLLM as an application dependency
- add arbitrary shell execution
- add arbitrary SQL execution
- add unrestricted filesystem access
- add external integrations
- build the desktop application
- build synchronization
- implement the entire roadmap
- rewrite unrelated parts of the repository