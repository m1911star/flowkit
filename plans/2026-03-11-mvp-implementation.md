# MVP → Phase 2 Implementation Plan

> **Status: ✅ ALL PHASES COMPLETE** — 609 tests passing, 3.40s

## Goal

Implemented Flowkit MVP + Phase 2: headless workflow backend with DSL v1, graph validation,
execution engine, persistence, webhook/schedule triggers, pause/resume/cancel,
SSE + WebSocket streaming, plugin model, parallel execution, sub-workflow composition,
structured error hierarchy, dead-letter queue, API auth. Full test coverage on all modules.

## Architecture

- **API Service**: FastAPI, serves REST endpoints, SSE streaming
- **Worker Service**: Arq-based async workers, execute nodes
- **Scheduler Service**: DB-polling loop for cron triggers
- **Persistence**: PostgreSQL (asyncpg + SQLAlchemy Core), Redis
- **Stack**: Python 3.12, uv for packaging

## Implementation Phases

### Phase 1 — Project Scaffold + Config + Models (Foundation) ✅

**Task 1.1: Project scaffold**
- Files: pyproject.toml, src/flowkit/__init__.py, src/flowkit/config.py, tests/conftest.py
- Setup uv project with dependencies: fastapi, uvicorn, sqlalchemy, asyncpg, redis, arq, pydantic, pydantic-settings, alembic, pytest, pytest-asyncio, httpx
- Config via pydantic BaseSettings (DATABASE_URL, REDIS_URL, etc.)
- Tests: test config loading from env vars

**Task 1.2: Database models + migrations**
- Files: src/flowkit/persistence/models.py, alembic.ini, alembic/env.py, alembic/versions/001_initial.py
- SQLAlchemy Core table definitions for all 7 tables per persistence spec
- Alembic migration for initial schema
- Tests: table creation against test DB, column types, constraints, indexes

**Task 1.3: Repository layer**
- Files: src/flowkit/persistence/repos.py, src/flowkit/persistence/database.py
- Async database session management (asyncpg)
- CRUD repos: WorkflowRepo, WorkflowVersionRepo, WorkflowRunRepo, NodeRunRepo, RunEventRepo, WebhookTriggerRepo, ScheduleTriggerRepo
- Tests: full CRUD for each repo against test DB

### Phase 2 — Definition Layer (DSL + Validation) ✅

**Task 2.1: DSL schema (Pydantic models)**
- Files: src/flowkit/definition/schema.py
- Pydantic models: WorkflowDefinition, NodeDef, EdgeDef, InputDef, OutputDef, + per-node config models (HttpConfig, CodeConfig, IfElseConfig, LoopConfig, HumanInputConfig)
- Enum types: NodeType, DataType
- Tests: valid/invalid deserialization, type coercion, defaults

**Task 2.2: Graph validator**
- Files: src/flowkit/definition/validator.py
- Implement all 32 validation rules (V-001 through V-032)
- Structural checks, graph checks (DAG, connectivity, reachability), type checks, semantic checks
- Tests: one test per validation rule minimum, plus happy-path full-graph validation

**Task 2.3: Definition loader**
- Files: src/flowkit/definition/loader.py
- Parse JSON → WorkflowDefinition → validate → return
- Checksum generation (SHA256 of canonical JSON)
- Tests: round-trip load, checksum stability, error propagation

### Phase 3 — Runtime Layer ✅

**Task 3.1: Variable pool**
- Files: src/flowkit/runtime/variable_pool.py
- Scoped variable storage: workflow scope, node scopes
- Variable reference resolution: parse {{workflow.input.X}}, {{nodes.ID.output.Y}}
- Serialization to/from JSONB dict for persistence
- Tests: set/get, scope isolation, reference resolution, serialization round-trip

**Task 3.2: State management**
- Files: src/flowkit/runtime/state.py
- RunState and NodeState enums with valid transition tables
- Transition validation functions
- Tests: all valid transitions pass, all invalid transitions raise

### Phase 4 — Engine Layer ✅

**Task 4.1: Graph runtime**
- Files: src/flowkit/engine/graph.py
- Build executable Graph from WorkflowDefinition
- find_ready_nodes(run_context) → list of node_ids (check incoming edges resolved)
- find_start_node(), get_node(), get_successors(), get_predecessors()
- Tests: graph construction, ready-node detection for linear/branching/join topologies

