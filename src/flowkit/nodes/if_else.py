"""If/else branching node executor — evaluates conditions to select a handle."""

from __future__ import annotations

import ast
import re
from typing import Any

from flowkit.definition.schema import IfElseConfig
from flowkit.nodes.base import NodeContext, NodeExecutor, NodeResult
from flowkit.runtime.state import NodeState

_REF_PATTERN = re.compile(r"\{\{([^}]+)\}\}")


class IfElseExecutor(NodeExecutor):
    """Evaluate conditions in order and return the handle of the first match."""

    async def execute(self, ctx: NodeContext) -> NodeResult:
        config = ctx.node_def.parsed_config()
        if not isinstance(config, IfElseConfig):
            return NodeResult(
                status=NodeState.FAILED,
                outputs={},
                error="Invalid or missing if_else node config",
            )

        pool = ctx.variable_pool

        for condition in config.conditions:
            try:
                if self._evaluate_expression(condition.expression, pool):
                    return NodeResult(
                        status=NodeState.COMPLETED,
                        outputs={},
                        next_handle=condition.id,
                    )
            except Exception as exc:
                return NodeResult(
                    status=NodeState.FAILED,
                    outputs={},
                    error=f"Error evaluating condition '{condition.id}': {exc}",
                )

        return NodeResult(
            status=NodeState.COMPLETED,
            outputs={},
            next_handle="else",
        )

    def _evaluate_expression(self, expression: str, pool: Any) -> bool:
        """Evaluate a simple comparison expression with variable references."""
        resolved = _REF_PATTERN.sub(
            lambda m: repr(pool.resolve_reference("{{" + m.group(1) + "}}")),
            expression,
        )

        safe_globals: dict[str, Any] = {"__builtins__": {}}
        safe_globals["true"] = True
        safe_globals["false"] = False
        safe_globals["null"] = None
        safe_globals["True"] = True
        safe_globals["False"] = False
        safe_globals["None"] = None

        result = eval(resolved, safe_globals)  # noqa: S307
        return bool(result)
