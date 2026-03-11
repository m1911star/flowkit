"""Tests for flowkit.nodes.http — HttpExecutor."""

import uuid
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from flowkit.definition.schema import NodeDef, NodeType
from flowkit.nodes.base import NodeContext
from flowkit.nodes.http import HttpExecutor
from flowkit.runtime.state import NodeState
from flowkit.runtime.variable_pool import VariablePool


def _make_ctx(config: dict, pool: VariablePool | None = None) -> NodeContext:
    return NodeContext(
        node_def=NodeDef(id="http_node", type=NodeType.http, config=config),
        variable_pool=pool or VariablePool(),
        run_id=uuid.uuid4(),
        node_run_id=uuid.uuid4(),
    )


class TestHttpExecutor:
    async def test_get_success(self):
        config = {"method": "GET", "url": "https://api.example.com/data", "timeout": 10}
        ctx = _make_ctx(config)

        mock_response = httpx.Response(
            200,
            json={"result": "ok"},
            headers={"content-type": "application/json"},
            request=httpx.Request("GET", "https://api.example.com/data"),
        )

        with patch("flowkit.nodes.http.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.request.return_value = mock_response
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            executor = HttpExecutor()
            result = await executor.execute(ctx)

        assert result.status == NodeState.COMPLETED
        assert result.outputs["status_code"] == 200
        assert result.outputs["body"] == {"result": "ok"}
        assert "content-type" in result.outputs["headers"]

    async def test_post_with_body(self):
        config = {
            "method": "POST",
            "url": "https://api.example.com/submit",
            "headers": {"Content-Type": "application/json"},
            "body": {"key": "value"},
            "timeout": 10,
        }
        ctx = _make_ctx(config)

        mock_response = httpx.Response(
            201,
            json={"id": "abc"},
            headers={"content-type": "application/json"},
            request=httpx.Request("POST", "https://api.example.com/submit"),
        )

        with patch("flowkit.nodes.http.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.request.return_value = mock_response
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            executor = HttpExecutor()
            result = await executor.execute(ctx)

        assert result.status == NodeState.COMPLETED
        assert result.outputs["status_code"] == 201
        assert result.outputs["body"] == {"id": "abc"}

    async def test_variable_resolution_in_url(self):
        pool = VariablePool({"order_id": "42"})
        config = {
            "method": "GET",
            "url": "{{workflow.input.order_id}}",
            "timeout": 10,
        }
        ctx = _make_ctx(config, pool)

        mock_response = httpx.Response(
            200,
            text="ok",
            headers={"content-type": "text/plain"},
            request=httpx.Request("GET", "42"),
        )

        with patch("flowkit.nodes.http.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.request.return_value = mock_response
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            executor = HttpExecutor()
            result = await executor.execute(ctx)

        assert result.status == NodeState.COMPLETED
        # URL was resolved from variable pool
        instance.request.assert_called_once()

    async def test_http_failure(self):
        config = {"method": "GET", "url": "https://api.example.com/fail", "timeout": 5}
        ctx = _make_ctx(config)

        with patch("flowkit.nodes.http.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.request.side_effect = httpx.ConnectError("Connection refused")
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            executor = HttpExecutor()
            result = await executor.execute(ctx)

        assert result.status == NodeState.FAILED
        assert "Connection refused" in result.error

    async def test_retry_on_failure(self):
        config = {
            "method": "GET",
            "url": "https://api.example.com/flaky",
            "timeout": 5,
            "retry": {"max_attempts": 3, "backoff": "fixed"},
        }
        ctx = _make_ctx(config)

        mock_response = httpx.Response(
            200,
            json={"ok": True},
            headers={"content-type": "application/json"},
            request=httpx.Request("GET", "https://api.example.com/flaky"),
        )

        with patch("flowkit.nodes.http.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            # Fail twice, succeed on third
            instance.request.side_effect = [
                httpx.ConnectError("fail1"),
                httpx.ConnectError("fail2"),
                mock_response,
            ]
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            executor = HttpExecutor()
            result = await executor.execute(ctx)

        assert result.status == NodeState.COMPLETED
        assert result.outputs["status_code"] == 200
        assert instance.request.call_count == 3

    async def test_retry_exhausted(self):
        config = {
            "method": "GET",
            "url": "https://api.example.com/down",
            "timeout": 5,
            "retry": {"max_attempts": 2, "backoff": "fixed"},
        }
        ctx = _make_ctx(config)

        with patch("flowkit.nodes.http.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.request.side_effect = httpx.ConnectError("always fails")
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            executor = HttpExecutor()
            result = await executor.execute(ctx)

        assert result.status == NodeState.FAILED
        assert "always fails" in result.error
        assert instance.request.call_count == 2

    async def test_text_response_body(self):
        config = {"method": "GET", "url": "https://example.com/text", "timeout": 10}
        ctx = _make_ctx(config)

        mock_response = httpx.Response(
            200,
            text="plain text response",
            headers={"content-type": "text/plain"},
            request=httpx.Request("GET", "https://example.com/text"),
        )

        with patch("flowkit.nodes.http.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.request.return_value = mock_response
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            executor = HttpExecutor()
            result = await executor.execute(ctx)

        assert result.status == NodeState.COMPLETED
        assert result.outputs["body"] == "plain text response"
