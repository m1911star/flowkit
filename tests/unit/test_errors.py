"""Tests for flowkit.errors — structured error hierarchy and API handler."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from flowkit.errors import (
    ExecutionError,
    FlowkitError,
    NotFoundError,
    StateTransitionError,
    TimeoutError,
    ValidationError,
    WebhookError,
)

if TYPE_CHECKING:
    from fastapi import FastAPI


# --------------------------------------------------------------------------- #
# Error class construction tests
# --------------------------------------------------------------------------- #


class TestFlowkitError:
    def test_base_error_attributes(self) -> None:
        exc = FlowkitError("something broke", code="GENERIC", details={"foo": "bar"})
        assert str(exc) == "something broke"
        assert exc.code == "GENERIC"
        assert exc.details == {"foo": "bar"}

    def test_base_error_defaults_empty_details(self) -> None:
        exc = FlowkitError("oops", code="X")
        assert exc.details == {}

    def test_is_exception(self) -> None:
        exc = FlowkitError("msg", code="C")
        assert isinstance(exc, Exception)


class TestNotFoundError:
    def test_message_and_details(self) -> None:
        exc = NotFoundError("Workflow", "abc-123")
        assert str(exc) == "Workflow 'abc-123' not found"
        assert exc.code == "NOT_FOUND"
        assert exc.details == {"resource": "Workflow", "id": "abc-123"}

    def test_inherits_from_base(self) -> None:
        exc = NotFoundError("X", "1")
        assert isinstance(exc, FlowkitError)


class TestValidationError:
    def test_with_errors_list(self) -> None:
        exc = ValidationError("bad input", errors=["field required", "too short"])
        assert str(exc) == "bad input"
        assert exc.code == "VALIDATION_ERROR"
        assert exc.details == {"errors": ["field required", "too short"]}

    def test_defaults_empty_errors(self) -> None:
        exc = ValidationError("nope")
        assert exc.details == {"errors": []}


class TestExecutionError:
    def test_full_details(self) -> None:
        exc = ExecutionError("node crashed", node_id="n1", run_id="r1")
        assert str(exc) == "node crashed"
        assert exc.code == "EXECUTION_ERROR"
        assert exc.details == {"node_id": "n1", "run_id": "r1"}

    def test_optional_fields_none(self) -> None:
        exc = ExecutionError("fail")
        assert exc.details == {"node_id": None, "run_id": None}


class TestTimeoutError:
    def test_attributes(self) -> None:
        exc = TimeoutError("took too long", timeout_seconds=30)
        assert str(exc) == "took too long"
        assert exc.code == "TIMEOUT"
        assert exc.details == {"timeout_seconds": 30}


class TestWebhookError:
    def test_with_key(self) -> None:
        exc = WebhookError("webhook failed", key="wh-1")
        assert str(exc) == "webhook failed"
        assert exc.code == "WEBHOOK_ERROR"
        assert exc.details == {"key": "wh-1"}

    def test_without_key(self) -> None:
        exc = WebhookError("generic webhook issue")
        assert exc.details == {"key": None}


class TestStateTransitionError:
    def test_attributes(self) -> None:
        exc = StateTransitionError(
            "cannot go from pending to completed", current="pending", target="completed"
        )
        assert str(exc) == "cannot go from pending to completed"
        assert exc.code == "INVALID_TRANSITION"
        assert exc.details == {"current": "pending", "target": "completed"}


# --------------------------------------------------------------------------- #
# API exception handler tests
# --------------------------------------------------------------------------- #


@pytest.fixture
def app_with_handler() -> FastAPI:
    """Minimal FastAPI app with the flowkit error handler registered."""
    from flowkit.api.app import create_app

    app = create_app()

    # Add test routes that raise various errors
    @app.get("/raise-not-found")
    async def _raise_not_found() -> None:
        raise NotFoundError("Widget", "42")

    @app.get("/raise-validation")
    async def _raise_validation() -> None:
        raise ValidationError("invalid", errors=["bad field"])

    @app.get("/raise-webhook")
    async def _raise_webhook() -> None:
        raise WebhookError("bad hook", key="k1")

    @app.get("/raise-timeout")
    async def _raise_timeout() -> None:
        raise TimeoutError("slow", timeout_seconds=60)

    @app.get("/raise-transition")
    async def _raise_transition() -> None:
        raise StateTransitionError("nope", current="a", target="b")

    @app.get("/raise-execution")
    async def _raise_execution() -> None:
        raise ExecutionError("boom", node_id="n1", run_id="r1")

    return app


@pytest.fixture
def client(app_with_handler: FastAPI) -> TestClient:
    return TestClient(app_with_handler, raise_server_exceptions=False)


class TestExceptionHandler:
    def test_not_found_returns_404(self, client: TestClient) -> None:
        resp = client.get("/raise-not-found")
        assert resp.status_code == 404
        body = resp.json()
        assert body["error"]["code"] == "NOT_FOUND"
        assert body["error"]["message"] == "Widget '42' not found"
        assert body["error"]["details"] == {"resource": "Widget", "id": "42"}

    def test_validation_returns_422(self, client: TestClient) -> None:
        resp = client.get("/raise-validation")
        assert resp.status_code == 422
        body = resp.json()
        assert body["error"]["code"] == "VALIDATION_ERROR"

    def test_webhook_returns_400(self, client: TestClient) -> None:
        resp = client.get("/raise-webhook")
        assert resp.status_code == 400
        body = resp.json()
        assert body["error"]["code"] == "WEBHOOK_ERROR"
        assert body["error"]["details"]["key"] == "k1"

    def test_timeout_returns_504(self, client: TestClient) -> None:
        resp = client.get("/raise-timeout")
        assert resp.status_code == 504
        body = resp.json()
        assert body["error"]["code"] == "TIMEOUT"

    def test_transition_returns_409(self, client: TestClient) -> None:
        resp = client.get("/raise-transition")
        assert resp.status_code == 409
        body = resp.json()
        assert body["error"]["code"] == "INVALID_TRANSITION"

    def test_execution_returns_500(self, client: TestClient) -> None:
        resp = client.get("/raise-execution")
        assert resp.status_code == 500
        body = resp.json()
        assert body["error"]["code"] == "EXECUTION_ERROR"


# --------------------------------------------------------------------------- #
# Webhook module integration — verify WebhookError is raised
# --------------------------------------------------------------------------- #


class TestWebhookRaisesStructuredErrors:
    def test_webhook_not_found_is_not_found_error(self) -> None:
        from flowkit.triggers.webhook import WebhookNotFoundError

        exc = WebhookNotFoundError("test-key")
        assert isinstance(exc, NotFoundError)
        assert isinstance(exc, FlowkitError)
        assert exc.key == "test-key"
        assert exc.code == "NOT_FOUND"
        assert exc.details["resource"] == "Webhook trigger"
        assert exc.details["id"] == "test-key"

    def test_webhook_inactive_is_webhook_error(self) -> None:
        from flowkit.triggers.webhook import WebhookInactiveError

        exc = WebhookInactiveError("dead-key")
        assert isinstance(exc, WebhookError)
        assert isinstance(exc, FlowkitError)
        assert exc.key == "dead-key"
        assert exc.code == "WEBHOOK_ERROR"
        assert exc.details["key"] == "dead-key"
