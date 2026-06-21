# Flowkit Architecture Spec

> Status: **v2** · Last updated: 2026-06-21

## 1. Overview

Flowkit is a headless workflow backend that provides workflow definition, orchestration, execution, scheduling, trigger handling, runtime state persistence, and event streaming. It exposes a REST API + WebSocket consumed by external systems — no built-in UI.

### Design Principles

1. **Engine independence** — the workflow engine knows nothing about HTTP, API serialization, or delivery transport.
2. **Definition ≠ Runtime** — workflow definitions are immutable snapshots; runtime state is a separate, mutable concern.
3. **Persistence-first** — every state transition is persisted before it is acknowledged. No in-memory-only correctness.
4. **Composable nodes** — nodes are small, self-contained units with a uniform interface. The catalog grows incrementally.
5. **Plugin extensibility** — custom node types can be registered via a stable plugin interface with entry-point discovery.

---

## 2. Service Topology

```
┌──────────────┐     ┌──────────────┐     ┌──────────────────┐
│  API Service │     │   Worker     │     │   Scheduler      │
│  (FastAPI)   │     │  Service     │     │   Service        │
│              │     │  (Arq)       │     │  (DB-polling)    │
└──────┬───────┘     └──────┬───────┘     └───────┬──────────┘
       │                    │                     │
       │         ┌──────────┴──────────┐          │
       │         │                     │          │
       ▼         ▼                     ▼          ▼
  ┌─────────┐  ┌─────────┐      ┌──────────┐
  │PostgreSQL│  │  Redis  │      │PostgreSQL│
  │ (state)  │  │ (queue) │      │(schedule)│
  └─────────┘  └─────────┘      └──────────┘
```

### 2.1 API Service

- **Framework**: FastAPI (async)
- **Responsibilities**: REST endpoints, request validation, SSE streaming, WebSocket streaming, webhook ingestion, API key auth
- **Does NOT**: Execute nodes, run cron jobs, maintain in-memory workflow state
- **Scaling**: Horizontal (stateless). Multiple replicas behind a load balancer.

### 2.2 Worker Service

- **Framework**: Arq (Redis-backed async task queue)
- **Responsibilities**: Execute individual node tasks, manage node-level retries, emit node completion events
- **Lifecycle**: Picks tasks from Redis queue → loads node context from DB → executes → writes result to DB → enqueues next-ready nodes. Supports `on_startup`/`on_shutdown` lifecycle hooks for plugin loading.
- **Scaling**: Horizontal. Each worker is stateless; coordination is via DB + Redis.

### 2.3 Scheduler Service

- **Framework**: Custom DB-polling loop (single lightweight process)
- **Responsibilities**: Poll `schedule_triggers` table for due triggers → enqueue workflow runs via the same path as API-initiated runs
- **Polling interval**: Configurable, default 15s
- **Graceful shutdown**: via `asyncio.Event` — polls terminate cleanly on SIGTERM.
- **Scaling**: Single-active with leader election (advisory lock). Multiple instances for HA, only one polls at a time.

---

## 3. Module Architecture

```
flowkit/
├── definition/          # Workflow DSL, schema, validation
│   ├── schema.py        # Pydantic models for DSL v1 (10 node types)
│   ├── validator.py     # Graph validation (cycles, reachability, types)
│   └── loader.py        # Parse & instantiate workflow definitions
│
├── engine/              # Core runtime engine
│   ├── graph.py         # In-memory graph representation for a run
│   ├── dispatcher.py    # Determines next-ready nodes, enqueues work
│   ├── executor.py      # Node execution orchestration (parallel + sequential)
│   └── commands.py      # Pause / resume / cancel command handling
│
├── nodes/               # Node type implementations
│   ├── base.py          # Abstract NodeExecutor interface
│   ├── start.py
│   ├── end.py
│   ├── http.py
│   ├── code.py
│   ├── if_else.py
│   ├── loop.py
│   ├── human_input.py
│   ├── parallel.py      # Fan-out parallel execution
│   └── sub_workflow.py  # Nested workflow composition
│
├── plugins/             # Plugin model for custom node types
│   ├── base.py          # PluginNodeExecutor ABC + PluginResult
│   ├── adapter.py       # PluginNodeAdapter (bridges plugin → internal NodeExecutor)
│   └── loader.py        # PluginRegistry + entry-point discovery
│
├── runtime/             # Runtime state management
│   ├── variable_pool.py # Scoped variable read/write
│   └── state.py         # Run & node state machines
│
├── persistence/         # Database repositories
│   ├── models.py        # SQLAlchemy Core table definitions (8 tables)
│   ├── repos.py         # 8 async repos (Workflow, Version, Run, NodeRun, Event,
│   │                    #   WebhookTrigger, ScheduleTrigger, DeadLetter)
│   └── database.py      # Connection management
│
├── triggers/            # Trigger subsystem
│   └── webhook.py       # Webhook trigger handler
│
├── streaming/           # Event streaming
│   ├── emitter.py       # Publish events to DB + Redis pub/sub
│   ├── sse.py           # SSE transport
│   └── ws.py            # WebSocket connection manager
│
├── api/                 # FastAPI application
│   ├── app.py           # Application factory
│   ├── deps.py          # Dependency injection
│   ├── middleware.py     # API key auth middleware
│   ├── routes/
│   │   ├── workflows.py
│   │   ├── runs.py
│   │   └── triggers.py
│   └── schemas/         # API request/response models (NOT engine models)
│       ├── workflows.py
│       ├── runs.py
│       ├── triggers.py
│       └── errors.py    # Structured error responses
│
├── worker/              # Arq worker entry point
│   ├── tasks.py         # Task definitions
│   └── settings.py      # Arq worker settings + lifecycle hooks
│
├── scheduler/           # Scheduler service entry point
│   └── poller.py        # DB-polling loop with graceful shutdown
│
├── errors.py            # Structured error hierarchy
└── config.py            # Centralized configuration
```

