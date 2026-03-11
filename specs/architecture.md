# Flowkit Architecture Spec

> Status: **Draft v1** · Date: 2026-03-11

## 1. Overview

Flowkit is a headless workflow backend that provides workflow definition, orchestration, execution, scheduling, trigger handling, runtime state persistence, and event streaming. It exposes a REST API consumed by external systems — no built-in UI.

### Design Principles

1. **Engine independence** — the workflow engine knows nothing about HTTP, API serialization, or delivery transport.
2. **Definition ≠ Runtime** — workflow definitions are immutable snapshots; runtime state is a separate, mutable concern.
3. **Persistence-first** — every state transition is persisted before it is acknowledged. No in-memory-only correctness.
4. **Composable nodes** — nodes are small, self-contained units with a uniform interface. The catalog grows incrementally.
5. **Narrow MVP** — ship the smallest useful surface; resist premature abstraction.

---

## 2. Service Topology

```
┌─────────────┐     ┌─────────────┐     ┌─────────────────┐
│  API Service │     │   Worker    │     │   Scheduler     │
│  (FastAPI)   │     │  Service    │     │   Service       │
│              │     │  (Arq)      │     │  (DB-polling)   │
└──────┬───────┘     └──────┬──────┘     └───────┬─────────┘
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
- **Responsibilities**: REST endpoints, request validation, SSE streaming, webhook ingestion
- **Does NOT**: Execute nodes, run cron jobs, maintain in-memory workflow state
- **Scaling**: Horizontal (stateless). Multiple replicas behind a load balancer.

### 2.2 Worker Service

- **Framework**: Arq (Redis-backed async task queue)
- **Responsibilities**: Execute individual node tasks, manage node-level retries, emit node completion events
- **Lifecycle**: Picks tasks from Redis queue → loads node context from DB → executes → writes result to DB → enqueues next-ready nodes
- **Scaling**: Horizontal. Each worker is stateless; coordination is via DB + Redis.

### 2.3 Scheduler Service

- **Framework**: Custom DB-polling loop (single lightweight process)
- **Responsibilities**: Poll `schedule_triggers` table for due triggers → enqueue workflow runs via the same path as API-initiated runs
- **Polling interval**: Configurable, default 15s
- **Scaling**: Single-active with leader election (advisory lock). Multiple instances for HA, only one polls at a time.

---

## 3. Module Architecture

```
flowkit/
├── definition/          # Workflow DSL, schema, validation
│   ├── schema.py        # Pydantic models for DSL v1
│   ├── validator.py     # Graph validation (cycles, reachability, types)
│   └── loader.py        # Parse & instantiate workflow definitions
│
├── engine/              # Core runtime engine
│   ├── graph.py         # In-memory graph representation for a run
│   ├── dispatcher.py    # Determines next-ready nodes, enqueues work
│   ├── executor.py      # Node execution orchestration
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
│   └── human_input.py
│
├── runtime/             # Runtime state management
│   ├── variable_pool.py # Scoped variable read/write
│   ├── state.py         # Run & node state machines
│   └── snapshot.py      # State snapshot for pause/resume
│
├── persistence/         # Database repositories
│   ├── models.py        # SQLAlchemy / raw SQL table definitions
│   ├── workflow_repo.py
│   ├── run_repo.py
│   ├── node_run_repo.py
│   ├── trigger_repo.py
│   └── event_repo.py
│
├── triggers/            # Trigger subsystem
│   ├── webhook.py       # Webhook trigger handler
│   └── schedule.py      # Schedule trigger evaluation
│
├── streaming/           # Event streaming
│   ├── emitter.py       # Publish events (Redis pub/sub)
│   └── sse.py           # SSE transport for API consumers
│
├── api/                 # FastAPI application
│   ├── app.py           # Application factory
│   ├── deps.py          # Dependency injection
│   ├── routes/
│   │   ├── workflows.py
│   │   ├── runs.py
│   │   ├── triggers.py
│   │   └── events.py
│   └── schemas/         # API request/response models (NOT engine models)
│       ├── workflow.py
│       ├── run.py
│       └── trigger.py
│
├── worker/              # Arq worker entry point
│   ├── tasks.py         # Task definitions
│   └── settings.py      # Arq worker settings
│
├── scheduler/           # Scheduler service entry point
│   └── poller.py        # DB-polling loop
│
└── config.py            # Centralized configuration
```

### 3.1 Module Boundaries & Dependencies

```
api  ──→  engine  ──→  runtime
 │          │            │
 │          ▼            │
 │        nodes          │
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
- `api` depends on `engine` and `persistence`. Never imports from `nodes` directly.
- `persistence` is the only module that talks to PostgreSQL.
- `streaming` is the only module that manages Redis pub/sub for events.
- `worker` and `scheduler` are entry points, not libraries. Nothing imports from them.

