<h1 align="center">
  <br>
  ⚙️ Flowkit
  <br>
</h1>

<p align="center">
  <strong>Headless workflow engine for Python — define, execute, pause, resume, stream.</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.12+-3776ab?style=flat-square&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white" />
  <img src="https://img.shields.io/badge/PostgreSQL-4169E1?style=flat-square&logo=postgresql&logoColor=white" />
  <img src="https://img.shields.io/badge/Redis-DC382D?style=flat-square&logo=redis&logoColor=white" />
  <img src="https://img.shields.io/badge/tests-609%20passed-brightgreen?style=flat-square" />
  <img src="https://img.shields.io/badge/license-MIT-blue?style=flat-square" />
</p>

<p align="center">
  <em>No UI. No vendor lock-in. Just a clean, modular workflow runtime you can embed anywhere.</em>
</p>

---

## What is Flowkit?

Flowkit is an open-source, headless workflow backend — a standalone engine for defining, validating, executing, and managing workflows via API. It handles:

- **Workflow Definition** — JSON-based DSL with graph validation (10 node types)
- **Execution Engine** — DAG-based dispatcher with topological ordering + parallel fan-out
- **State Persistence** — Full run/node-run records in PostgreSQL + dead-letter queue
- **Pause / Resume / Cancel** — First-class support via human-input nodes
- **Event Streaming** — Real-time SSE + WebSocket events for every state transition
- **Triggers** — Webhook and cron-based schedule triggers
- **Async Workers** — Arq-powered background execution with Redis
- **Plugin Model** — Custom node types via plugin interface with entry-point discovery
- **Sub-Workflows** — Nested workflow composition (workflow-as-node)
- **Error Hierarchy** — Structured errors with machine-readable codes + dead-letter tracking

> Think of it as the execution layer you'd rip out of Dify, N8N, or Prefect — but decoupled from any product UI.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        API Layer (FastAPI)                   │
│  /workflows  /runs  /triggers  /events(SSE)  /ws(WS)       │
│  ↕ Auth: X-API-Key middleware                                │
└──────────┬────────────────────────────────┬─────────────────┘
           │                                │
           ▼                                ▼
┌─────────────────────┐          ┌────────────────────┐
│   Worker (Arq)      │          │  Scheduler (Poller)│
│   async task exec   │          │  cron-based polls   │
└─────────┬───────────┘          └────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────┐
│                     Engine Core                              │
│  ┌──────────┐  ┌────────────┐  ┌────────────┐              │
│  │ Graph    │  │ Dispatcher │  │ Executor   │              │
│  │ Builder  │  │ (topo-sort)│  │ (parallel) │              │
│  └──────────┘  └────────────┘  └────────────┘              │
│  ┌──────────┐  ┌────────────┐  ┌────────────┐              │
│  │ Variable │  │ Run State  │  │ Error      │              │
│  │ Pool     │  │ Machine    │  │ Hierarchy  │              │
│  └──────────┘  └────────────┘  └────────────┘              │
│  ┌──────────┐  ┌────────────┐                               │
│  │ Plugin   │  │ Sub-Wkfl   │                               │
│  │ Adapter  │  │ Executor   │                               │
│  └──────────┘  └────────────┘                               │
└──────────┬──────────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────┐
│               Persistence (SQLAlchemy Core)                  │
│  workflows │ versions │ runs │ node_runs │ events            │
│  webhook_triggers │ schedule_triggers │ dead_letter_queue   │
└─────────────────────────────────────────────────────────────┘
```

---

## Node Types (10 types)

| Node | Purpose | Key Behavior |
|------|---------|-------------|
| `start` | Entry point | Injects initial variables into the run |
| `end` | Terminal node | Collects final outputs |
| `code` | Inline Python | AST-validated sandbox with daemon-thread timeout |
| `http` | HTTP request | Async `httpx` with jitter backoff + retry |
| `if_else` | Conditional branch | Evaluates expression → routes to branch |
| `loop` | Iteration | Repeats body nodes N times (max_iterations guard) |
| `human_input` | Pause & wait | Suspends run, resumes on external signal |
| `parallel` | Fan-out | Concurrent branches over collection items |
| `sub_workflow` | Nested workflow | Executes child workflow definition inline |
| `plugin` | Custom node | User-registered via PluginNodeExecutor ABC |

---

## Demo Workflows

Three example workflows demonstrate the engine capabilities. Each includes a **Mermaid diagram** and **live execution output** from `demo_workflows.py`.

### Flow 1 — Linear Pipeline

A simple computation: `start → compute(7×6+8) → format → end`

**Mermaid Source:**

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {
  'fontSize': '14px',
  'fontFamily': 'Inter, system-ui, sans-serif',
  'primaryColor': '#4f46e5',
  'primaryTextColor': '#ffffff',
  'primaryBorderColor': '#4338ca',
  'lineColor': '#6366f1',
  'secondaryColor': '#f0fdf4',
  'tertiaryColor': '#fef2f2'
}}}%%

flowchart LR
    A([🟢 Start]):::startNode --> B[⚡ Compute<br/><small>result = a × b + c</small>]:::processNode
    B --> C[📝 Format<br/><small>message = '...'</small>]:::processNode
    C --> D([🔴 End]):::endNode

    classDef startNode fill:#22c55e,stroke:#16a34a,color:#fff,stroke-width:2px
    classDef endNode fill:#ef4444,stroke:#dc2626,color:#fff,stroke-width:2px
    classDef processNode fill:#4f46e5,stroke:#4338ca,color:#fff,stroke-width:2px
```

