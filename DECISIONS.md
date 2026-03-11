# DECISIONS

## Implemented

### DEC-001 — Product boundary

- **Status**: Implemented
- **Decision**: Build Flowkit as a headless workflow backend service, not a full product suite.
- **Why**: Keeps scope focused on orchestration, execution, scheduling, and state management.
- **Outcome**: API-only service with no UI. All interactions via REST + SSE.

### DEC-002 — Modular architecture

- **Status**: Implemented
- **Decision**: Modular backend split into definition, engine, runtime, persistence, triggers, scheduler, streaming, and API layers.
- **Why**: Preserves separation between workflow semantics and delivery concerns.
- **Outcome**: 10 independent packages under `src/flowkit/` — engine has zero import dependencies on API layer.

### DEC-003 — Technology stack

- **Status**: Implemented
- **Decision**: Python 3.12 + FastAPI + PostgreSQL (asyncpg) + Redis.
- **Why**: Fast iteration, strong async ecosystem, excellent typing support.
- **Outcome**: Full async stack with SQLAlchemy Core (no ORM), Pydantic v2 for all schemas.

### DEC-004 — Worker framework: Arq

- **Status**: Implemented
- **Decision**: Use Arq (Redis-backed async task queue) for background node execution.
- **Why**: Lightweight, native async, Redis-backed. Avoids Celery complexity for our workload.
- **Outcome**: `src/flowkit/worker/` with task definitions and settings. Workers are stateless, scale horizontally.

### DEC-005 — Scheduler: DB-driven polling

- **Status**: Implemented
- **Decision**: DB-driven polling loop for cron triggers, not APScheduler or Celery Beat.
- **Why**: Single source of truth in PostgreSQL. `FOR UPDATE SKIP LOCKED` prevents double-fires.
- **Outcome**: `src/flowkit/scheduler/poller.py` — configurable poll interval, croniter for cron parsing.

### DEC-006 — Event streaming: SSE

- **Status**: Implemented
- **Decision**: Server-Sent Events for real-time run/node event streaming.
- **Why**: Unidirectional (server→client), HTTP-native, works through proxies, reconnection built into spec.
- **Outcome**: `src/flowkit/streaming/` with emitter + SSE endpoint. 11 event types.

### DEC-007 — DSL format: JSON

- **Status**: Implemented
- **Decision**: JSON as canonical DSL serialization format.
- **Why**: Native to Python/JS. JSONB storage in PostgreSQL. Schema validation via Pydantic.
- **Outcome**: Workflow definitions stored as JSONB. API accepts/returns JSON. 32 validation rules.

### DEC-008 — SQLAlchemy Core (no ORM)

- **Status**: Implemented
- **Decision**: Use SQLAlchemy Core table definitions, not ORM mapped classes.
- **Why**: Explicit SQL control, better async compatibility, no identity map overhead.
- **Outcome**: All repos use explicit `insert()`, `select()`, `update()` statements.

### DEC-009 — Keyword-only repo arguments

- **Status**: Implemented
- **Decision**: All repository methods use keyword-only arguments after `*` separator.
- **Why**: Prevents positional argument bugs, self-documenting call sites.
- **Outcome**: `repo.create(conn, *, workflow_id=..., status=...)` across all 7 repos.

### DEC-010 — Testing with aiosqlite

- **Status**: Implemented
- **Decision**: Use aiosqlite (in-memory SQLite) for tests instead of requiring PostgreSQL.
- **Why**: Zero infrastructure requirement for tests. Fast, deterministic, portable.
- **Outcome**: 510 tests pass in ~2s. Integration tests exercise full engine lifecycle in-process.

## Superseded

None yet.
