"""Plugin loader — discovers and registers plugin node types."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pydantic import BaseModel

    from flowkit.plugins.base import PluginMetadata, PluginNodeExecutor

logger = logging.getLogger(__name__)


class PluginRegistry:
    """Registry of loaded plugins."""

    def __init__(self) -> None:
        self._plugins: dict[str, LoadedPlugin] = {}  # node_type -> plugin

    def register(
        self,
        metadata: PluginMetadata,
        executor_class: type[PluginNodeExecutor],
        config_schema: type[BaseModel] | None = None,
    ) -> None:
        """Register a plugin."""
        if metadata.node_type in self._plugins:
            raise ValueError(f"Plugin node type '{metadata.node_type}' already registered")
        self._plugins[metadata.node_type] = LoadedPlugin(
            metadata=metadata,
            executor_class=executor_class,
            config_schema=config_schema,
        )
        logger.info("Plugin registered: %s (node_type=%s)", metadata.name, metadata.node_type)

    def get(self, node_type: str) -> LoadedPlugin | None:
        return self._plugins.get(node_type)

    def list_plugins(self) -> list[PluginMetadata]:
        return [p.metadata for p in self._plugins.values()]

    def is_registered(self, node_type: str) -> bool:
        return node_type in self._plugins


@dataclass
class LoadedPlugin:
    """A plugin that has been loaded and registered."""

    metadata: PluginMetadata
    executor_class: type[PluginNodeExecutor]
    config_schema: type[BaseModel] | None = None


def load_plugins_from_entry_points(registry: PluginRegistry) -> int:
    """Discover plugins via importlib.metadata entry_points.

    Looks for entry points in group 'flowkit.plugins'.
    Each entry point should resolve to a function that returns
    (PluginMetadata, type[PluginNodeExecutor], optional config schema class).

    Returns the number of plugins loaded.
    """
    import importlib.metadata

    count = 0
    eps = importlib.metadata.entry_points(group="flowkit.plugins")
    for ep in eps:
        try:
            factory = ep.load()
            metadata, executor_cls, config_schema = factory()
            registry.register(metadata, executor_cls, config_schema)
            count += 1
        except Exception:
            logger.exception("Failed to load plugin: %s", ep.name)
    return count


# Module-level singleton
plugin_registry = PluginRegistry()
