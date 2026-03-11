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

## Active (Phase 2)

- [ ] Error handling hardening — retry policies, dead-letter tracking
- [ ] HTTP node: response schema validation, timeout configuration
- [ ] Code node: sandbox hardening (restricted builtins, resource limits)
- [ ] Loop node: break conditions, max iteration guards
- [ ] Workflow versioning API (publish, rollback, diff)
- [ ] Run log / audit trail API
- [ ] Bulk operations (batch cancel, batch retry)
- [ ] Metrics / observability (structured logging, Prometheus counters)
- [ ] OpenAPI spec generation + API docs polish

## Backlog (Phase 3+)

- [ ] Plugin model for custom node types
- [ ] Parallel execution (fan-out / fan-in)
- [ ] Sub-workflow node (workflow-as-node composition)
- [ ] Template variables + secrets management
- [ ] Multi-tenancy (workspace isolation)
- [ ] Distributed scheduler (multi-instance leader election)
- [ ] WebSocket transport option for event streaming
- [ ] SDK (Python client library)
- [ ] CLI tool for workflow management

## Out of Scope

- Visual workflow editor (headless only)
- RAG / knowledge base system
- Model provider management UI
- Billing and advanced tenancy model
- Plugin marketplace
