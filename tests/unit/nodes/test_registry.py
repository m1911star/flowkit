"""Tests for flowkit.nodes.registry — executor registry."""

import pytest

from flowkit.definition.schema import NodeType
from flowkit.nodes.base import NodeExecutor
from flowkit.nodes.code import CodeExecutor
from flowkit.nodes.end import EndExecutor
from flowkit.nodes.http import HttpExecutor
from flowkit.nodes.human_input import HumanInputExecutor
from flowkit.nodes.if_else import IfElseExecutor
from flowkit.nodes.loop import LoopExecutor
from flowkit.nodes.parallel import ParallelExecutor
from flowkit.nodes.registry import EXECUTOR_REGISTRY, get_executor
from flowkit.nodes.start import StartExecutor


class TestExecutorRegistry:
    def test_all_node_types_registered(self):
        for node_type in NodeType:
            assert node_type in EXECUTOR_REGISTRY, f"{node_type} not in registry"

    def test_correct_executor_types(self):
        assert EXECUTOR_REGISTRY[NodeType.start] is StartExecutor
        assert EXECUTOR_REGISTRY[NodeType.end] is EndExecutor
        assert EXECUTOR_REGISTRY[NodeType.http] is HttpExecutor
        assert EXECUTOR_REGISTRY[NodeType.code] is CodeExecutor
        assert EXECUTOR_REGISTRY[NodeType.if_else] is IfElseExecutor
        assert EXECUTOR_REGISTRY[NodeType.loop] is LoopExecutor
        assert EXECUTOR_REGISTRY[NodeType.human_input] is HumanInputExecutor
        assert EXECUTOR_REGISTRY[NodeType.parallel] is ParallelExecutor

    def test_get_executor_returns_instance(self):
        for node_type in NodeType:
            executor = get_executor(node_type)
            assert isinstance(executor, NodeExecutor)

    def test_get_executor_returns_correct_type(self):
        executor = get_executor(NodeType.http)
        assert isinstance(executor, HttpExecutor)

    def test_get_executor_unknown_type_raises(self):
        with pytest.raises(KeyError):
            get_executor("nonexistent")  # type: ignore[arg-type]
