"""Plugin interface — contract for custom node type plugins."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel


@dataclass
class PluginMetadata:
    """Metadata describing a plugin."""

    name: str  # unique plugin name, e.g. "slack_notification"
    version: str  # semver, e.g. "1.0.0"
    node_type: str  # the node type ID it registers, e.g. "slack"
    description: str = ""
    author: str = ""


class PluginConfigSchema(BaseModel):
    """Base class for plugin config schemas. Plugins subclass this."""


class PluginNodeExecutor(ABC):
    """Abstract base for plugin node executors.

    Plugins implement this to define custom node behavior.
    The interface mirrors NodeExecutor but uses plain dicts
    to avoid tight coupling to internal types.
    """

    @abstractmethod
    async def execute(
        self,
        config: dict[str, Any],
        inputs: dict[str, Any],
        context: dict[str, Any],
    ) -> PluginResult:
        """Execute the plugin node.

        Args:
            config: The node's config dict (validated against config_schema)
            inputs: Resolved input variables from the variable pool
            context: Execution context (run_id, node_id, etc.)

        Returns:
            PluginResult with status, outputs, and optional error.
        """
        ...


@dataclass
class PluginResult:
    """Result of a plugin node execution."""

    status: str  # "completed", "failed", "waiting"
    outputs: dict[str, Any]
    error: str | None = None
