# AGENTS.md

## Project Overview

Flowkit is a headless workflow backend service — define, validate, execute, pause/resume, and stream workflows via API. No UI, no vendor lock-in.

**Status: MVP Complete** — all functionality implemented and tested (510 tests).

## Stack

- Python 3.12, FastAPI (factory: `flowkit.api.app:create_app`), Uvicorn
- SQLAlchemy Core (no ORM), asyncpg, aiosqlite (tests)
- Redis, Arq (worker queue)
- Pydantic v2 + pydantic-settings, Alembic, croniter, httpx, sse-starlette
- pytest, pytest-asyncio, pytest-cov, testcontainers (integration tests)
- ruff (py312, line-length=100), mypy (strict + pydantic plugin)
- Package manager: uv

## Commands

```bash
# Install dependencies
uv sync

# Run all tests (uses aiosqlite in-memory, no external deps)
uv run pytest tests/ -v

# Run only unit tests
uv run pytest tests/unit/ -v

# Lint
uv run ruff check src/ tests/

# Type-check
uv run mypy src/

# Run demo workflows
uv run python demo_workflows.py

# Start API server (requires PostgreSQL + Redis)
export FLOWKIT_DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/flowkit"
export FLOWKIT_REDIS_URL="redis://localhost:6379"
uv run uvicorn flowkit.api.app:create_app --factory --reload --host 0.0.0.0 --port 8000

# Run alembic migrations
uv run alembic upgrade head

# Environment variables use FLOWKIT_ prefix (see src/flowkit/config.py)
```

## Architecture

```
API (FastAPI) → Worker (Arq) → Engine → Persistence (PostgreSQL)
                                  ↕
                              Scheduler (DB poller)
                              Streaming (SSE)
```

## Project Structure

```
src/flowkit/
├── api/            # FastAPI routes, schemas, deps
├── definition/     # DSL schema, validator, loader
├── engine/         # Graph, dispatcher, executor, commands
├── nodes/          # 7 node types + base + registry
├── persistence/    # Models, repos, database
├── runtime/        # Variable pool, state machine
├── scheduler/      # DB-polling cron scheduler
├── streaming/      # SSE event emitter
├── triggers/       # Webhook handler
├── worker/         # Arq task runner
└── config.py       # Pydantic settings (FLOWKIT_ prefix)
```

## Node Types

start, end, http, code, if_else, loop, human_input

## Conventions

- **SQLAlchemy Core only** — no ORM, explicit SQL
- **Keyword-only repo args** — `repo.method(conn, *, key=value)` pattern
- **Separate API models** — API schemas ≠ internal engine models
- **Tests**: aiosqlite in-memory, `asyncio_mode=auto`, `testpaths=tests`, `pythonpath=src`
- **Linting**: ruff (py312, line-length=100), mypy strict with pydantic plugin
- **Package manager**: uv

## Principles

- Keep workflow engine independent from API delivery concerns
- Keep workflow definition independent from runtime execution state
- Persist enough runtime state to support pause/resume and debugging
- Prefer small, composable node abstractions over coupled service objects
- Do not over-expand node catalog before core runtime is stable
- Never suppress type errors
- Separate API models from internal engine models

## Key Specs

- `specs/architecture.md` — System architecture, service topology, module responsibilities
- `specs/dsl-v1.md` — Workflow DSL v1 schema, node types, 32 validation rules
- `specs/persistence.md` — Database schema, 7 tables, index strategy

## Key Decisions

See `DECISIONS.md` for all architectural decisions (DEC-001 through DEC-010).

## Notes
