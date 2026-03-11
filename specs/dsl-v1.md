# Flowkit DSL v1 Specification

> Status: **Draft v1** · Date: 2026-03-11

## 1. Overview

The Flowkit DSL (Domain-Specific Language) defines the structure of a workflow as a directed graph of nodes connected by edges. The canonical serialization format is **JSON**. Definitions are immutable once published — edits create new versions.

### Design Goals

- **Declarative**: Describe *what* the workflow is, not *how* to execute it.
- **Statically validatable**: All structural errors caught before execution.
- **Serialization-agnostic internals**: Engine works with parsed Pydantic models, not raw JSON.
- **Extensible**: New node types can be added without changing the schema envelope.

---

## 2. Top-Level Schema

```json
{
  "version": "1.0",
  "metadata": {
    "name": "order-processing",
    "description": "Process incoming orders with approval gate"
  },
  "inputs": {
    "order_id": { "type": "string", "required": true },
    "priority": { "type": "string", "enum": ["low", "normal", "high"], "default": "normal" }
  },
  "outputs": {
    "result": { "type": "string" },
    "processed_at": { "type": "string" }
  },
  "nodes": [ ... ],
  "edges": [ ... ]
}
```

### Field Reference

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `version` | string | ✓ | DSL version. Must be `"1.0"` for this spec. |
| `metadata` | object | ✓ | Human-readable workflow metadata. |
| `metadata.name` | string | ✓ | Unique workflow name (slug format: `[a-z0-9-]+`). |
| `metadata.description` | string | | Optional description. |
| `inputs` | object | | Workflow-level input parameter definitions. Keys are parameter names. |
| `outputs` | object | | Workflow-level output declarations. Populated by the `end` node. |
| `nodes` | array | ✓ | List of node definitions. Minimum 2 (start + end). |
| `edges` | array | ✓ | List of edge definitions connecting nodes. |

---

## 3. Variable Type System

DSL v1 supports a minimal type system for inputs, outputs, and variable declarations.

### Supported Types

| Type | JSON Representation | Description |
|------|---------------------|-------------|
| `string` | `"hello"` | UTF-8 string |
| `number` | `42`, `3.14` | Integer or float |
| `boolean` | `true`, `false` | Boolean |
| `object` | `{...}` | Arbitrary JSON object |
| `array` | `[...]` | JSON array |
| `any` | any | No type constraint |

### Variable Declaration Schema