**Rendered:**

<p align="center">
  <img src="diagrams/flow1_linear_pipeline.svg" alt="Linear Pipeline Flow" width="700" />
</p>

<details>
<summary>📟 Execution Output (click to expand)</summary>

```
═══════════════════════════════════════════════════════
  Flow 1: Linear Pipeline
  start → compute(a×b+c) → format(message) → end
═══════════════════════════════════════════════════════

  Inputs:  a=7, b=6, c=8
  Expected: 7 × 6 + 8 = 50

  ▶ Run(ea143e77)          pending → running
  📡 run_started
    ▶ Node(start_1)        pending → running     → type=start
    ✅ Node(start_1)        running → completed   → outputs={'a': 7, 'b': 6, 'c': 8}
    ▶ Node(compute)        pending → running     → type=code
    ✅ Node(compute)        running → completed   → outputs={'value': 50}
    ▶ Node(format)         pending → running     → type=code
    ✅ Node(format)         running → completed   → outputs={'message': '7 × 6 + 8 = 50'}
    ▶ Node(end_1)          pending → running     → type=end
    ✅ Node(end_1)          running → completed   → outputs={'message': '7 × 6 + 8 = 50'}
  ✅ Run(ea143e77)          running → completed
  📡 run_completed

  Final Outputs
    status               = completed
    message              = 7 × 6 + 8 = 50
```

</details>

---

### Flow 2 — Conditional Branching

Score-based routing: `start → if_else(score≥60?) → pass/fail → end`

**Mermaid Source:**

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {
  'fontSize': '14px',
  'fontFamily': 'Inter, system-ui, sans-serif',
  'primaryColor': '#4f46e5',
  'primaryTextColor': '#ffffff',
  'primaryBorderColor': '#4338ca',
  'lineColor': '#6366f1',
  'secondaryColor': '#f0fdf4',
  'tertiaryColor': '#fef2f2'
}}}%%

flowchart TD
    A([🟢 Start]):::startNode --> B{🔀 If/Else<br/><small>score >= 60?</small>}:::conditionNode
    B -- "score >= 60" --> C[✅ Pass<br/><small>result = 'passed'</small>]:::passNode
    B -- "else" --> D[❌ Fail<br/><small>result = 'failed'</small>]:::failNode
    C --> E([🔵 End]):::endNode
    D --> E

    classDef startNode fill:#22c55e,stroke:#16a34a,color:#fff,stroke-width:2px
    classDef endNode fill:#4f46e5,stroke:#4338ca,color:#fff,stroke-width:2px
    classDef conditionNode fill:#f59e0b,stroke:#d97706,color:#fff,stroke-width:2px
    classDef passNode fill:#22c55e,stroke:#16a34a,color:#fff,stroke-width:2px
    classDef failNode fill:#ef4444,stroke:#dc2626,color:#fff,stroke-width:2px
```

**Rendered:**

<p align="center">
  <img src="diagrams/flow2_branching.svg" alt="Conditional Branching Flow" width="500" />
</p>

<details>
<summary>📟 Execution Output — score=85 PASS (click to expand)</summary>

```
═══════════════════════════════════════════════════════
  Flow 2a: Branching (PASS path)
  start → if_else(score>=60?) → pass/fail → end
