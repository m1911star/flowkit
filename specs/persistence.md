# Flowkit Persistence Schema

> Status: **Draft v1** · Date: 2026-03-11

## 1. Overview

All Flowkit runtime state is persisted in PostgreSQL. This document defines the table schema, indexes, constraints, state machines, and migration strategy.

### Design Principles

1. **Persistence-first**: Every state transition is written to DB before being acknowledged.
2. **Append-friendly**: Prefer inserts + status updates over destructive modifications.
3. **Queryable**: Support operational debugging — "show me all failed nodes for run X".
4. **Immutable definitions**: Workflow definitions are versioned snapshots, never mutated in place.
5. **JSONB for flexibility**: Node configs, variable pools, and event payloads use JSONB to avoid schema churn.

---

## 2. Entity-Relationship Overview

```
workflows 1──∞ workflow_versions 1──∞ workflow_runs 1──∞ node_runs
                                  1──∞ run_events
workflows 1──∞ webhook_triggers
workflows 1──∞ schedule_triggers
```

---

## 3. Table Definitions

### 3.1 `workflows`

The top-level workflow entity. A logical container for versions.

```sql
CREATE TABLE workflows (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        VARCHAR(255) NOT NULL UNIQUE,   -- slug: [a-z0-9-]+
    description TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_workflows_name ON workflows (name);
```

### 3.2 `workflow_versions`

Immutable snapshots of workflow definitions. Each edit creates a new version.

```sql
CREATE TABLE workflow_versions (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_id   UUID NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
    version       INTEGER NOT NULL,                  -- auto-incrementing per workflow
    definition    JSONB NOT NULL,                     -- full DSL v1 document
    checksum      VARCHAR(64) NOT NULL,               -- SHA-256 of definition JSON
    is_published  BOOLEAN NOT NULL DEFAULT false,     -- only published versions can be run
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (workflow_id, version)
);

CREATE INDEX idx_wv_workflow_id ON workflow_versions (workflow_id);
CREATE INDEX idx_wv_published ON workflow_versions (workflow_id, is_published) WHERE is_published = true;
```

**Notes:**
- `definition` contains the complete DSL v1 JSON document.
- `checksum` prevents duplicate versions with identical content.
- `is_published`: Only one version can be published at a time per workflow (enforced at application level — see "Publishing" below).
- Validation is performed before insert; invalid definitions are rejected.

### 3.3 `workflow_runs`

A single execution instance of a workflow version.

```sql
CREATE TABLE workflow_runs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_id         UUID NOT NULL REFERENCES workflows(id),
    workflow_version_id UUID NOT NULL REFERENCES workflow_versions(id),
    status              VARCHAR(20) NOT NULL DEFAULT 'pending',
    inputs              JSONB NOT NULL DEFAULT '{}',       -- workflow input values
    outputs             JSONB,                              -- workflow output values (set on completion)
    variable_pool       JSONB NOT NULL DEFAULT '{}',       -- current runtime variable state
    error               JSONB,                              -- error details if failed
    trigger_type        VARCHAR(20),                        -- 'api' | 'webhook' | 'schedule' | null
    trigger_id          UUID,                               -- FK to webhook/schedule trigger (nullable)
    started_at          TIMESTAMPTZ,
    completed_at        TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_wr_workflow_id ON workflow_runs (workflow_id);
CREATE INDEX idx_wr_status ON workflow_runs (status);
CREATE INDEX idx_wr_created_at ON workflow_runs (created_at DESC);
CREATE INDEX idx_wr_active ON workflow_runs (status) WHERE status IN ('pending', 'running', 'paused');
```

**Status values:** `pending`, `running`, `paused`, `completed`, `failed`, `cancelled`

**State machine:**

```
pending → running         (start node enqueued)
running → completed       (end node completed)
running → failed          (unrecoverable node failure)
running → cancelled       (user cancellation)
running → paused          (user pause)
paused  → running         (user resume)
paused  → cancelled       (user cancel while paused)
```

**Allowed transitions (enforced at application level):**

| From | To |
|------|----|
| `pending` | `running` |
| `running` | `completed`, `failed`, `cancelled`, `paused` |
| `paused` | `running`, `cancelled` |

### 3.4 `node_runs`

Execution record for a single node within a workflow run.

```sql
CREATE TABLE node_runs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_run_id UUID NOT NULL REFERENCES workflow_runs(id) ON DELETE CASCADE,
    node_id         VARCHAR(255) NOT NULL,          -- matches node.id in DSL
    node_type       VARCHAR(50) NOT NULL,           -- matches node.type in DSL
    status          VARCHAR(20) NOT NULL DEFAULT 'pending',
    inputs          JSONB,                           -- resolved input values
    outputs         JSONB,                           -- output values after execution
    error           JSONB,                           -- error details if failed
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (workflow_run_id, node_id)
);

CREATE INDEX idx_nr_run_id ON node_runs (workflow_run_id);
CREATE INDEX idx_nr_status ON node_runs (workflow_run_id, status);
CREATE INDEX idx_nr_run_node ON node_runs (workflow_run_id, node_id);
```

