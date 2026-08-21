# Product Vision

## Local-First AI Knowledge Workspace

An open-source, local-first personal knowledge workspace where users own their data and can run powerful AI assistants and agents alongside it.

The goal is not simply:

"Notion + chatbot"

The goal is:

> A personal knowledge system that AI can understand, analyze, and safely operate on.

---

## Core experience

The user creates a workspace containing:

- pages
- nested pages
- blocks
- tasks
- files
- eventually databases and relationships

The workspace is indexed locally.

The user can then ask:

- What am I working on?
- What have I learned about X?
- What projects am I neglecting?
- What ideas keep appearing in my notes?
- Which pages overlap?
- What decisions did I make?
- What remains unresolved?

The AI retrieves relevant workspace information and answers with source references.

---

## Agent

The AI agent can use controlled tools to:

- search
- read
- create
- update
- move
- delete
- query structured data
- create files

All modifications require approval in the MVP.

The agent should eventually be capable of multi-step tasks such as:

"Clean up my AI research workspace."

It can:

1. inspect the workspace
2. identify relevant information
3. propose changes
4. wait for approval
5. execute approved changes
6. verify the result
7. report what happened

---

## Local-first

The default configuration should keep:

- workspace data
- files
- database
- embeddings
- inference

on the user's machine.

Cloud storage and cloud AI are optional.

Cloud storage does not imply cloud AI.

Local AI does not imply local storage only.

Users should be able to mix providers.

Example:

Storage: Google Drive
AI: local llama.cpp

or:

Storage: local
AI: local Ollama

or eventually:

Storage: S3
AI: cloud provider

The user explicitly controls these choices.

---

## Architecture

Frontend:

React
TypeScript
Vite
pnpm
TanStack Query
Zustand

Backend:

Python
FastAPI
Pydantic
SQLAlchemy
SQLite
uv

Search:

semantic embeddings
+
keyword search
+
hybrid retrieval

Vector storage:

sqlite-vec

Fallback:

NumPy-based local vector search if sqlite-vec portability becomes problematic.

AI:

LLMProvider abstraction
+
OpenAI-compatible providers

Potential runtimes:

- llama.cpp
- Ollama
- vLLM
- cloud APIs

The application must not depend directly on a particular inference runtime.

---

## Data flow

### Question answering

User
→ query
→ retrieval
→ relevant workspace content
→ context builder
→ LLM
→ answer + sources

### Agent

User
→ request
→ agent
→ tools
→ proposed change set
→ user approval
→ execution
→ verification
→ audit trail

---

## Search

Search should combine:

- semantic similarity
- keyword matching
- metadata
- eventually recency and relationships

Documents are chunked while preserving source page/block/file metadata.

Embeddings are versioned.

Changing the embedding model requires re-indexing.

---

## Long-term direction

The system should eventually understand relationships between:

- projects
- pages
- tasks
- files
- people
- concepts
- databases
- external integrations

This can evolve into a personal knowledge graph.

---

## Roadmap

### Phase 1
Foundation

- workspace
- pages
- editor
- files
- search
- embeddings
- local AI
- assistant
- agent
- approvals

### Phase 2
Knowledge intelligence

- hybrid retrieval
- reranking
- relationships
- knowledge graph
- proactive insights
- better document parsing

### Phase 3
Advanced agents

- multi-step workflows
- background jobs
- scheduled agents
- verification
- richer permissions

### Phase 4
Integrations

- GitHub
- calendar
- email
- cloud storage
- import/export

### Phase 5
Desktop

Windows
macOS
Linux

### Phase 6
Synchronization

Optional multi-device sync.

### Phase 7
Hosted service

Optional cloud offering.

The open-source local version remains independently useful.