# BACKLOG

## Completed (MVP — Phase 1)

- [x] Project scaffold (pyproject.toml, uv, config)
- [x] Database models — 7 tables (workflows, versions, runs, node_runs, events, webhook_triggers, schedule_triggers)
- [x] Repository layer — 7 async repos with full CRUD
- [x] Alembic migration infrastructure + initial schema
- [x] DSL v1 schema (Pydantic v2 models, 7 node types)
- [x] Graph validator (32 validation rules, structural + semantic)
- [x] Definition loader (JSON → validate → checksum)
- [x] Variable pool (scoped storage, reference resolution, serialization)
- [x] Run state machine (RunState + NodeState with transition validation)
- [x] Graph builder (DAG construction, topological ordering, ready-node detection)
- [x] Node executors (start, end, http, code, if_else, loop, human_input)
- [x] Executor registry
- [x] Engine dispatcher + command channel (StartRun, PauseRun, ResumeRun, CancelRun, CompleteNode)
- [x] Workflow executor (orchestrates full run lifecycle)
- [x] SSE event streaming (emitter + endpoint)
- [x] Webhook trigger handler
- [x] Schedule trigger poller (DB-driven, cron via croniter)
- [x] API layer (FastAPI routes, Pydantic schemas, dependency injection)
- [x] Arq worker (async task execution + settings)
- [x] Architecture spec, DSL spec, persistence spec
- [x] 510 tests (474 unit + 36 integration)
- [x] Demo workflows (3 flows with Mermaid diagrams + execution output)

## Completed (Phase 2)

- [x] Structured error hierarchy — `FlowkitError` base + 6 subclasses (`NotFoundError`, `ValidationError`, `ExecutionError`, `TimeoutError`, `WebhookError`, `StateTransitionError`)
- [x] Global exception handler with status code mapping in API
- [x] Code node sandbox — AST pre-validation, daemon-thread timeout, source size limit
- [x] Loop node — `max_iterations` enforcement (default 100)
- [x] HTTP node — jitter backoff, 10MB response limit, 4xx/5xx retry
- [x] Structured logging across engine, nodes, triggers, persistence
- [x] Scheduler graceful shutdown via `asyncio.Event`
- [x] Worker lifecycle hooks (`on_startup`/`on_shutdown`)
- [x] Dead-letter queue table + `DeadLetterRepo` (create/retry/resolve)
- [x] API key auth middleware (`X-API-Key`, configurable, disabled by default)
- [x] OpenAPI error response annotations on all routes
- [x] Workflow versioning — rollback + diff endpoints
- [x] Parallel execution — `asyncio.gather()` for multiple ready nodes
- [x] New `parallel` node type — fan-out over collections with `max_concurrency`
- [x] New `sub_workflow` node type — nested workflow composition with `input_mapping`
- [x] WebSocket streaming — `/ws/runs/{run_id}` endpoint with bidirectional messaging
- [x] Plugin model — `PluginNodeExecutor` ABC, `PluginRegistry`, `PluginNodeAdapter`, entry point discovery
- [x] 609 tests passing, ruff clean, mypy clean

## Active (Phase 3)

- [ ] Template variables + secrets management
- [ ] Multi-tenancy (workspace isolation)
- [ ] Distributed scheduler (multi-instance leader election)
- [ ] SDK (Python client library)
- [ ] CLI tool for workflow management

## Out of Scope

- Visual workflow editor (headless only)
- RAG / knowledge base system
- Model provider management UI
- Billing and advanced tenancy model
- Plugin marketplace