**Status values:** `pending`, `running`, `completed`, `failed`, `skipped`, `waiting`

**State machine:**

```
pending  → running        (worker picks up task)
running  → completed      (successful execution)
running  → failed         (execution error)
running  → waiting        (human_input node awaiting input)
waiting  → running        (human input received, re-executing)
pending  → skipped        (branch not taken — if_else / cancelled run)
```

**Allowed transitions:**

| From | To |
|------|----|
| `pending` | `running`, `skipped` |
| `running` | `completed`, `failed`, `waiting` |
| `waiting` | `running` |

### 3.5 `run_events`

Ordered event log for a workflow run. Powers SSE streaming and audit trail.

```sql
CREATE TABLE run_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_run_id UUID NOT NULL REFERENCES workflow_runs(id) ON DELETE CASCADE,
    sequence        BIGINT NOT NULL,                 -- monotonic ordering per run
    event_type      VARCHAR(50) NOT NULL,
    node_id         VARCHAR(255),                    -- null for run-level events
    payload         JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (workflow_run_id, sequence)
);

CREATE INDEX idx_re_run_id ON run_events (workflow_run_id, sequence);
CREATE INDEX idx_re_type ON run_events (event_type);
```

**Event types (v1):**

| Event Type | Level | Payload |
|------------|-------|---------|
| `run_started` | run | `{inputs}` |
| `run_completed` | run | `{outputs}` |
| `run_failed` | run | `{error}` |
| `run_paused` | run | `{}` |
| `run_resumed` | run | `{}` |
| `run_cancelled` | run | `{}` |
| `node_started` | node | `{node_id, node_type}` |
| `node_completed` | node | `{node_id, node_type, outputs}` |
| `node_failed` | node | `{node_id, node_type, error}` |
| `node_waiting` | node | `{node_id, prompt, input_schema}` |
| `node_resumed` | node | `{node_id, input_data}` |

**Sequence generation:** Application-level counter per run (atomic increment in a transaction), not a DB sequence.

### 3.6 `webhook_triggers`

Webhook trigger definitions. Each has a unique key used as the URL path.

```sql
CREATE TABLE webhook_triggers (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_id     UUID NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
    key             VARCHAR(255) NOT NULL UNIQUE,    -- URL path segment (opaque UUID or slug)
    is_active       BOOLEAN NOT NULL DEFAULT true,
    input_mapping   JSONB NOT NULL DEFAULT '{}',     -- maps webhook payload fields to workflow inputs
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_wt_key ON webhook_triggers (key) WHERE is_active = true;
CREATE INDEX idx_wt_workflow ON webhook_triggers (workflow_id);
```

**`input_mapping` example:**

```json
{
  "order_id": "$.body.order.id",
  "priority": "$.body.priority"
}
```

Uses JSONPath-like syntax to extract values from the webhook payload. The `$` root represents the full webhook request context:
- `$.body` — parsed request body
- `$.headers` — request headers
- `$.query` — query parameters

### 3.7 `schedule_triggers`

Cron-based schedule trigger definitions.

```sql
CREATE TABLE schedule_triggers (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_id     UUID NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
    cron_expression VARCHAR(100) NOT NULL,           -- standard 5-field cron
    timezone        VARCHAR(50) NOT NULL DEFAULT 'UTC',
    is_active       BOOLEAN NOT NULL DEFAULT true,
    inputs          JSONB NOT NULL DEFAULT '{}',     -- static workflow inputs for each run
    next_fire_at    TIMESTAMPTZ,                     -- pre-computed next fire time
    last_fired_at   TIMESTAMPTZ,                     -- last successful fire time
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_st_next_fire ON schedule_triggers (next_fire_at) WHERE is_active = true;
CREATE INDEX idx_st_workflow ON schedule_triggers (workflow_id);
```

**Polling query (used by scheduler service):**

```sql
SELECT * FROM schedule_triggers
WHERE is_active = true
  AND next_fire_at <= now()
ORDER BY next_fire_at ASC
FOR UPDATE SKIP LOCKED;
```

`FOR UPDATE SKIP LOCKED` ensures:
- Multiple scheduler instances won't double-fire the same trigger.
- Already-locked triggers are skipped, not blocked on.

After processing:
```sql
UPDATE schedule_triggers
SET last_fired_at = now(),
    next_fire_at = <computed from cron_expression>,
    updated_at = now()
WHERE id = :id;
```

---

## 4. Indexes Summary

| Table | Index | Purpose |
|-------|-------|---------|
| `workflows` | `name` | Lookup by slug |
| `workflow_versions` | `(workflow_id)` | List versions |
| `workflow_versions` | `(workflow_id, is_published) WHERE published` | Find active version |
| `workflow_runs` | `(workflow_id)` | List runs per workflow |
| `workflow_runs` | `(status)` | Filter by status |
| `workflow_runs` | `(created_at DESC)` | Recent runs |
| `workflow_runs` | `(status) WHERE active` | Watchdog: find stalled runs |
| `node_runs` | `(workflow_run_id)` | List nodes per run |
| `node_runs` | `(workflow_run_id, status)` | Find running/pending nodes |
| `node_runs` | `(workflow_run_id, node_id)` | Lookup specific node |
| `run_events` | `(workflow_run_id, sequence)` | Ordered event stream |
| `run_events` | `(event_type)` | Filter by event type |
| `webhook_triggers` | `(key) WHERE active` | Webhook lookup |
| `schedule_triggers` | `(next_fire_at) WHERE active` | Scheduler polling |

