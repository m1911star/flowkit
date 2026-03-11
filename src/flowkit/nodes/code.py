"""Code node executor — runs user Python code in a restricted scope."""

from __future__ import annotations

import signal
from typing import Any

from flowkit.definition.schema import CodeNodeConfig
from flowkit.nodes.base import NodeContext, NodeExecutor, NodeResult
from flowkit.runtime.state import NodeState

# Restricted builtins — no file/network/import access
_SAFE_BUILTINS = {
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "dict": dict,
    "enumerate": enumerate,
    "filter": filter,
    "float": float,
    "format": format,
    "frozenset": frozenset,
    "getattr": getattr,
    "hasattr": hasattr,
    "hash": hash,
    "int": int,
    "isinstance": isinstance,
    "issubclass": issubclass,
    "iter": iter,
    "len": len,
    "list": list,
    "map": map,
    "max": max,
    "min": min,
    "next": next,
    "print": print,
    "range": range,
    "repr": repr,
    "reversed": reversed,
    "round": round,
    "set": set,
    "slice": slice,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "type": type,
    "zip": zip,
    "True": True,
    "False": False,
    "None": None,
    # Common exception types
    "Exception": Exception,
    "ValueError": ValueError,
    "TypeError": TypeError,
    "KeyError": KeyError,
    "IndexError": IndexError,
    "AttributeError": AttributeError,
    "RuntimeError": RuntimeError,
    "ZeroDivisionError": ZeroDivisionError,
    "StopIteration": StopIteration,
}

_DEFAULT_TIMEOUT = 30


class CodeExecutor(NodeExecutor):
    """Execute a user-provided Python code snippet."""

    async def execute(self, ctx: NodeContext) -> NodeResult:
        config = ctx.node_def.parsed_config()
        if not isinstance(config, CodeNodeConfig):
            return NodeResult(
                status=NodeState.FAILED,
                outputs={},
                error="Invalid or missing code node config",
            )

        pool = ctx.variable_pool

        # Resolve input variables
        resolved_inputs: dict[str, Any] = {}
        for name, ref in config.inputs.items():
            resolved_inputs[name] = pool.resolve_value(ref)

        # Build restricted execution scope
        scope: dict[str, Any] = {"__builtins__": _SAFE_BUILTINS}
        scope.update(resolved_inputs)

        try:
            exec(config.source, scope)  # noqa: S102
        except Exception as exc:
            return NodeResult(
                status=NodeState.FAILED,
                outputs={},
                error=f"{type(exc).__name__}: {exc}",
            )

        # Extract result from scope
        result_value = scope.get("result")
        if isinstance(result_value, dict):
            outputs = result_value
        else:
            outputs = {}

        return NodeResult(status=NodeState.COMPLETED, outputs=outputs)