═══════════════════════════════════════════════════════

  Inputs:  score=85
  Expected: PASS branch

  ▶ Run(b3f1a2c4)          pending → running
    ▶ Node(start_1)        pending → running     → type=start
    ✅ Node(start_1)        running → completed   → outputs={'score': 85}
    ▶ Node(check_score)    pending → running     → type=if_else
    ✅ Node(check_score)    running → completed   → outputs={'branch': 'true'}
    ▶ Node(pass_node)      pending → running     → type=code
    ✅ Node(pass_node)      running → completed   → outputs={'result': 'passed'}
    ▶ Node(end_1)          pending → running     → type=end
    ✅ Node(end_1)          running → completed   → outputs={'result': 'passed'}
  ✅ Run(b3f1a2c4)          running → completed

  Final Outputs
    status               = completed
    result               = passed
```

</details>

<details>
<summary>📟 Execution Output — score=42 FAIL (click to expand)</summary>

```
═══════════════════════════════════════════════════════
  Flow 2b: Branching (FAIL path)
  start → if_else(score>=60?) → pass/fail → end
═══════════════════════════════════════════════════════

  Inputs:  score=42
  Expected: FAIL branch

  ▶ Run(d7e9f0b1)          pending → running
    ▶ Node(start_1)        pending → running     → type=start
    ✅ Node(start_1)        running → completed   → outputs={'score': 42}
    ▶ Node(check_score)    pending → running     → type=if_else
    ✅ Node(check_score)    running → completed   → outputs={'branch': 'false'}
    ▶ Node(fail_node)      pending → running     → type=code
    ✅ Node(fail_node)      running → completed   → outputs={'result': 'failed'}
    ▶ Node(end_1)          pending → running     → type=end
    ✅ Node(end_1)          running → completed   → outputs={'result': 'failed'}
  ✅ Run(d7e9f0b1)          running → completed

  Final Outputs
    status               = completed
    result               = failed
```

</details>

---

### Flow 3 — Human-in-the-Loop

Pause & resume: `start → calculate → ⏸ human_approval → process → end`

**Mermaid Source:**

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {
  'fontSize': '14px',
  'fontFamily': 'Inter, system-ui, sans-serif',
  'primaryColor': '#4f46e5',
  'primaryTextColor': '#ffffff',
  'primaryBorderColor': '#4338ca',
  'lineColor': '#6366f1',
  'secondaryColor': '#f0fdf4',
  'tertiaryColor': '#fef2f2'
}}}%%

flowchart TD
    A([🟢 Start]):::startNode --> B[⚡ Calculate<br/><small>total = price × qty</small>]:::processNode
    B --> C[/⏸ Human Approval<br/><small>PAUSES run</small>/]:::humanNode
    C -- "▶️ resumed" --> D[📦 Process<br/><small>order confirmed</small>]:::processNode
    D --> E([🔴 End]):::endNode

    classDef startNode fill:#22c55e,stroke:#16a34a,color:#fff,stroke-width:2px
    classDef endNode fill:#ef4444,stroke:#dc2626,color:#fff,stroke-width:2px
    classDef processNode fill:#4f46e5,stroke:#4338ca,color:#fff,stroke-width:2px
    classDef humanNode fill:#f59e0b,stroke:#d97706,color:#fff,stroke-width:2px,stroke-dasharray: 5 5
```

**Rendered:**

<p align="center">
  <img src="diagrams/flow3_human_in_loop.svg" alt="Human-in-the-Loop Flow" width="400" />
</p>

<details>
<summary>📟 Execution Output (click to expand)</summary>

```
═══════════════════════════════════════════════════════
  Flow 3: Human-in-the-Loop
  start → calc → ⏸ approve → process → end
═══════════════════════════════════════════════════════

  Inputs:  price=99.9, qty=3
  Expected: pause → resume → completed

  ▶ Run(c4a5b6d7)          pending → running
    ▶ Node(start_1)        pending → running     → type=start
    ✅ Node(start_1)        running → completed   → outputs={'price': 99.9, 'qty': 3}
    ▶ Node(calc)           pending → running     → type=code
    ✅ Node(calc)           running → completed   → outputs={'total': 299.7}
    ▶ Node(approve)        pending → running     → type=human_input
    ⏸ Node(approve)        running → paused      → waiting for input...
  ⏸ Run(c4a5b6d7)          running → paused
  📡 run_paused

  💤 Run is paused. Simulating human approval...

  ▶ Run(c4a5b6d7)          paused → running       (resumed)
    ▶ Node(approve)        paused → running       → resumed with {'approved': True}
    ✅ Node(approve)        running → completed   → outputs={'approved': True}
    ▶ Node(process)        pending → running     → type=code
    ✅ Node(process)        running → completed   → outputs={'order': 'confirmed', 'total': 299.7}
    ▶ Node(end_1)          pending → running     → type=end
    ✅ Node(end_1)          running → completed   → outputs={'order': 'confirmed', 'total': 299.7}
  ✅ Run(c4a5b6d7)          running → completed
  📡 run_completed

  Final Outputs
    status               = completed
    order                = confirmed
    total                = 299.7
```