---

## 5. Publishing Workflow

Publishing controls which version of a workflow is used for new runs.

```sql
-- Unpublish current version (within transaction)
UPDATE workflow_versions
SET is_published = false, updated_at = now()
WHERE workflow_id = :workflow_id AND is_published = true;

-- Publish target version
UPDATE workflow_versions
SET is_published = true, updated_at = now()
WHERE id = :version_id;
```

- Only published versions can be used to start new runs.
- Existing runs continue using their pinned `workflow_version_id` regardless of publishing changes.
- A workflow with no published version cannot be triggered (API returns 409).

---

## 6. Concurrency & Locking Patterns

### 6.1 Node Dispatch (Optimistic)

When a node completes, the dispatcher must determine next-ready nodes:

```sql
-- Within a transaction:
-- 1. Update completed node
UPDATE node_runs SET status = 'completed', outputs = :outputs, ... WHERE id = :id;

-- 2. Find candidate next nodes (edges from completed node)
-- 3. For each candidate, check all incoming edges are satisfied:
SELECT nr.node_id
FROM node_runs nr
WHERE nr.workflow_run_id = :run_id
  AND nr.node_id = :candidate_id
  AND nr.status = 'pending'
  AND NOT EXISTS (
    -- Any unsatisfied incoming edge
    SELECT 1 FROM edges_view e
    JOIN node_runs pred ON pred.node_id = e.source AND pred.workflow_run_id = :run_id
    WHERE e.target = :candidate_id
      AND pred.status NOT IN ('completed', 'skipped')
  );

-- 4. Update ready nodes to 'running', enqueue via Arq
```

The `FOR UPDATE` on the node_run row prevents race conditions when two upstream nodes complete simultaneously for a join node.

### 6.2 Scheduler (SKIP LOCKED)

See section 3.7 — `FOR UPDATE SKIP LOCKED` on `schedule_triggers`.

### 6.3 Run State Transitions (Optimistic Locking)

```sql
UPDATE workflow_runs
SET status = :new_status, updated_at = now()
WHERE id = :run_id AND status = :expected_current_status;
-- Check affected rows = 1; if 0, state changed underneath → retry or error
```

---

## 7. Data Retention & Cleanup

### MVP (v1)

No automatic cleanup. All data retained.

### Future

| Strategy | Mechanism |
|----------|-----------|
| Run TTL | Background job deletes runs older than configurable threshold |
| Event compaction | Archive events to cold storage after run completion |
| Soft delete | `deleted_at` column on workflows (cascade to versions, triggers) |

---

## 8. Migration Strategy

### Tool

**Alembic** (SQLAlchemy ecosystem, standard for FastAPI projects).

### Conventions

- Migrations are stored in `migrations/versions/`.
- Each migration has a human-readable slug: `001_initial_schema.py`, `002_add_loop_support.py`.
- Migrations are forward-only in production (no downgrade support required for MVP).
- All DDL runs in transactions (PostgreSQL default).

### Initial Migration

The tables defined in this spec constitute migration `001_initial_schema`. All tables are created in a single migration with proper foreign key ordering.

### Schema Evolution Rules

| Change Type | Approach |
|-------------|----------|
| Add nullable column | Simple `ALTER TABLE ADD COLUMN` |
| Add required column | Add nullable → backfill → set NOT NULL |
| Add index | `CREATE INDEX CONCURRENTLY` (non-blocking) |
| Modify JSONB structure | Application-level compat — old data still readable |
| Remove column | Deprecate in code first → remove in next major version |

---

## 9. Connection Management

| Setting | Value | Rationale |
|---------|-------|-----------|
| Pool size (API) | 10 | Matches default uvicorn workers |
| Pool size (Worker) | 5 per worker | Each worker handles one node at a time, but queries overlap |
| Pool size (Scheduler) | 2 | Minimal — only polling queries |
| Pool overflow | 5 | Burst handling |
| Async driver | `asyncpg` | Native async for FastAPI/Arq |
| ORM | None (raw SQL / SQLAlchemy Core) | Avoid ORM overhead for simple queries |

---

## 10. Open Questions

| Question | Status |
|----------|--------|
| Do we need a separate `edge_activations` table to track which edges fired during a run? | Deferred — reconstruct from node_runs + definition for v1 |
| Should `variable_pool` be a separate table instead of JSONB on `workflow_runs`? | JSONB is sufficient for MVP; separate table if pool grows large |
| Do we need `node_run` retry tracking (attempt count, per-attempt logs)? | Deferred — single attempt in v1 |
