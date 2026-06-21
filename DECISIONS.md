# DECISIONS

## Implemented

### DEC-001 — Product boundary

- **Status**: Implemented
- **Decision**: Build Flowkit as a headless workflow backend service, not a full product suite.
- **Why**: Keeps scope focused on orchestration, execution, scheduling, and state management.
- **Outcome**: API-only service with no UI. All interactions via REST + SSE + WebSocket.

### DEC-002 — Modular architecture

- **Status**: Implemented
- **Decision**: Modular backend split into definition, engine, runtime, persistence, triggers, scheduler, streaming, plugins, and API layers.
- **Why**: Preserves separation between workflow semantics and delivery concerns.
- **Outcome**: 12 independent packages under `src/flowkit/` — engine has zero import dependencies on API layer.

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
- **Outcome**: `src/flowkit/scheduler/poller.py` — configurable poll interval, croniter for cron parsing, `asyncio.Event` for graceful shutdown.

### DEC-006 — Event streaming: SSE + WebSocket

- **Status**: Implemented
- **Decision**: Server-Sent Events for server→client streaming, WebSocket for bidirectional communication.
- **Why**: SSE is HTTP-native, works through proxies, built-in reconnection. WebSocket adds client→server messaging (ping, cancel ack, resume ack).
- **Outcome**: `src/flowkit/streaming/` with emitter + SSE endpoint + WebSocket connection manager. 11 event types.

### DEC-007 — DSL format: JSON

- **Status**: Implemented
- **Decision**: JSON as canonical DSL serialization format.
- **Why**: Native to Python/JS. JSONB storage in PostgreSQL. Schema validation via Pydantic.
- **Outcome**: Workflow definitions stored as JSONB. API accepts/returns JSON. 32 validation rules. 10 node types.

### DEC-008 — SQLAlchemy Core (no ORM)

- **Status**: Implemented
- **Decision**: Use SQLAlchemy Core table definitions, not ORM mapped classes.
- **Why**: Explicit SQL control, better async compatibility, no identity map overhead.
- **Outcome**: All repos use explicit `insert()`, `select()`, `update()` statements across 8 tables.

### DEC-009 — Keyword-only repo arguments

- **Status**: Implemented
- **Decision**: All repository methods use keyword-only arguments after `*` separator.
- **Why**: Prevents positional argument bugs, self-documenting call sites.
- **Outcome**: `repo.create(conn, *, workflow_id=..., status=...)` across all 8 repos.

### DEC-010 — Testing with aiosqlite

- **Status**: Implemented
- **Decision**: Use aiosqlite (in-memory SQLite) for tests instead of requiring PostgreSQL.
- **Why**: Zero infrastructure requirement for tests. Fast, deterministic, portable.
- **Outcome**: 609 tests pass in ~3.4s. Integration tests exercise full engine lifecycle in-process.

### DEC-011 — Structured error hierarchy

- **Status**: Implemented
- **Decision**: All errors inherit from a single `FlowkitError` base with machine-readable `code` and optional `details` dict.
- **Why**: Consistent API error responses, enables dead-letter classification, avoids string matching on exceptions.
- **Outcome**: 7 error classes (`FlowkitError` + `NotFoundError`, `ValidationError`, `ExecutionError`, `TimeoutError`, `WebhookError`, `StateTransitionError`). Global exception handler with status code mapping on all routes.

### DEC-012 — Dead-letter queue

- **Status**: Implemented
- **Decision**: Unrecoverable node failures are persisted to a `dead_letter_queue` table rather than lost or only logged.
- **Why**: Enables operational recovery — inspect, retry, or resolve failed executions without digging through logs.
- **Outcome**: `dead_letter_queue` table (8th table), `DeadLetterRepo` with `create`/`retry`/`resolve` operations, status lifecycle: `pending → retrying → resolved | failed`.

### DEC-013 — API authentication

- **Status**: Implemented
- **Decision**: Simple `X-API-Key` header-based auth via Starlette middleware, configurable and disabled by default.
- **Why**: Sufficient for internal/trusted networks in v1. No OAuth/JWT complexity yet. Timing-safe comparison via `secrets.compare_digest`.
- **Outcome**: `ApiKeyMiddleware` in `src/flowkit/api/middleware.py`. Controlled by `FLOWKIT_API_KEY` env var (empty = disabled). `/health`, `/docs`, etc. are public.

### DEC-014 — Plugin model

- **Status**: Implemented
- **Decision**: Custom node types via a `PluginNodeExecutor` ABC with dict-based I/O, bridged to internal `NodeExecutor` via `PluginNodeAdapter`.
- **Why**: Decouples plugins from internal types. dict-based interface avoids tight coupling. `importlib.metadata` entry-point discovery enables pip-installable plugins.
- **Outcome**: `src/flowkit/plugins/` — `PluginNodeExecutor` ABC, `PluginRegistry` singleton, `PluginNodeAdapter` bridge, `load_plugins_from_entry_points()` discovery. Entry point group: `flowkit.plugins`.

### DEC-015 — Parallel execution

- **Status**: Implemented
- **Decision**: Structural parallelism via `asyncio.gather()` when multiple nodes are ready, plus a `parallel` node type for collection fan-out.
- **Why**: `asyncio.gather()` is simple and correct for I/O-bound node execution. Fail-fast semantics: first FAILED aborts remaining.
- **Outcome**: Engine executor supports concurrent dispatch. `ParallelExecutor` with `max_concurrency` control (default 10). Diamond workflow tests pass.

### DEC-016 — Sub-workflow composition

- **Status**: Implemented
- **Decision**: Nested workflow execution via in-process delegation to `WorkflowExecutor`, with status mapping between child and parent.
- **Why**: Enables workflow-as-node composition without spawning separate runs or workers. Late import pattern avoids circular dependency.
- **Outcome**: `SubWorkflowExecutor` validates child definition, resolves `input_mapping`, executes synchronously. Child PAUSED→parent WAITING, child FAILED→parent FAILED.

### DEC-017 — WebSocket streaming

- **Status**: Implemented
- **Decision**: Add WebSocket endpoint at `/ws/runs/{run_id}` for bidirectional event streaming alongside existing SSE.
- **Why**: SSE is unidirectional. WebSocket enables client→server messaging (ping/pong, cancel acknowledgement) without separate HTTP calls.
- **Outcome**: `ConnectionManager` in `src/flowkit/streaming/ws.py` — per-run_id connection tracking, broadcast with dead-connection pruning.

## Superseded

None yet.
