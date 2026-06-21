"""Code node executor — runs user Python code in a restricted scope."""

from __future__ import annotations

import ast
import logging
import threading
from typing import Any

from flowkit.definition.schema import CodeNodeConfig
from flowkit.nodes.base import NodeContext, NodeExecutor, NodeResult
from flowkit.runtime.state import NodeState

logger = logging.getLogger(__name__)

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
_MAX_SOURCE_LENGTH = 50_000

# Function names that are forbidden even if they appear in builtins or scope
_FORBIDDEN_CALLS: frozenset[str] = frozenset(
    {"eval", "exec", "compile", "globals", "locals", "vars", "dir", "delattr", "setattr"}
)


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

        # --- Guard: source length ---
        if len(config.source) > _MAX_SOURCE_LENGTH:
            return NodeResult(
                status=NodeState.FAILED,
                outputs={},
                error=f"Source too large ({len(config.source)} chars, max {_MAX_SOURCE_LENGTH})",
            )

        # --- Guard: AST pre-validation ---
        logger.debug("Code execution started for node %s", ctx.node_def.id)
        validation_error = _validate_ast(config.source)
        if validation_error is not None:
            logger.warning("AST validation failed: %s", validation_error)
            return NodeResult(
                status=NodeState.FAILED,
                outputs={},
                error=validation_error,
            )

        pool = ctx.variable_pool

        # Resolve input variables
        resolved_inputs: dict[str, Any] = {}
        for name, ref in config.inputs.items():
            resolved_inputs[name] = pool.resolve_value(ref)

        # Build restricted execution scope
        scope: dict[str, Any] = {"__builtins__": _SAFE_BUILTINS}
        scope.update(resolved_inputs)

        timeout = _DEFAULT_TIMEOUT

        try:
            compiled = compile(config.source, "<sandbox>", "exec")
        except SyntaxError as exc:
            return NodeResult(
                status=NodeState.FAILED,
                outputs={},
                error=f"SyntaxError: {exc}",
            )

        # Run in a daemon thread so it doesn't block process exit on timeout
        error_box: list[Exception] = []

        def _run() -> None:
            try:
                exec(compiled, scope)  # noqa: S102
            except Exception as exc:
                error_box.append(exc)

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        thread.join(timeout=timeout)

        if thread.is_alive():
            logger.warning("Code execution timed out after %ds", timeout)
            return NodeResult(
                status=NodeState.FAILED,
                outputs={},
                error=f"Execution timed out after {timeout}s",
            )

        if error_box:
            err = error_box[0]
            return NodeResult(
                status=NodeState.FAILED,
                outputs={},
                error=f"{type(err).__name__}: {err}",
            )

        # Extract result from scope
        result_value = scope.get("result")
        outputs = result_value if isinstance(result_value, dict) else {}

        return NodeResult(status=NodeState.COMPLETED, outputs=outputs)


def _validate_ast(source: str) -> str | None:
    """Parse and walk the AST, returning an error message if dangerous nodes are found."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return f"SyntaxError: {exc}"

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = ", ".join(alias.name for alias in node.names)
            return f"Forbidden: import statement ({names})"

        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            return f"Forbidden: from-import statement ({module})"

        if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            return f"Forbidden: access to private/dunder attribute '{node.attr}'"

        if isinstance(node, ast.Call):
            func = node.func
            # Direct name call: eval(...), exec(...)
            if isinstance(func, ast.Name) and func.id in _FORBIDDEN_CALLS:
                return f"Forbidden: call to '{func.id}'"

    return None