### 3.1 Module Boundaries & Dependencies

```
api  ──→  engine  ──→  runtime
 │          │            │
 │          ▼            │
 │        nodes          │
 │          │            │
 │          ├── plugins  │
 │          │            │
 ▼          ▼            ▼
      persistence  ◄────┘
          │
          ▼
    streaming (events)
```

**Rules:**
- `definition` is a pure library — no I/O, no DB, no network.
- `engine` depends on `definition`, `runtime`, `persistence`. Never on `api`.
- `nodes` depend on `runtime` (variable pool). Never on `engine` or `api`.
- `plugins` depends only on `definition` and `runtime` via the adapter. Entry points are external packages.
- `api` depends on `engine` and `persistence`. Never imports from `nodes` directly.
- `persistence` is the only module that talks to PostgreSQL.
- `streaming` manages SSE + WebSocket transports. Event emission goes through DB + Redis pub/sub.
- `worker` and `scheduler` are entry points, not libraries. Nothing imports from them.
- `errors.py` is a zero-dependency leaf — importable from anywhere.

---

## 4. Core Abstractions

### 4.1 WorkflowDefinition

Immutable, versioned snapshot of a workflow's structure. Stored as a JSONB document (DSL v1). See `specs/dsl-v1.md`.

### 4.2 Graph

Ephemeral in-memory representation built from a WorkflowDefinition at run start. Provides adjacency queries: `successors(node_id)`, `predecessors(node_id)`, `ready_nodes(completed_set)`.

### 4.3 NodeExecutor

```python
class NodeExecutor(ABC):
    node_type: str

    async def execute(self, context: NodeContext) -> NodeResult:
        """Execute the node. Returns output data + next-edge selector."""
        ...
```

Every node type implements this interface. `NodeContext` provides:
- `node_def`: The node's static configuration from the DSL
- `variable_pool`: Scoped read/write access to the variable pool
- `run_id`, `node_run_id`: Identifiers

`NodeResult` contains:
- `status`: `completed` | `failed` | `waiting`
- `outputs`: Dict of output values
- `next_handle`: Which outgoing edge(s) to activate (for branching nodes)
- `error`: Optional error detail string

### 4.4 PluginNodeExecutor

External plugin interface — decoupled from internal types:

```python
class PluginNodeExecutor(ABC):
    async def execute(
        self,
        config: dict[str, Any],
        inputs: dict[str, Any],
        context: dict[str, Any],
    ) -> PluginResult:
        ...
```

`PluginNodeAdapter` bridges this interface to `NodeExecutor` — handles config validation, variable resolution, and status mapping. Discovered via `importlib.metadata` entry points in the `flowkit.plugins` group.

### 4.5 VariablePool

Scoped key-value store for a single workflow run. Two scopes:
- **workflow scope**: Readable/writable by any node in the run.
- **node scope**: Private to a single node execution (inputs/outputs).

Backed by a JSONB column on the `workflow_runs` table. Loaded into memory during node execution, flushed to DB after each node completes.

### 4.6 Dispatcher

The Dispatcher determines which nodes are ready to execute after a node completes:

```
on_node_complete(run_id, node_id, result):
    1. Record node result in DB
    2. Resolve activated edges from result.next_handle
    3. For each target node of activated edges:
       a. Check if ALL incoming edges are satisfied (join semantics)
       b. If ready → enqueue node task via Arq
    4. If no nodes are ready AND no nodes are running → run is complete
```