---

## 4. Core Abstractions

### 4.1 WorkflowDefinition

Immutable, versioned snapshot of a workflow's structure. Stored as a JSON document (DSL v1). See `specs/dsl-v1.md`.

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
- `node_config`: The node's static configuration from the DSL
- `variables`: Scoped read/write access to the variable pool
- `inputs`: Resolved input data from upstream edges
- `run_id`, `node_id`: Identifiers

`NodeResult` contains:
- `outputs`: Dict of output values
- `edge_selector`: Which outgoing edge(s) to activate (for branching nodes)
- `status`: `completed` | `failed` | `waiting` (for human_input)

### 4.4 VariablePool

Scoped key-value store for a single workflow run. Two scopes:
- **workflow scope**: Readable/writable by any node in the run.
- **node scope**: Private to a single node execution (inputs/outputs).

Backed by a JSONB column on the `workflow_runs` table. Loaded into memory during node execution, flushed to DB after each node completes.

### 4.5 Dispatcher

The Dispatcher determines which nodes are ready to execute after a node completes:

```
on_node_complete(run_id, node_id, result):
    1. Record node result in DB
    2. Resolve activated edges from result.edge_selector
    3. For each target node of activated edges:
       a. Check if ALL incoming edges are satisfied (join semantics)
       b. If ready → enqueue node task via Arq
    4. If no nodes are ready AND no nodes are running → run is complete
```

### 4.6 State Machines

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
14. Events emitted at each step via Redis pub/sub → SSE
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
3. All within a transaction to prevent double-fire
```

### 5.5 Event Streaming (SSE)

```
1. Client GET /runs/{id}/events (SSE connection)
2. API subscribes to Redis pub/sub channel: run:{run_id}
3. Worker/Dispatcher publishes events to channel on each state change:
   - node_started, node_completed, node_failed
   - run_completed, run_failed, run_paused
   - variable_updated (opt-in)
4. API forwards events to client as SSE messages
5. On disconnect, API unsubscribes from channel
```

---

## 6. Error Handling Strategy

### 6.1 Node-Level

- Each node type defines its own error handling (e.g., HTTP node: timeout, status code mapping)
- Node failures set `node_run.status = failed` with error detail in `node_run.error`
- Default behavior: node failure → run failure (fail-fast)
- Future: per-node retry policy, error handlers, fallback edges

### 6.2 Engine-Level

- Dispatcher failures (bug, crash): Run stays in `running` with no progress. Detected by a watchdog query: "runs in `running` with no `running` nodes and last activity > threshold"
- Worker crash mid-execution: Node stays in `running`. Same watchdog detects and re-enqueues (idempotent execution required)
- DB failure: All operations fail loudly. No silent data loss.

### 6.3 Infrastructure-Level

- Redis down: Workers cannot receive tasks. Runs stall but do not corrupt. Recovery: Redis comes back, pending tasks in queue are processed.
- PostgreSQL down: Everything halts. No writes accepted. Services retry with backoff.

---

## 7. Deployment Model (MVP)

### Single-Machine Development

```
docker-compose:
  - api (FastAPI, uvicorn)
  - worker (Arq worker process)
  - scheduler (DB-polling process)
  - postgres
  - redis
```

All three services share the same codebase, different entry points:
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

## 8. Configuration

Single config source via environment variables + Pydantic `BaseSettings`:

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://...` | PostgreSQL connection |
| `REDIS_URL` | `redis://localhost:6379` | Redis connection |
| `SCHEDULER_POLL_INTERVAL` | `15` | Seconds between schedule polls |
| `WORKER_CONCURRENCY` | `10` | Max concurrent node executions per worker |
| `LOG_LEVEL` | `INFO` | Logging level |
| `API_HOST` | `0.0.0.0` | API bind host |
| `API_PORT` | `8000` | API bind port |

---

## 9. Security Boundaries (MVP)

- No multi-tenancy in v1. Single-tenant deployment assumed.
- Code node executes in-process (sandboxing deferred to v2).
- Webhook keys are opaque UUIDs — no signing verification in v1.
- No authentication on API in v1 (intended for internal/trusted network).
- Secrets in workflow variables are stored as plaintext in DB (encryption deferred).

---

## 10. Open Items for Future Specs

| Item | Tracked In |
|------|------------|
| DSL v1 JSON schema & node catalog | `specs/dsl-v1.md` |
| Database table design | `specs/persistence.md` |
| API endpoint contracts | `specs/api.md` (future) |
| Code node sandboxing | Backlog |
| Plugin / custom node packaging | Backlog |
| Distributed tracing | Backlog |