```json
{
  "type": "string",
  "required": true,
  "default": "fallback_value",
  "description": "Human-readable description"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | ✓ | One of the supported types. |
| `required` | boolean | | Default `false`. If `true`, must be provided at run start. |
| `default` | any | | Default value if not provided. Must match declared type. |
| `enum` | array | | Allowed values (only for `string` and `number`). |
| `description` | string | | Human-readable description. |

---

## 4. Variable References

Nodes reference upstream outputs and workflow inputs using a template syntax within string values:

```
{{workflow.input.order_id}}
{{nodes.fetch_order.output.status}}
{{nodes.check_stock.output.available}}
```

### Reference Grammar

```
reference     = "{{" path "}}"
path          = scope "." identifier ("." identifier)*
scope         = "workflow" | "nodes"
identifier    = [a-zA-Z_][a-zA-Z0-9_]*
```

### Scope Resolution

| Pattern | Resolves To |
|---------|-------------|
| `workflow.input.<name>` | Workflow-level input parameter |
| `workflow.output.<name>` | Workflow-level output (write-only in end node) |
| `nodes.<node_id>.output.<name>` | Output of a previously completed node |

**Rules:**
- References are resolved at node execution time, not at definition time.
- Referencing a node that hasn't completed yet is a runtime error.
- Circular references are prevented by the DAG constraint (no cycles).
- References can appear in any string-typed field within `node.config`.

---

## 5. Node Definition

```json
{
  "id": "fetch_order",
  "type": "http",
  "label": "Fetch Order Details",
  "config": {
    "method": "GET",
    "url": "https://api.example.com/orders/{{workflow.input.order_id}}",
    "headers": { "Authorization": "Bearer {{workflow.input.api_token}}" },
    "timeout": 30
  },
  "position": { "x": 200, "y": 100 }
}
```

### Common Fields (All Node Types)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | ✓ | Unique within the workflow. Format: `[a-z0-9_]+`. |
| `type` | string | ✓ | Node type identifier. Must be a registered type. |
| `label` | string | | Human-readable display name. |
| `config` | object | | Type-specific configuration. Schema varies per node type. |
| `position` | object | | UI position hint `{x, y}`. Ignored by engine. |

---

## 6. Node Type Catalog (MVP)

### 6.1 `start`

Entry point of the workflow. Exactly one per workflow. Receives workflow inputs and passes them downstream.

**Config:** None.

**Outputs:** All workflow inputs are available as outputs of the start node.

**Constraints:**
- Must have zero incoming edges.
- Must have exactly one outgoing edge.
- Exactly one `start` node per workflow.

```json
{ "id": "start", "type": "start" }
```

### 6.2 `end`

Terminal node. Maps node inputs to workflow outputs. Exactly one per workflow.

**Config:**

```json
{
  "output_mapping": {
    "result": "{{nodes.process.output.result}}",
    "processed_at": "{{nodes.process.output.timestamp}}"
  }
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `output_mapping` | object | | Maps workflow output names to variable references. |

**Constraints:**
- Must have zero outgoing edges.
- Must have at least one incoming edge.
- Exactly one `end` node per workflow.

### 6.3 `http`

Makes an HTTP request to an external service.

**Config:**

```json
{
  "method": "POST",
  "url": "https://api.example.com/process",
  "headers": { "Content-Type": "application/json" },
  "body": "{\"order_id\": \"{{workflow.input.order_id}}\"}",
  "timeout": 30,
  "retry": { "max_attempts": 3, "backoff": "exponential" }
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `method` | string | ✓ | | HTTP method: GET, POST, PUT, PATCH, DELETE |
| `url` | string | ✓ | | Request URL. Supports variable references. |
| `headers` | object | | `{}` | Request headers. Values support variable references. |
| `body` | string\|object | | | Request body. String for raw, object for JSON. |
| `timeout` | number | | `30` | Request timeout in seconds. |
| `retry` | object | | | Retry policy. |
| `retry.max_attempts` | number | | `1` | Max retry attempts (1 = no retry). |
| `retry.backoff` | string | | `"fixed"` | `"fixed"` or `"exponential"`. |

**Outputs:**

| Key | Type | Description |
|-----|------|-------------|
| `status_code` | number | HTTP response status code |
| `headers` | object | Response headers |
| `body` | any | Parsed response body (JSON if content-type matches, else string) |

### 6.4 `code`

Executes a user-provided Python code snippet.

**Config:**

```json
{
  "language": "python",
  "source": "result = inputs['value'] * 2\nreturn {'doubled': result}",
  "inputs": {
    "value": "{{nodes.fetch.output.amount}}"
  }
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `language` | string | ✓ | Must be `"python"` in v1. |
| `source` | string | ✓ | Code to execute. Must return a dict. |
| `inputs` | object | | Named inputs passed to the code as the `inputs` dict. Values support variable references. |

**Execution model (v1):**
- Code runs in-process via `exec()` with a restricted global scope.
- Available in scope: `inputs` (dict), standard builtins (no `__import__`, no `open`, no `os`, no `sys`).
- Must return a dict by assigning to `return` or calling `return {...}` from a wrapped function.
- Timeout: 30s default, configurable.

**Outputs:** The dict returned by the code snippet. All keys become named outputs.

**Security note:** v1 runs code in-process with restricted builtins. NOT suitable for untrusted code. Sandbox (subprocess/container) planned for v2.

### 6.5 `if_else`

Conditional branching. Evaluates a condition and activates one of two outgoing edges.

**Config:**

```json
{
  "conditions": [
    {
      "id": "high_priority",
      "expression": "{{nodes.fetch.output.priority}} == 'high'"
    }
  ]
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `conditions` | array | ✓ | Ordered list of conditions. First match wins. |
| `conditions[].id` | string | ✓ | Condition identifier, referenced by edge `source_handle`. |
| `conditions[].expression` | string | ✓ | Boolean expression. Supports variable references and basic operators. |

**Expression language (v1):** Simple comparisons only — no function calls, no complex logic.
- Operators: `==`, `!=`, `>`, `<`, `>=`, `<=`, `in`, `not in`
- Boolean combinators: `and`, `or`, `not`
- Literal values: strings (single-quoted), numbers, `true`, `false`, `null`

**Edge model:** The `if_else` node uses `source_handle` on edges to route:
- Each condition's `id` is a handle (e.g., `"high_priority"`)
- A special handle `"else"` is activated when no conditions match

**Outputs:** None (branching only).

### 6.6 `loop`

Iterates over an array, executing a sub-path for each item.

**Config:**

```json
{
  "items": "{{nodes.fetch.output.orders}}",
  "item_variable": "current_order",
  "index_variable": "loop_index",
  "max_iterations": 100
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `items` | string | ✓ | | Variable reference resolving to an array. |
| `item_variable` | string | | `"item"` | Variable name for the current item. |
| `index_variable` | string | | `"index"` | Variable name for the current index. |
| `max_iterations` | number | | `100` | Safety limit. |

**Execution model:**
- The loop node itself iterates. For each item, it sets `item_variable` and `index_variable` in the variable pool, then executes its connected sub-path.
- Sub-path: The nodes connected via the `"body"` handle of the loop, terminating at a node connected back to the loop's `"done"` handle.
- After all iterations complete, execution continues via the `"completed"` edge.

**Outputs:**

| Key | Type | Description |
|-----|------|-------------|
| `results` | array | Collected outputs from each iteration's terminal node. |
| `count` | number | Total iterations executed. |

### 6.7 `human_input`

Pauses execution and waits for external human input via the API.

**Config:**

```json
{
  "prompt": "Please approve order {{workflow.input.order_id}}",
  "input_schema": {
    "approved": { "type": "boolean", "required": true },
    "comment": { "type": "string" }
  },
  "timeout": 86400
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `prompt` | string | ✓ | | Message shown to the human operator. |
| `input_schema` | object | | | Expected input fields. Same format as workflow input declarations. |
| `timeout` | number | | `86400` | Seconds to wait before timing out (default 24h). |

**Execution model:**
1. Node enters `waiting` status.
2. An event is emitted: `human_input_required` with the prompt and schema.
3. Execution pauses at this node (other parallel branches may continue).
4. External system calls `POST /runs/{id}/nodes/{node_id}/input` with the required data.
5. Node resumes, input data becomes the node's outputs.
6. If timeout expires, node fails with `timeout` error.

**Outputs:** The submitted input data. Keys match `input_schema` field names.

---

## 7. Edge Definition

```json
{
  "id": "e1",
  "source": "fetch_order",
  "target": "check_stock",
  "source_handle": "default",
  "target_handle": "default"
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `id` | string | ✓ | | Unique within the workflow. |
| `source` | string | ✓ | | Source node `id`. |
| `target` | string | ✓ | | Target node `id`. |
| `source_handle` | string | | `"default"` | Output handle on the source node (for branching). |
| `target_handle` | string | | `"default"` | Input handle on the target node. |

### Handle Semantics

Most nodes have a single `"default"` output handle. Special cases:

| Node Type | Output Handles |
|-----------|---------------|
| `start` | `default` |
| `end` | *(none — terminal)* |
| `http` | `default` |
| `code` | `default` |
| `if_else` | One per condition `id` + `else` |
| `loop` | `body` (sub-path), `completed` (after loop) |
| `human_input` | `default` |

---

## 8. Validation Rules

The following rules MUST pass before a workflow definition is accepted.

### 8.1 Structural Rules

| Rule | Error Code | Description |
|------|------------|-------------|
| V-001 | `missing_start` | Exactly one node with `type: "start"` must exist. |
| V-002 | `missing_end` | Exactly one node with `type: "end"` must exist. |
| V-003 | `duplicate_node_id` | All node `id` values must be unique. |
| V-004 | `duplicate_edge_id` | All edge `id` values must be unique. |
| V-005 | `unknown_node_ref` | Edge `source` and `target` must reference existing node `id`s. |
| V-006 | `orphan_node` | Every node must have at least one edge (incoming or outgoing), except in degenerate start→end case. |
| V-007 | `start_has_incoming` | Start node must have zero incoming edges. |
| V-008 | `end_has_outgoing` | End node must have zero outgoing edges. |

### 8.2 Graph Rules

| Rule | Error Code | Description |
|------|------------|-------------|
| V-010 | `cycle_detected` | The graph must be a DAG (no cycles). Exception: loop body back-edges are allowed. |
| V-011 | `unreachable_node` | All nodes must be reachable from the start node. |
| V-012 | `no_path_to_end` | All non-loop-body paths must reach the end node. |

### 8.3 Type Rules

| Rule | Error Code | Description |
|------|------------|-------------|
| V-020 | `unknown_node_type` | Node `type` must be a registered node type. |
| V-021 | `invalid_config` | Node `config` must match the schema for its type. |
| V-022 | `invalid_handle` | Edge `source_handle` must be valid for the source node type. |
| V-023 | `invalid_variable_ref` | Variable references must follow the grammar and reference valid paths. |
| V-024 | `input_type_mismatch` | Default values must match declared types. |
| V-025 | `missing_required_input` | Required workflow inputs must not have undefined references. |

### 8.4 Semantic Rules

| Rule | Error Code | Description |
|------|------------|-------------|
| V-030 | `if_else_missing_else` | `if_else` nodes should have an `else` edge (warning, not error). |
| V-031 | `loop_missing_body` | `loop` nodes must have a `body` handle edge. |
| V-032 | `loop_missing_completed` | `loop` nodes must have a `completed` handle edge. |

---

## 9. Complete Example

```json
{
  "version": "1.0",
  "metadata": {
    "name": "order-approval",
    "description": "Fetch order, check priority, route to approval if high"
  },
  "inputs": {
    "order_id": { "type": "string", "required": true },
    "api_token": { "type": "string", "required": true }
  },
  "outputs": {
    "status": { "type": "string" },
    "approved": { "type": "boolean" }
  },
  "nodes": [
    { "id": "start", "type": "start" },
    {
      "id": "fetch_order",
      "type": "http",
      "label": "Fetch Order",
      "config": {
        "method": "GET",
        "url": "https://api.example.com/orders/{{workflow.input.order_id}}",
        "headers": { "Authorization": "Bearer {{workflow.input.api_token}}" }
      }
    },
    {
      "id": "check_priority",
      "type": "if_else",
      "label": "High Priority?",
      "config": {
        "conditions": [
          { "id": "is_high", "expression": "{{nodes.fetch_order.output.body.priority}} == 'high'" }
        ]
      }
    },
    {
      "id": "approve",
      "type": "human_input",
      "label": "Manager Approval",
      "config": {
        "prompt": "Approve high-priority order {{workflow.input.order_id}}?",
        "input_schema": {
          "approved": { "type": "boolean", "required": true },
          "comment": { "type": "string" }
        }
      }
    },
    {
      "id": "auto_approve",
      "type": "code",
      "label": "Auto Approve",
      "config": {
        "language": "python",
        "source": "return {'approved': True, 'comment': 'Auto-approved (normal priority)'}",
        "inputs": {}
      }
    },
    {
      "id": "end",
      "type": "end",
      "config": {
        "output_mapping": {
          "status": "completed",
          "approved": "{{nodes.approve.output.approved}}"
        }
      }
    }
  ],
  "edges": [
    { "id": "e1", "source": "start", "target": "fetch_order" },
    { "id": "e2", "source": "fetch_order", "target": "check_priority" },
    { "id": "e3", "source": "check_priority", "target": "approve", "source_handle": "is_high" },
    { "id": "e4", "source": "check_priority", "target": "auto_approve", "source_handle": "else" },
    { "id": "e5", "source": "approve", "target": "end" },
    { "id": "e6", "source": "auto_approve", "target": "end" }
  ]
}
```

---

## 10. Versioning Strategy

- The `version` field tracks DSL schema versions (not workflow content versions).
- Workflow content versioning is handled at the persistence layer (see `specs/persistence.md`).
- DSL v1 is forward-compatible: unknown fields in `config` are preserved but ignored.
- Breaking changes to the envelope (nodes/edges structure) require a version bump to `"2.0"`.