**Task 4.2: Node executors**
- Files: src/flowkit/nodes/base.py, src/flowkit/nodes/start.py, src/flowkit/nodes/end.py, src/flowkit/nodes/http.py, src/flowkit/nodes/code.py, src/flowkit/nodes/if_else.py, src/flowkit/nodes/loop.py, src/flowkit/nodes/human_input.py, src/flowkit/nodes/registry.py
- NodeExecutor ABC: execute(NodeContext) → NodeResult
- NodeContext: node_def, variable_pool, run_id, node_run_id
- NodeResult: status, outputs, error, next_handle
- Registry: maps NodeType → executor class
- Tests per executor: happy path, error handling, edge cases

**Task 4.3: Dispatcher + command channel**
- Files: src/flowkit/engine/dispatcher.py, src/flowkit/engine/commands.py, src/flowkit/engine/executor.py
- Commands: StartRun, PauseRun, ResumeRun, CancelRun, CompleteNode
- Dispatcher: process_command() → state transitions + enqueue next nodes
- Executor: orchestrates run lifecycle (init → dispatch start → loop until done)
- Tests: full run lifecycle for linear/branching workflows, pause/resume/cancel flows

### Phase 5 — Streaming + Triggers ✅

**Task 5.1: Event emitter**
- Files: src/flowkit/streaming/emitter.py
- Emit run_events to DB + Redis pub/sub
- 11 event types per spec
- Tests: event emission, event ordering (sequence numbers)

**Task 5.2: SSE endpoint**
- Files: src/flowkit/streaming/sse.py
- SSE response generator from Redis pub/sub subscription
- Tests: SSE format, reconnection (Last-Event-ID), filtering by run_id

**Task 5.3: Webhook trigger handler**
- Files: src/flowkit/triggers/webhook.py
- Lookup by key → resolve workflow + inputs → start run
- Tests: valid trigger, inactive trigger, unknown key, input mapping

**Task 5.4: Schedule trigger poller**
- Files: src/flowkit/scheduler/poller.py
- DB polling loop: find due triggers (next_fire_at <= now), SKIP LOCKED, fire, update next_fire_at
- Cron expression parsing (croniter)
- Tests: polling logic, cron computation, concurrent safety

### Phase 6 — API Layer ✅

**Task 6.1: API schemas**
- Files: src/flowkit/api/schemas/workflows.py, src/flowkit/api/schemas/runs.py, src/flowkit/api/schemas/triggers.py
- Request/response Pydantic models (separate from internal models)
- Tests: serialization/deserialization

**Task 6.2: API routes**
- Files: src/flowkit/api/routes/workflows.py, src/flowkit/api/routes/runs.py, src/flowkit/api/routes/triggers.py, src/flowkit/api/routes/events.py
- POST /workflows, GET /workflows, GET /workflows/:id
- POST /workflows/:id/versions (publish), GET /workflows/:id/versions
- POST /workflows/:id/run, GET /runs/:id, POST /runs/:id/resume, POST /runs/:id/cancel
- POST /triggers/webhook/:key
- GET /runs/:id/events (SSE)
- Tests: full HTTP tests via httpx AsyncClient

**Task 6.3: App assembly + deps**
- Files: src/flowkit/api/app.py, src/flowkit/api/deps.py
- FastAPI app factory, dependency injection (DB session, Redis, repos)
- Lifespan handler: connect DB pool, Redis pool, shutdown
- Tests: app startup/shutdown, health endpoint

### Phase 7 — Worker + Integration ✅

**Task 7.1: Arq worker**
- Files: src/flowkit/worker/tasks.py, src/flowkit/worker/settings.py
- Arq task: execute_node(run_id, node_id) → lookup → execute → dispatch
- Worker settings: redis connection, concurrency
- Tests: task execution mock

**Task 7.2: Integration tests**
- Files: tests/integration/test_linear_workflow.py, tests/integration/test_branching_workflow.py, tests/integration/test_pause_resume.py, tests/integration/test_webhook_trigger.py
- End-to-end: define workflow → run → verify state transitions + events
- Tests use in-process execution (no Arq, synchronous dispatch) for determinism

## Dependency Graph

```
Phase 1 (scaffold, models, repos)
  ├─→ Phase 2 (DSL schema, validator, loader) [independent]
  ├─→ Phase 3 (variable pool, state mgmt) [independent]
  │
  Phase 2 + Phase 3
  └─→ Phase 4 (graph, executors, dispatcher)
       └─→ Phase 5 (streaming, triggers)
            └─→ Phase 6 (API)
                 └─→ Phase 7 (worker, integration)
```

## Execution Strategy

- Phase 1: sequential (foundation)
- Phase 2 + Phase 3: parallel (independent)
- Phase 4-7: sequential (each depends on previous)