### 4.7 Parallel Execution

When multiple nodes are ready simultaneously, the executor uses `asyncio.gather()` for concurrent dispatch. The `parallel` node type fans out over a collection, creating one execution branch per item. Fail-fast semantics: first `FAILED` node aborts remaining; `WAITING` (human_input) nodes defer until the batch completes.

### 4.8 State Machines

**WorkflowRun states:**
```
pending → running → completed
                  → failed
                  → cancelled
running → paused → running (resume)
                 → cancelled
```

**NodeRun states:**
```
pending → running → completed
                  → failed
                  → skipped
running → waiting → running (resume, for human_input)
```

All state transitions are persisted atomically with their side effects (variable updates, event emission).

---

## 5. Key Data Flows

### 5.1 Run a Workflow (API-initiated)

```
1. Client POST /workflows/{id}/run {inputs}
2. API validates inputs against workflow definition
3. API creates workflow_run record (status=pending)
4. API creates node_run records for all nodes (status=pending)
5. API snapshots initial variable pool (workflow inputs)
6. API enqueues start node via Arq → returns run_id
7. Worker picks up start node task
8. Worker loads node context (config, variables, inputs)
9. Worker executes start node → NodeResult
10. Worker calls Dispatcher.on_node_complete()
11. Dispatcher writes result, finds next-ready nodes, enqueues them
12. Repeat 7-11 until end node completes or error
13. Run status → completed/failed
14. Events emitted at each step via DB + Redis pub/sub → SSE / WebSocket
```

### 5.2 Pause / Resume

```
Pause:
1. Client POST /runs/{id}/pause
2. API sets run status → paused
3. API sends pause command to Dispatcher via Redis command channel
4. Dispatcher stops enqueuing new nodes
5. Currently-running nodes finish (graceful) — their results are recorded
6. No new nodes are started

Resume:
1. Client POST /runs/{id}/resume
2. API sets run status → running
3. API calls Dispatcher to re-evaluate ready nodes from current state
4. Dispatcher enqueues ready nodes → execution continues
```

### 5.3 Webhook Trigger

```
1. External system POST /triggers/webhook/{key} {payload}
2. API looks up webhook_trigger by key
3. API resolves associated workflow_id + input mapping
4. API creates workflow_run with mapped inputs → same as 5.1 step 3+
```

### 5.4 Schedule Trigger

```
1. Scheduler polls schedule_triggers WHERE next_fire_at <= now()
2. For each due trigger:
   a. Create workflow_run with configured inputs
   b. Enqueue start node via Arq
   c. Update next_fire_at based on cron expression
3. All within a transaction (FOR UPDATE SKIP LOCKED) to prevent double-fire
```

### 5.5 Event Streaming (SSE + WebSocket)

```
SSE:
1. Client GET /runs/{id}/events (SSE connection)
2. API subscribes to Redis pub/sub channel: run:{run_id}
3. Worker/Dispatcher publishes events to channel on each state change
4. API forwards events to client as SSE messages
5. On disconnect, API unsubscribes from channel

WebSocket:
1. Client connects to ws://host/ws/runs/{run_id}
2. ConnectionManager tracks active connections per run_id
3. Bidirectional messaging: server sends events, client sends ping/cancel ack/resume ack
4. Dead connections auto-pruned on broadcast attempt
```

### 5.6 Sub-Workflow Execution

```
1. SubWorkflowExecutor receives NodeContext with embedded child definition
2. Child definition is validated via load_dict()
3. input_mapping is resolved from parent variable pool → child_inputs
4. WorkflowExecutor.execute_workflow() runs child synchronously in-process
5. Child result mapped: COMPLETED→completed, PAUSED→waiting, FAILED→failed
6. Child outputs become parent node outputs
```

---

## 6. Error Handling Strategy

### 6.1 Error Hierarchy

All errors inherit from `FlowkitError` with a machine-readable `code` and optional `details` dict:

| Class | Code | HTTP | Use Case |
|-------|------|------|----------|
| `FlowkitError` | `FLOWKIT_ERROR` | 500 | Base class |
| `NotFoundError` | `NOT_FOUND` | 404 | Resource not found |
| `ValidationError` | `VALIDATION_ERROR` | 422 | Input validation |
| `ExecutionError` | `EXECUTION_ERROR` | 500 | Node execution failure |
| `TimeoutError` | `TIMEOUT` | 504 | Operation timeout |
| `WebhookError` | `WEBHOOK_ERROR` | 400 | Webhook processing |
| `StateTransitionError` | `INVALID_TRANSITION` | 409 | Invalid state change |