</details>

---

## Quick Start

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- PostgreSQL (runtime) — SQLite used for tests
- Redis (for worker queue)

### Install

```bash
git clone https://github.com/m1911star/flowkit.git
cd flowkit
uv sync
```

### Run Tests

```bash
uv run pytest tests/ -v
```

```
609 passed in 3.40s
```

### Run Demo

```bash
uv run python demo_workflows.py
```

### Start the Server

```bash
# Set environment variables (or use .env) — all use FLOWKIT_ prefix
export FLOWKIT_DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/flowkit"
export FLOWKIT_REDIS_URL="redis://localhost:6379"
# Optional: API key auth
export FLOWKIT_API_KEY="your-secret-key"

uv run uvicorn flowkit.api.app:create_app --factory --reload
```

### API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/workflows` | Create a workflow |
| `GET` | `/workflows` | List workflows |
| `GET` | `/workflows/{id}` | Get workflow detail |
| `POST` | `/workflows/{id}/versions` | Publish a new version |
| `GET` | `/workflows/{id}/versions` | List all versions |
| `POST` | `/workflows/{id}/versions/{vid}/rollback` | Rollback to a version |
| `GET` | `/workflows/{id}/versions/diff` | Diff two versions |
| `POST` | `/workflows/{id}/runs` | Start a run |
| `GET` | `/runs/{id}` | Get run status |
| `POST` | `/runs/{id}/resume` | Resume paused run |
| `POST` | `/runs/{id}/cancel` | Cancel running run |
| `GET` | `/runs/{id}/events` | SSE event stream |
| `WS`  | `/ws/runs/{run_id}` | WebSocket bidirectional stream |
| `POST` | `/triggers/webhook` | Create webhook trigger |
| `POST` | `/triggers/schedule` | Create schedule trigger |

---

## Project Structure

```
src/flowkit/
├── api/                  # FastAPI routes, schemas, deps, middleware
│   ├── routes/           # workflows, runs, triggers
│   └── schemas/          # request/response models + error schemas
├── definition/           # DSL schema, validation, loader
├── engine/               # Graph builder, dispatcher, executor (parallel + sequential)
├── nodes/                # Node implementations (10 types)
├── plugins/              # PluginNodeExecutor ABC, registry, adapter, loader
├── persistence/          # SQLAlchemy models (8 tables), repos, database
├── runtime/              # Variable pool, run state machine
├── scheduler/            # Cron-based polling scheduler
├── streaming/            # SSE emitter + WebSocket connection manager
├── triggers/             # Webhook handler
├── worker/               # Arq async task runner + lifecycle hooks
├── config.py             # Pydantic settings (FLOWKIT_ prefix)
└── errors.py             # Structured error hierarchy

tests/
├── unit/                 # Unit tests across all modules
└── integration/          # Integration tests (full engine runs)
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| API | FastAPI + Uvicorn |
| Database | PostgreSQL (asyncpg) + SQLAlchemy Core |
| Queue | Redis + Arq |
| Migrations | Alembic |
| Validation | Pydantic v2 + pydantic-settings |
| HTTP Client | httpx (async) |
| Streaming | sse-starlette + WebSocket (starlette) |
| Scheduling | croniter + DB polling |
| Plugins | importlib.metadata entry points |
| Testing | pytest + pytest-asyncio + aiosqlite + testcontainers |
| Linting | Ruff + mypy (strict) |

---

## Configuration

All settings via environment variables with `FLOWKIT_` prefix:

| Variable | Default | Description |
|----------|---------|-------------|
| `FLOWKIT_DATABASE_URL` | `postgresql+asyncpg://...` | Database connection string |
| `FLOWKIT_REDIS_URL` | `redis://localhost:6379` | Redis connection for Arq |
| `FLOWKIT_API_HOST` | `0.0.0.0` | API bind host |
| `FLOWKIT_API_PORT` | `8000` | API bind port |
| `FLOWKIT_API_KEY` | `""` | API key for X-API-Key auth (empty = disabled) |
| `FLOWKIT_LOG_LEVEL` | `INFO` | Logging level |
| `FLOWKIT_WORKER_CONCURRENCY` | `10` | Max concurrent node executions per worker |
| `FLOWKIT_SCHEDULER_POLL_INTERVAL` | `15` | Cron scheduler poll interval (seconds) |

---

## License

MIT
