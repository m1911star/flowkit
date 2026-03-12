"""HTTP node executor — makes HTTP requests via httpx."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx

from flowkit.definition.schema import HttpNodeConfig
from flowkit.nodes.base import NodeContext, NodeExecutor, NodeResult
from flowkit.runtime.state import NodeState


class HttpExecutor(NodeExecutor):
    """Execute an HTTP request per the node configuration."""

    async def execute(self, ctx: NodeContext) -> NodeResult:
        config = ctx.node_def.parsed_config()
        if not isinstance(config, HttpNodeConfig):
            return NodeResult(
                status=NodeState.FAILED,
                outputs={},
                error="Invalid or missing HTTP node config",
            )

        pool = ctx.variable_pool

        # Resolve variable references in config fields
        url = str(pool.resolve_value(config.url))
        headers = {k: str(pool.resolve_value(v)) for k, v in config.headers.items()}
        body = pool.resolve_value(config.body) if config.body is not None else None
        timeout = config.timeout

        max_attempts = 1
        if config.retry:
            max_attempts = config.retry.max_attempts

        last_error: str | None = None

        for attempt in range(max_attempts):
            try:
                response = await self._do_request(
                    method=config.method.value,
                    url=url,
                    headers=headers,
                    body=body,
                    timeout=timeout,
                )
                return NodeResult(
                    status=NodeState.COMPLETED,
                    outputs=self._parse_response(response),
                )
            except (TimeoutError, httpx.HTTPError) as exc:
                last_error = str(exc)
                if attempt < max_attempts - 1:
                    # Simple backoff: fixed = no wait in tests, exponential = 2^attempt
                    if config.retry and config.retry.backoff.value == "exponential":
                        await asyncio.sleep(min(2**attempt, 30))
                    continue

        return NodeResult(
            status=NodeState.FAILED,
            outputs={},
            error=last_error or "HTTP request failed",
        )

    async def _do_request(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: Any,
        timeout: int,
    ) -> httpx.Response:
        """Make the actual HTTP request."""
        kwargs: dict[str, Any] = {
            "method": method,
            "url": url,
            "headers": headers,
            "timeout": timeout,
        }

        if body is not None:
            if isinstance(body, (dict, list)):
                kwargs["content"] = json.dumps(body).encode()
                if "Content-Type" not in headers and "content-type" not in headers:
                    kwargs["headers"]["Content-Type"] = "application/json"
            else:
                kwargs["content"] = str(body).encode()

        async with httpx.AsyncClient() as client:
            return await client.request(**kwargs)

    def _parse_response(self, response: httpx.Response) -> dict[str, Any]:
        """Extract outputs from the HTTP response."""
        content_type = response.headers.get("content-type", "")

        if "application/json" in content_type:
            try:
                body = response.json()
            except (json.JSONDecodeError, ValueError):
                body = response.text
        else:
            body = response.text

        return {
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "body": body,
        }