A global exception handler maps these to structured JSON error responses on all API routes.

### 6.2 Node-Level

- Code node: AST pre-validation, daemon-thread timeout, source size limit
- HTTP node: jitter backoff, 10MB response limit, 4xx/5xx retry
- Loop node: `max_iterations` enforcement (default 100)
- Parallel node: fail-fast — first FAILED aborts remaining
- Node failures set `node_run.status = failed` with error detail

### 6.3 Dead-Letter Queue

Unrecoverable failures are recorded in `dead_letter_queue` for later inspection/retry:

```
dead_letter_queue fields:
  workflow_run_id, node_id, error, attempt, max_retries, status
  status: pending | retrying | resolved | failed
```

`DeadLetterRepo` provides: `create()`, `retry()` (increment attempt + re-enqueue), `resolve()` (mark resolved).

### 6.4 Engine-Level

- Dispatcher failures: Run stays in `running`. Detected by watchdog query.
- Worker crash mid-execution: Node stays in `running`. Watchdog re-enqueues (idempotent execution expected).
- DB failure: All operations fail loudly. No silent data loss.

### 6.5 Infrastructure-Level

- Redis down: Workers stall but do not corrupt. Pending tasks re-queued on recovery.
- PostgreSQL down: Everything halts. Services retry with backoff.
- Scheduler graceful shutdown: `asyncio.Event` allows clean poll termination on SIGTERM.

---

## 7. Security

### 7.1 API Authentication

- `X-API-Key` header-based auth via `ApiKeyMiddleware`
- Configured with `FLOWKIT_API_KEY` env var
- Disabled by default (empty key = dev mode)
- Public paths exempt: `/health`, `/docs`, `/openapi.json`, `/redoc`
- Uses `secrets.compare_digest` for timing-safe comparison

### 7.2 Code Node Sandbox

- AST pre-validation: rejects dangerous constructs (`__import__`, `open`, `os`, `sys`, `subprocess`, `eval`, `exec`, `compile`)
- Daemon-thread timeout via `threading.Thread(daemon=True)` + `join(timeout)`
- Source size limit (configurable)
- Restricted builtins: no `__import__`, no `open`, no `compile`

### 7.3 Other

- Webhook keys are opaque UUIDs
- API key auth is optional — intended for internal/trusted networks when disabled
- Secrets in workflow variables are stored as plaintext in DB (encryption deferred to future)

---

## 8. Deployment Model

### Single-Machine Development

```
docker-compose:
  - api (FastAPI, uvicorn)
  - worker (Arq worker process)
  - scheduler (DB-polling process)
  - postgres
  - redis
```

Entry points:
- `flowkit.api.app:create_app` (uvicorn)
- `flowkit.worker.tasks:WorkerSettings` (arq)
- `flowkit.scheduler.poller:main` (plain async loop)

### Production Path (future)

- API: Multiple replicas behind LB
- Workers: Scale horizontally based on queue depth
- Scheduler: Single-active with PG advisory lock
- PostgreSQL: Managed instance with connection pooling (pgbouncer)
- Redis: Managed instance or Sentinel for HA

---

## 9. Configuration

Single config source via environment variables + Pydantic `BaseSettings` with `FLOWKIT_` prefix:

| Variable | Default | Description |
|----------|---------|-------------|
| `FLOWKIT_DATABASE_URL` | `postgresql+asyncpg://...` | PostgreSQL connection |
| `FLOWKIT_REDIS_URL` | `redis://localhost:6379` | Redis connection |
| `FLOWKIT_API_HOST` | `0.0.0.0` | API bind host |
| `FLOWKIT_API_PORT` | `8000` | API bind port |
| `FLOWKIT_API_KEY` | `""` | API key for auth (empty = disabled) |
| `FLOWKIT_WORKER_CONCURRENCY` | `10` | Max concurrent node executions per worker |
| `FLOWKIT_SCHEDULER_POLL_INTERVAL` | `15` | Seconds between schedule polls |
| `FLOWKIT_LOG_LEVEL` | `INFO` | Logging level |

---

## 10. Open Items for Future

| Item | Tracked In |
|------|------------|
| DSL v1 JSON schema & node catalog | `specs/dsl-v1.md` |
| Database table design (8 tables) | `specs/persistence.md` |
| Plugin / custom node packaging | `src/flowkit/plugins/` |
| Template variables + secrets management | Backlog |
| Multi-tenancy | Backlog |
| Distributed scheduler (leader election) | Backlog |
| SDK (Python client) | Backlog |
| CLI tool | Backlog |
