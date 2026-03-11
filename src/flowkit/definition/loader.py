"""Flowkit DSL v1 — Definition Loader.

Loads workflow definitions from JSON strings or dicts, validates them,
and provides checksum computation for content-addressable identity.

Usage:
    definition = load('{"version": "1.0", ...}')
    definition = load_dict({"version": "1.0", ...})
    checksum = compute_checksum(definition)
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import ValidationError as PydanticValidationError

from flowkit.definition.schema import WorkflowDefinition
from flowkit.definition.validator import ValidationError, validate


class DefinitionLoadError(Exception):
    """Raised when a workflow definition fails to load or validate."""

    def __init__(
        self,
        message: str,
        parse_errors: list[dict[str, Any]] | None = None,
        validation_errors: list[ValidationError] | None = None,
    ) -> None:
        super().__init__(message)
        self.parse_errors = parse_errors or []
        self.validation_errors = validation_errors or []


def load(json_str: str) -> WorkflowDefinition:
    """Parse a JSON string into a validated WorkflowDefinition.

    Args:
        json_str: A JSON string representing a workflow definition.

    Returns:
        A validated WorkflowDefinition instance.

    Raises:
        DefinitionLoadError: If JSON parsing, Pydantic validation, or graph
            validation fails.
    """
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as exc:
        raise DefinitionLoadError(
            f"Invalid JSON: {exc}",
            parse_errors=[{"error": str(exc)}],
        ) from exc

    if not isinstance(data, dict):
        raise DefinitionLoadError(
            f"Expected a JSON object, got {type(data).__name__}",
            parse_errors=[{"error": f"Expected object, got {type(data).__name__}"}],
        )

    return load_dict(data)


def load_dict(data: dict[str, Any]) -> WorkflowDefinition:
    """Parse a dict into a validated WorkflowDefinition.

    Args:
        data: A dictionary representing a workflow definition.

    Returns:
        A validated WorkflowDefinition instance.

    Raises:
        DefinitionLoadError: If Pydantic validation or graph validation fails.
    """
    # Step 1: Pydantic schema validation
    try:
        definition = WorkflowDefinition.model_validate(data)
    except PydanticValidationError as exc:
        raise DefinitionLoadError(
            f"Schema validation failed: {exc.error_count()} error(s)",
            parse_errors=[
                {
                    "loc": list(e["loc"]),
                    "msg": e["msg"],
                    "type": e["type"],
                }
                for e in exc.errors()
            ],
        ) from exc

    # Step 2: Graph / semantic validation
    errors = validate(definition)
    if errors:
        raise DefinitionLoadError(
            f"Validation failed: {len(errors)} error(s)",
            validation_errors=errors,
        )

    return definition


def compute_checksum(definition: WorkflowDefinition) -> str:
    """Compute a SHA-256 checksum of the canonical JSON representation.

    The checksum is deterministic — the same definition always produces the
    same hash, regardless of dict ordering in Python.

    Args:
        definition: A WorkflowDefinition to hash.

    Returns:
        A hex-encoded SHA-256 digest string.
    """
    # model_dump with mode="json" produces JSON-serializable types;
    # json.dumps with sort_keys ensures deterministic ordering.
    canonical = json.dumps(
        definition.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
