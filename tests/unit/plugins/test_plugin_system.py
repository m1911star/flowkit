"""Tests for flowkit.plugins — plugin system."""

import uuid
from typing import Any
from unittest.mock import patch

import pytest

from flowkit.definition.schema import NodeDef, NodeType
from flowkit.nodes.base import NodeContext
from flowkit.plugins.adapter import PluginNodeAdapter
from flowkit.plugins.base import (
    PluginConfigSchema,
    PluginMetadata,
    PluginNodeExecutor,
    PluginResult,
)
from flowkit.plugins.loader import PluginRegistry
from flowkit.runtime.state import NodeState
from flowkit.runtime.variable_pool import VariablePool

# ---------------------------------------------------------------------------
# Test plugin implementations
# ---------------------------------------------------------------------------


class EchoPlugin(PluginNodeExecutor):
    async def execute(
        self,
        config: dict[str, Any],
        inputs: dict[str, Any],
        context: dict[str, Any],
    ) -> PluginResult:
        return PluginResult(status="completed", outputs={"echo": inputs})


class FailPlugin(PluginNodeExecutor):
    async def execute(
        self,
        config: dict[str, Any],
        inputs: dict[str, Any],
        context: dict[str, Any],
    ) -> PluginResult:
        return PluginResult(status="failed", outputs={}, error="intentional failure")


class ExplodingPlugin(PluginNodeExecutor):
    async def execute(
        self,
        config: dict[str, Any],
        inputs: dict[str, Any],
        context: dict[str, Any],
    ) -> PluginResult:
        raise RuntimeError("kaboom")


class EchoConfigSchema(PluginConfigSchema):
    message: str
    count: int = 1


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _echo_metadata(node_type: str = "echo") -> PluginMetadata:
    return PluginMetadata(
        name="echo_plugin",
        version="1.0.0",
        node_type=node_type,
        description="Echoes inputs",
        author="test",
    )


def _make_ctx(
    config: dict[str, Any] | None = None, pool: VariablePool | None = None
) -> NodeContext:
    return NodeContext(
        node_def=NodeDef(id="plugin_node", type=NodeType.code, config=config),
        variable_pool=pool or VariablePool(),
        run_id=uuid.uuid4(),
        node_run_id=uuid.uuid4(),
    )


# ---------------------------------------------------------------------------
# Registry tests
# ---------------------------------------------------------------------------


class TestPluginRegistry:
    def test_registry_register_and_get(self) -> None:
        registry = PluginRegistry()
        meta = _echo_metadata()
        registry.register(meta, EchoPlugin)

        loaded = registry.get("echo")
        assert loaded is not None
        assert loaded.metadata is meta
        assert loaded.executor_class is EchoPlugin

    def test_registry_duplicate_raises(self) -> None:
        registry = PluginRegistry()
        meta = _echo_metadata()
        registry.register(meta, EchoPlugin)

        with pytest.raises(ValueError, match="already registered"):
            registry.register(meta, EchoPlugin)

    def test_registry_list_plugins(self) -> None:
        registry = PluginRegistry()
        meta1 = _echo_metadata("echo")
        meta2 = PluginMetadata(name="other", version="2.0.0", node_type="other")
        registry.register(meta1, EchoPlugin)
        registry.register(meta2, FailPlugin)

        plugins = registry.list_plugins()
        assert len(plugins) == 2
        assert meta1 in plugins
        assert meta2 in plugins

    def test_registry_is_registered(self) -> None:
        registry = PluginRegistry()
        assert registry.is_registered("echo") is False
        registry.register(_echo_metadata(), EchoPlugin)
        assert registry.is_registered("echo") is True


# ---------------------------------------------------------------------------
# Adapter tests
# ---------------------------------------------------------------------------


class TestPluginNodeAdapter:
    async def test_adapter_executes_plugin(self) -> None:
        registry = PluginRegistry()
        registry.register(_echo_metadata(), EchoPlugin)

        pool = VariablePool(workflow_inputs={"greeting": "hello"})
        ctx = _make_ctx(
            config={"inputs": {"greeting": "{{workflow.input.greeting}}"}},
            pool=pool,
        )

        adapter = PluginNodeAdapter("echo")
        with patch("flowkit.plugins.adapter.plugin_registry", registry):
            result = await adapter.execute(ctx)

        assert result.status == NodeState.COMPLETED
        assert result.outputs == {"echo": {"greeting": "hello"}}
        assert result.error is None

    async def test_adapter_plugin_not_found(self) -> None:
        registry = PluginRegistry()

        ctx = _make_ctx(config={})
        adapter = PluginNodeAdapter("nonexistent")
        with patch("flowkit.plugins.adapter.plugin_registry", registry):
            result = await adapter.execute(ctx)

        assert result.status == NodeState.FAILED
        assert "not found" in (result.error or "")

    async def test_adapter_config_validation_fails(self) -> None:
        registry = PluginRegistry()
        meta = _echo_metadata()
        registry.register(meta, EchoPlugin, config_schema=EchoConfigSchema)

        # Missing required 'message' field
        ctx = _make_ctx(config={"count": 5})
        adapter = PluginNodeAdapter("echo")
        with patch("flowkit.plugins.adapter.plugin_registry", registry):
            result = await adapter.execute(ctx)

        assert result.status == NodeState.FAILED
        assert "config validation failed" in (result.error or "").lower()

    async def test_adapter_plugin_exception(self) -> None:
        registry = PluginRegistry()
        meta = PluginMetadata(name="exploding", version="1.0.0", node_type="explode")
        registry.register(meta, ExplodingPlugin)

        ctx = _make_ctx(config={})
        adapter = PluginNodeAdapter("explode")
        with patch("flowkit.plugins.adapter.plugin_registry", registry):
            result = await adapter.execute(ctx)

        assert result.status == NodeState.FAILED
        assert "RuntimeError" in (result.error or "")
        assert "kaboom" in (result.error or "")

    async def test_adapter_failed_plugin(self) -> None:
        registry = PluginRegistry()
        meta = PluginMetadata(name="fail_plugin", version="1.0.0", node_type="fail")
        registry.register(meta, FailPlugin)

        ctx = _make_ctx(config={})
        adapter = PluginNodeAdapter("fail")
        with patch("flowkit.plugins.adapter.plugin_registry", registry):
            result = await adapter.execute(ctx)

        assert result.status == NodeState.FAILED
        assert result.error == "intentional failure"
        assert result.outputs == {}
