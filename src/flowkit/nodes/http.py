"""HTTP node executor — makes HTTP requests via httpx."""

from __future__ import annotations

import asyncio
import json
import logging
import random
from typing import Any

import httpx

from flowkit.definition.schema import HttpNodeConfig
from flowkit.nodes.base import NodeContext, NodeExecutor, NodeResult
from flowkit.runtime.state import NodeState

logger = logging.getLogger(__name__)
_MAX_RESPONSE_SIZE = 10 * 1024 * 1024  # 10 MB


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
                logger.debug("HTTP request started: %s %s", config.method.value, url)
                response = await self._do_request(
                    method=config.method.value,
                    url=url,
                    headers=headers,
                    body=body,
                    timeout=timeout,
                )
                response.raise_for_status()
                if len(response.content) > _MAX_RESPONSE_SIZE:
                    return NodeResult(
                        status=NodeState.FAILED,
                        outputs={},
                        error=(
                            f"Response size {len(response.content)} bytes"
                            f" exceeds limit of {_MAX_RESPONSE_SIZE} bytes"
                        ),
                    )
                logger.debug("HTTP response received: status=%d", response.status_code)
                return NodeResult(
                    status=NodeState.COMPLETED,
                    outputs=self._parse_response(response),
                )
            except (TimeoutError, httpx.HTTPError) as exc:
                last_error = str(exc)
                if attempt < max_attempts - 1:
                    logger.warning(
                        "HTTP retry attempt %d failed: %s", attempt + 1, last_error
                    )
                    if config.retry and config.retry.backoff.value == "exponential":
                        base_delay = float(2**attempt)
                    else:
                        base_delay = 1.0
                    delay = min(base_delay * (0.75 + random.random() * 0.5), 60.0)
                    await asyncio.sleep(delay)
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
