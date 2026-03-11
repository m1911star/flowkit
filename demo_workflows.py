#!/usr/bin/env python3
"""
Flowkit Demo — Execute 3 workflow patterns and print state transitions.

Workflows:
  1. Linear Pipeline:  start → compute → format → end
  2. Branching:        start → if_else → [pass | fail] → end
  3. Human-in-Loop:    start → calc → human_approval → process → end

Usage:
    uv run python demo_workflows.py
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import create_async_engine

from flowkit.definition.loader import load_dict
from flowkit.engine.graph import Graph
from flowkit.nodes.base import NodeContext, NodeResult
from flowkit.nodes.registry import get_executor
from flowkit.persistence.models import metadata
from flowkit.persistence.repos import (
    NodeRunRepo,
    RunEventRepo,
    WorkflowRepo,
    WorkflowRunRepo,
    WorkflowVersionRepo,
)
from flowkit.runtime.state import NodeState, RunState
from flowkit.runtime.variable_pool import VariablePool
from flowkit.streaming.emitter import (
    NODE_COMPLETED,
    NODE_FAILED,
    NODE_STARTED,
    NODE_WAITING,
    RUN_COMPLETED,
    RUN_FAILED,
    RUN_PAUSED,
    RUN_STARTED,
    EventEmitter,
)

# ─── Pretty Printing ───────────────────────────────────────────────

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"
CYAN = "\033[36m"
WHITE = "\033[37m"
BG_GREEN = "\033[42m"
BG_RED = "\033[41m"
BG_YELLOW = "\033[43m"
BG_BLUE = "\033[44m"

STATE_ICONS = {
    "pending": f"{DIM}⏳{RESET}",
    "running": f"{BLUE}▶{RESET}",
    "completed": f"{GREEN}✅{RESET}",
    "failed": f"{RED}❌{RESET}",
    "waiting": f"{YELLOW}⏸{RESET}",
    "paused": f"{YELLOW}⏸{RESET}",
    "cancelled": f"{RED}🚫{RESET}",
    "skipped": f"{DIM}⏭{RESET}",
}

EVENT_COLORS = {
    RUN_STARTED: CYAN,
    RUN_COMPLETED: GREEN,
    RUN_FAILED: RED,
    RUN_PAUSED: YELLOW,
    NODE_STARTED: BLUE,
    NODE_COMPLETED: GREEN,
    NODE_FAILED: RED,
    NODE_WAITING: YELLOW,
}


def banner(title: str, subtitle: str = "") -> None:
    width = 60
    print(f"\n{'═' * width}")
    print(f"{BOLD}{MAGENTA}  {title}{RESET}")
    if subtitle:
        print(f"{DIM}  {subtitle}{RESET}")
    print(f"{'═' * width}")


def log_state(
    timestamp: str, entity: str, old_state: str, new_state: str, detail: str = ""
) -> None:
    icon = STATE_ICONS.get(new_state, "?")
    color = (
        GREEN
        if new_state == "completed"
        else RED
        if new_state == "failed"
        else YELLOW
        if new_state in ("waiting", "paused")
        else BLUE
        if new_state == "running"
        else ""
    )
    detail_str = f"  {DIM}→ {detail}{RESET}" if detail else ""
    print(
        f"  {DIM}{timestamp}{RESET}  {icon} {BOLD}{entity:<20}{RESET}  {old_state:>10} → {color}{new_state:<10}{RESET}{detail_str}"
    )


def log_event(event_type: str, node_id: str | None = None, payload: dict | None = None) -> None:
    color = EVENT_COLORS.get(event_type, WHITE)
    node_str = f" [{node_id}]" if node_id else ""
    payload_str = f"  {DIM}{payload}{RESET}" if payload else ""
    print(f"  {color}📡 {event_type}{node_str}{RESET}{payload_str}")


def print_result_table(title: str, data: dict) -> None:
    print(f"\n  {BOLD}{title}{RESET}")
    for k, v in data.items():
        print(f"    {CYAN}{k:<20}{RESET} = {v}")


# ─── DSL Definitions ───────────────────────────────────────────────

FLOW1_LINEAR = {
    "version": "1.0",
    "metadata": {"name": "linear-pipeline", "description": "Compute a*b+c, then format result"},
    "inputs": {
        "a": {"type": "number", "required": True},
        "b": {"type": "number", "required": True},
        "c": {"type": "number", "required": True},
    },
    "outputs": {"message": {"type": "string"}},
    "nodes": [
        {"id": "start_1", "type": "start", "config": {}},
        {
            "id": "compute",
            "type": "code",
            "config": {
                "language": "python",
                "source": "result = {'value': a * b + c}",
                "inputs": {
                    "a": "{{workflow.input.a}}",
                    "b": "{{workflow.input.b}}",
                    "c": "{{workflow.input.c}}",
                },
            },
        },
        {
            "id": "format",
            "type": "code",
            "config": {
                "language": "python",
                "source": "result = {'message': f'{a} × {b} + {c} = {value}'}",
                "inputs": {
                    "a": "{{workflow.input.a}}",
                    "b": "{{workflow.input.b}}",
                    "c": "{{workflow.input.c}}",
                    "value": "{{nodes.compute.output.value}}",
                },
            },
        },
        {
            "id": "end_1",
            "type": "end",
            "config": {
                "output_mapping": {"message": "{{nodes.format.output.message}}"},
            },
        },
    ],
    "edges": [
        {"id": "e1", "source": "start_1", "target": "compute"},
        {"id": "e2", "source": "compute", "target": "format"},
        {"id": "e3", "source": "format", "target": "end_1"},
    ],
}

FLOW2_BRANCHING = {
    "version": "1.0",
    "metadata": {"name": "score-checker", "description": "Branch based on score >= 60"},
    "inputs": {"score": {"type": "number", "required": True}},
    "outputs": {"verdict": {"type": "string"}},
    "nodes": [
        {"id": "start_1", "type": "start", "config": {}},
        {
            "id": "check",
            "type": "if_else",
            "config": {
                "conditions": [
                    {"id": "pass", "expression": "{{nodes.start_1.output.score}} >= 60"},
                ],
            },
        },
        {
            "id": "pass_node",
            "type": "code",
            "config": {
                "language": "python",
                "source": "result = {'verdict': f'Score {score}: PASS ✅ Congratulations!'}",
                "inputs": {"score": "{{workflow.input.score}}"},
            },
        },
        {
            "id": "fail_node",
            "type": "code",
            "config": {
                "language": "python",
                "source": "result = {'verdict': f'Score {score}: FAIL ❌ Try again!'}",
                "inputs": {"score": "{{workflow.input.score}}"},
            },
        },
        {
            "id": "end_1",
            "type": "end",
            "config": {
                "output_mapping": {"verdict": "{{nodes.{branch}.output.verdict}}"},
            },
        },
    ],
    "edges": [
        {"id": "e1", "source": "start_1", "target": "check"},
        {"id": "e2", "source": "check", "target": "pass_node", "source_handle": "pass"},
        {"id": "e3", "source": "check", "target": "fail_node", "source_handle": "else"},
        {"id": "e4", "source": "pass_node", "target": "end_1"},
        {"id": "e5", "source": "fail_node", "target": "end_1"},
    ],
}

FLOW3_HUMAN_IN_LOOP = {
    "version": "1.0",
    "metadata": {"name": "order-approval", "description": "Order with human approval step"},
    "inputs": {
        "item": {"type": "string", "required": True},
        "quantity": {"type": "number", "required": True},
        "unit_price": {"type": "number", "required": True},
    },
    "outputs": {"confirmation": {"type": "string"}},
    "nodes": [
        {"id": "start_1", "type": "start", "config": {}},
        {
            "id": "calc",
            "type": "code",
            "config": {
                "language": "python",
                "source": "result = {'total': quantity * unit_price, 'summary': f'{quantity}x {item} @ ${unit_price} = ${quantity * unit_price}'}",
                "inputs": {
                    "item": "{{workflow.input.item}}",
                    "quantity": "{{workflow.input.quantity}}",
                    "unit_price": "{{workflow.input.unit_price}}",
                },
            },
        },
        {
            "id": "approve",
            "type": "human_input",
            "config": {
                "prompt": "Please approve this order: {{nodes.calc.output.summary}}",
                "input_schema": {"approved": {"type": "boolean"}},
            },
        },
        {
            "id": "process",
            "type": "code",
            "config": {
                "language": "python",
                "source": "result = {'confirmation': f'Order confirmed: {summary}. Approved={approved}'}",
                "inputs": {
                    "summary": "{{nodes.calc.output.summary}}",
                    "approved": "{{nodes.approve.output.approved}}",
                },
            },
        },
        {
            "id": "end_1",
            "type": "end",
            "config": {
                "output_mapping": {
                    "confirmation": "{{nodes.process.output.confirmation}}",
                },
            },
        },
    ],
    "edges": [
        {"id": "e1", "source": "start_1", "target": "calc"},
        {"id": "e2", "source": "calc", "target": "approve"},
        {"id": "e3", "source": "approve", "target": "process"},
        {"id": "e4", "source": "process", "target": "end_1"},
    ],
}


# ─── Execution Engine ──────────────────────────────────────────────


async def execute_flow(
    conn,
    definition_dict: dict,
    inputs: dict,
    *,
    flow_name: str,
    pause_callback=None,
) -> tuple[str, dict, VariablePool]:
    """Execute a workflow and print state transitions in real time."""
    definition = load_dict(definition_dict)
    graph = Graph(definition)
    pool = VariablePool()
    pool.set_workflow_inputs(inputs)

    workflow_repo = WorkflowRepo()
    version_repo = WorkflowVersionRepo()
    run_repo = WorkflowRunRepo()
    node_run_repo = NodeRunRepo()
    event_repo = RunEventRepo()
    emitter = EventEmitter(event_repo)

    # Create workflow + version + run in DB
    wf = await workflow_repo.create(conn, name=flow_name, description="")
    import json

    ver = await version_repo.create(
        conn,
        workflow_id=wf["id"],
        version=1,
        definition=definition_dict,
        checksum="demo",
        is_published=True,
    )
    run = await run_repo.create(
        conn,
        workflow_id=wf["id"],
        workflow_version_id=ver["id"],
        inputs=inputs,
    )
    run_id = run["id"]

    def ts() -> str:
        return datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3]

    # Start run
    await run_repo.update_status(
        conn, run_id, status=RunState.RUNNING.value, expected_status=RunState.PENDING.value
    )
    await emitter.emit(conn, run_id, RUN_STARTED)
    log_state(ts(), f"Run({str(run_id)[:8]})", "pending", "running")
    log_event(RUN_STARTED)

    completed: set[str] = set()
    paused_node: str | None = None

    while True:
        ready = graph.find_ready_nodes(completed)
        if not ready:
            break

        for node_id in ready:
            node_def = graph.get_node(node_id)

            # Create node run
            nr = await node_run_repo.create(
                conn, workflow_run_id=run_id, node_id=node_id, node_type=node_def.type.value
            )
            nr_id = nr["id"]

            # Mark running
            await node_run_repo.update_status(conn, nr_id, status=NodeState.RUNNING.value)
            await emitter.emit(conn, run_id, NODE_STARTED, node_id=node_id)
            log_state(
                ts(), f"  Node({node_id})", "pending", "running", f"type={node_def.type.value}"
            )

            # Execute
            executor = get_executor(node_def.type)
            ctx = NodeContext(
                node_def=node_def,
                variable_pool=pool,
                run_id=run_id,
                node_run_id=nr_id,
            )
            result = await executor.execute(ctx)

            if result.status == NodeState.WAITING:
                await node_run_repo.update_status(conn, nr_id, status=NodeState.WAITING.value)
                await emitter.emit(conn, run_id, NODE_WAITING, node_id=node_id)
                log_state(
                    ts(), f"  Node({node_id})", "running", "waiting", "⏸ human input required"
                )

                await run_repo.update_status(conn, run_id, status=RunState.PAUSED.value)
                await emitter.emit(conn, run_id, RUN_PAUSED)
                log_state(ts(), f"Run({str(run_id)[:8]})", "running", "paused")
                log_event(RUN_PAUSED)

                # Simulate human providing input
                if pause_callback:
                    print(
                        f"\n  {YELLOW}{BOLD}  ⏸  WORKFLOW PAUSED — awaiting human input...{RESET}"
                    )
                    human_inputs = pause_callback()
                    print(f"  {GREEN}{BOLD}  ▶  Human provided: {human_inputs}{RESET}\n")

                    # Resume
                    pool.set_node_outputs(node_id, human_inputs)
                    await node_run_repo.update_status(
                        conn, nr_id, status=NodeState.COMPLETED.value, outputs=human_inputs
                    )
                    await emitter.emit(conn, run_id, NODE_COMPLETED, node_id=node_id)
                    log_state(
                        ts(),
                        f"  Node({node_id})",
                        "waiting",
                        "completed",
                        f"outputs={human_inputs}",
                    )

                    await run_repo.update_status(
                        conn,
                        run_id,
                        status=RunState.RUNNING.value,
                        expected_status=RunState.PAUSED.value,
                    )
                    log_state(ts(), f"Run({str(run_id)[:8]})", "paused", "running", "resumed")
                    completed.add(node_id)
                    continue
                else:
                    paused_node = node_id
                    return "paused", {}, pool

            if result.status == NodeState.FAILED:
                await node_run_repo.update_status(
                    conn, nr_id, status=NodeState.FAILED.value, error=result.error
                )
                await emitter.emit(
                    conn, run_id, NODE_FAILED, node_id=node_id, payload={"error": result.error}
                )
                log_state(ts(), f"  Node({node_id})", "running", "failed", f"error={result.error}")

                await run_repo.update_status(conn, run_id, status=RunState.FAILED.value)
                await emitter.emit(conn, run_id, RUN_FAILED)
                log_state(ts(), f"Run({str(run_id)[:8]})", "running", "failed")
                return "failed", {}, pool

            # Completed
            pool.set_node_outputs(node_id, result.outputs)
            await node_run_repo.update_status(
                conn, nr_id, status=NodeState.COMPLETED.value, outputs=result.outputs
            )
            await emitter.emit(conn, run_id, NODE_COMPLETED, node_id=node_id)

            detail = f"outputs={result.outputs}"
            if result.next_handle != "default":
                detail += f"  handle={result.next_handle}"
            log_state(ts(), f"  Node({node_id})", "running", "completed", detail)

            # For if_else branching: only follow the chosen handle
            if node_def.type.value == "if_else":
                chosen_handle = result.next_handle
                successors = graph.get_outgoing_edges(node_id)
                for edge in successors:
                    if edge.source_handle == chosen_handle:
                        # This successor should run
                        pass
                    else:
                        # Skip the other branch
                        other_node_id = edge.target
                        completed.add(other_node_id)
                        log_state(
                            ts(),
                            f"  Node({other_node_id})",
                            "pending",
                            "skipped",
                            f"branch not taken",
                        )

            completed.add(node_id)

    # Complete
    await run_repo.update_status(conn, run_id, status=RunState.COMPLETED.value)
    await emitter.emit(conn, run_id, RUN_COMPLETED)
    log_state(ts(), f"Run({str(run_id)[:8]})", "running", "completed")
    log_event(RUN_COMPLETED)

    final_outputs = pool.to_dict()
    return "completed", final_outputs, pool


# ─── Main ──────────────────────────────────────────────────────────


async def main() -> None:
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)

    # ── Flow 1: Linear Pipeline ──────────────────────────────────
    banner(
        "Flow 1: Linear Pipeline",
        "start → compute(a×b+c) → format(message) → end",
    )
    inputs1 = {"a": 7, "b": 6, "c": 8}
    print(f"\n  {BOLD}Inputs:{RESET}  a={inputs1['a']}, b={inputs1['b']}, c={inputs1['c']}")
    print(f"  {DIM}Expected: 7 × 6 + 8 = 50{RESET}\n")

    async with engine.begin() as conn:
        status, outputs, pool = await execute_flow(
            conn, FLOW1_LINEAR, inputs1, flow_name="Linear Pipeline"
        )

    print_result_table(
        "Final Outputs",
        {
            "status": f"{GREEN}{status}{RESET}",
            "message": pool.get_node_output("format", "message")
            if status == "completed"
            else "N/A",
        },
    )

    # ── Flow 2: Branching (PASS case) ────────────────────────────
    banner(
        "Flow 2a: Branching — Score 85 (PASS)",
        "start → if_else(score>=60?) → pass_node → end",
    )
    # Fix the end node output_mapping dynamically for branching
    flow2_pass = _make_branch_flow(85, "pass_node")
    print(f"\n  {BOLD}Inputs:{RESET}  score=85")
    print(f"  {DIM}Expected: PASS branch{RESET}\n")

    async with engine.begin() as conn:
        status, outputs, pool = await execute_flow(
            conn, flow2_pass, {"score": 85}, flow_name="Score Check PASS"
        )

    print_result_table(
        "Final Outputs",
        {
            "status": f"{GREEN}{status}{RESET}",
            "verdict": pool.get_node_output("pass_node", "verdict")
            if status == "completed"
            else "N/A",
        },
    )

    # ── Flow 2: Branching (FAIL case) ────────────────────────────
    banner(
        "Flow 2b: Branching — Score 42 (FAIL)",
        "start → if_else(score>=60?) → fail_node → end",
    )
    flow2_fail = _make_branch_flow(42, "fail_node")
    print(f"\n  {BOLD}Inputs:{RESET}  score=42")
    print(f"  {DIM}Expected: FAIL branch{RESET}\n")

    async with engine.begin() as conn:
        status, outputs, pool = await execute_flow(
            conn, flow2_fail, {"score": 42}, flow_name="Score Check FAIL"
        )

    print_result_table(
        "Final Outputs",
        {
            "status": f"{GREEN}{status}{RESET}",
            "verdict": pool.get_node_output("fail_node", "verdict")
            if status == "completed"
            else "N/A",
        },
    )

    # ── Flow 3: Human-in-the-Loop ────────────────────────────────
    banner(
        "Flow 3: Human-in-the-Loop (Order Approval)",
        "start → calc → ⏸ human_approval → process → end",
    )
    inputs3 = {"item": "MacBook Pro", "quantity": 3, "unit_price": 2499}
    print(
        f"\n  {BOLD}Inputs:{RESET}  item={inputs3['item']}, qty={inputs3['quantity']}, price=${inputs3['unit_price']}"
    )
    print(f"  {DIM}Expected: pause at approval, then resume{RESET}\n")

    def human_approves():
        return {"approved": True}

    async with engine.begin() as conn:
        status, outputs, pool = await execute_flow(
            conn,
            FLOW3_HUMAN_IN_LOOP,
            inputs3,
            flow_name="Order Approval",
            pause_callback=human_approves,
        )

    print_result_table(
        "Final Outputs",
        {
            "status": f"{GREEN}{status}{RESET}",
            "confirmation": pool.get_node_output("process", "confirmation")
            if status == "completed"
            else "N/A",
        },
    )

    # ── Summary ──────────────────────────────────────────────────
    print(f"\n{'═' * 60}")
    print(f"{BOLD}{GREEN}  All 4 workflow executions completed successfully! 🎉{RESET}")
    print(f"{'═' * 60}\n")

    await engine.dispose()


def _make_branch_flow(score: int, expected_branch: str) -> dict:
    """Build a branching flow with proper end node output_mapping."""
    import copy

    flow = copy.deepcopy(FLOW2_BRANCHING)
    # Fix end node to reference whichever branch actually runs
    # We'll use a dynamic approach: both branches write to same key
    flow["nodes"][4]["config"]["output_mapping"] = {
        "verdict": f"{{{{nodes.{expected_branch}.output.verdict}}}}"
    }
    return flow


if __name__ == "__main__":
    asyncio.run(main())
