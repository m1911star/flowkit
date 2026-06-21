"""Tests for API routes."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest

if TYPE_CHECKING:
    from httpx import AsyncClient


class TestHealth:
    async def test_health(self, client: AsyncClient) -> None:
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


class TestWorkflowCRUD:
    async def test_create_workflow(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/workflows",
            json={"name": "test-wf", "description": "A test workflow"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "test-wf"
        assert data["description"] == "A test workflow"
        assert "id" in data

    async def test_list_workflows(self, client: AsyncClient) -> None:
        await client.post("/api/v1/workflows", json={"name": "wf-1"})
        await client.post("/api/v1/workflows", json={"name": "wf-2"})
        resp = await client.get("/api/v1/workflows")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 2

    async def test_get_workflow(self, client: AsyncClient) -> None:
        create_resp = await client.post("/api/v1/workflows", json={"name": "get-me"})
        wf_id = create_resp.json()["id"]
        resp = await client.get(f"/api/v1/workflows/{wf_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "get-me"

    async def test_get_workflow_not_found(self, client: AsyncClient) -> None:
        resp = await client.get(f"/api/v1/workflows/{uuid4()}")
        assert resp.status_code == 404

    async def test_update_workflow(self, client: AsyncClient) -> None:
        create_resp = await client.post("/api/v1/workflows", json={"name": "old-name"})
        wf_id = create_resp.json()["id"]
        resp = await client.patch(f"/api/v1/workflows/{wf_id}", json={"name": "new-name"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "new-name"

    async def test_delete_workflow(self, client: AsyncClient) -> None:
        create_resp = await client.post("/api/v1/workflows", json={"name": "delete-me"})
        wf_id = create_resp.json()["id"]
        resp = await client.delete(f"/api/v1/workflows/{wf_id}")
        assert resp.status_code == 204
        # Verify deleted
        get_resp = await client.get(f"/api/v1/workflows/{wf_id}")
        assert get_resp.status_code == 404

    async def test_update_workflow_not_found(self, client: AsyncClient) -> None:
        resp = await client.patch(f"/api/v1/workflows/{uuid4()}", json={"name": "nope"})
        assert resp.status_code == 404

    async def test_delete_workflow_not_found(self, client: AsyncClient) -> None:
        resp = await client.delete(f"/api/v1/workflows/{uuid4()}")
        assert resp.status_code == 404

    async def test_update_workflow_empty_body(self, client: AsyncClient) -> None:
        create_resp = await client.post("/api/v1/workflows", json={"name": "empty-update"})
        wf_id = create_resp.json()["id"]
        resp = await client.patch(f"/api/v1/workflows/{wf_id}", json={})
        assert resp.status_code == 400


class TestWorkflowVersions:
    @pytest.fixture
    async def workflow_id(self, client: AsyncClient) -> str:
        resp = await client.post("/api/v1/workflows", json={"name": "versioned-wf"})
        return resp.json()["id"]

    def _minimal_definition(self) -> dict:
        return {
            "version": "1.0",
            "metadata": {"name": "test-wf", "description": "test"},
            "inputs": {},
            "outputs": {},
            "nodes": [
                {"id": "start", "type": "start", "label": "Start"},
                {"id": "end", "type": "end", "label": "End"},
            ],
            "edges": [
                {"id": "e1", "source": "start", "target": "end"},
            ],
        }

    async def test_create_version(self, client: AsyncClient, workflow_id: str) -> None:
        resp = await client.post(
            f"/api/v1/workflows/{workflow_id}/versions",
            json={"definition": self._minimal_definition()},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["version"] == 1
        assert data["checksum"] is not None

    async def test_create_version_auto_increments(
        self, client: AsyncClient, workflow_id: str
    ) -> None:
        defn = self._minimal_definition()
        await client.post(f"/api/v1/workflows/{workflow_id}/versions", json={"definition": defn})
        resp = await client.post(
            f"/api/v1/workflows/{workflow_id}/versions", json={"definition": defn}
        )
        assert resp.json()["version"] == 2

    async def test_list_versions(self, client: AsyncClient, workflow_id: str) -> None:
        defn = self._minimal_definition()
        await client.post(f"/api/v1/workflows/{workflow_id}/versions", json={"definition": defn})
        resp = await client.get(f"/api/v1/workflows/{workflow_id}/versions")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    async def test_create_version_workflow_not_found(self, client: AsyncClient) -> None:
        resp = await client.post(
            f"/api/v1/workflows/{uuid4()}/versions",
            json={"definition": self._minimal_definition()},
        )
        assert resp.status_code == 404

    async def test_create_version_invalid_definition(
        self, client: AsyncClient, workflow_id: str
    ) -> None:
        resp = await client.post(
            f"/api/v1/workflows/{workflow_id}/versions",
            json={"definition": {"invalid": "not a valid dsl definition"}},
        )
        assert resp.status_code == 422

    async def test_publish_version(self, client: AsyncClient, workflow_id: str) -> None:
        defn = self._minimal_definition()
        ver_resp = await client.post(
            f"/api/v1/workflows/{workflow_id}/versions", json={"definition": defn}
        )
        version_id = ver_resp.json()["id"]
        resp = await client.post(
            f"/api/v1/workflows/{workflow_id}/versions/{version_id}/publish"
        )
        assert resp.status_code == 200
        assert resp.json()["is_published"] is True

    async def test_publish_version_not_found(self, client: AsyncClient, workflow_id: str) -> None:
        resp = await client.post(
            f"/api/v1/workflows/{workflow_id}/versions/{uuid4()}/publish"
        )
        assert resp.status_code == 404

    async def test_rollback_version(self, client: AsyncClient, workflow_id: str) -> None:
        defn = self._minimal_definition()
        ver1_resp = await client.post(
            f"/api/v1/workflows/{workflow_id}/versions", json={"definition": defn}
        )
        ver1_id = ver1_resp.json()["id"]
        # Create a second version and publish it
        ver2_resp = await client.post(
            f"/api/v1/workflows/{workflow_id}/versions",
            json={"definition": defn, "is_published": True},
        )
        assert ver2_resp.status_code == 201
        # Rollback to version 1
        resp = await client.post(
            f"/api/v1/workflows/{workflow_id}/versions/{ver1_id}/rollback"
        )
        assert resp.status_code == 200
        assert resp.json()["is_published"] is True

    async def test_rollback_version_not_found(
        self, client: AsyncClient, workflow_id: str
    ) -> None:
        resp = await client.post(
            f"/api/v1/workflows/{workflow_id}/versions/{uuid4()}/rollback"
        )
        assert resp.status_code == 404

    async def test_diff_versions(self, client: AsyncClient, workflow_id: str) -> None:
        defn1 = self._minimal_definition()
        await client.post(
            f"/api/v1/workflows/{workflow_id}/versions", json={"definition": defn1}
        )
        # Create v2 with an extra http node inserted between start and end
        defn2 = self._minimal_definition()
        defn2["nodes"].append({
            "id": "mid", "type": "http", "label": "Middle",
            "config": {"url": "http://example.com", "method": "GET"},
        })
        defn2["edges"] = [
            {"id": "e1", "source": "start", "target": "mid"},
            {"id": "e2", "source": "mid", "target": "end"},
        ]
        v2_resp = await client.post(
            f"/api/v1/workflows/{workflow_id}/versions", json={"definition": defn2}
        )
        assert v2_resp.status_code == 201, v2_resp.json()
        resp = await client.get(
            f"/api/v1/workflows/{workflow_id}/versions/diff",
            params={"from_version": 1, "to_version": 2},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "mid" in data["nodes_added"]

    async def test_diff_versions_not_found(
        self, client: AsyncClient, workflow_id: str
    ) -> None:
        resp = await client.get(
            f"/api/v1/workflows/{workflow_id}/versions/diff",
            params={"from_version": 99, "to_version": 100},
        )
        assert resp.status_code == 404


class TestRunRoutes:
    @pytest.fixture
    async def run_setup(self, client: AsyncClient) -> dict:
        """Create workflow with version, return IDs."""
        wf_resp = await client.post("/api/v1/workflows", json={"name": "run-wf"})
        wf_id = wf_resp.json()["id"]
        defn = {
            "version": "1.0",
            "metadata": {"name": "test-wf", "description": "test"},
            "inputs": {},
            "outputs": {},
            "nodes": [
                {"id": "start", "type": "start", "label": "Start"},
                {"id": "end", "type": "end", "label": "End"},
            ],
            "edges": [{"id": "e1", "source": "start", "target": "end"}],
        }
        ver_resp = await client.post(
            f"/api/v1/workflows/{wf_id}/versions",
            json={"definition": defn, "is_published": True},
        )
        return {"workflow_id": wf_id, "version_id": ver_resp.json()["id"]}

    async def test_start_run(self, client: AsyncClient, run_setup: dict) -> None:
        resp = await client.post(
            f"/api/v1/runs/workflows/{run_setup['workflow_id']}/run",
            json={"inputs": {"x": 1}},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "pending"
        assert data["inputs"] == {"x": 1}

    async def test_start_run_no_version(self, client: AsyncClient) -> None:
        wf_resp = await client.post("/api/v1/workflows", json={"name": "no-version-wf"})
        wf_id = wf_resp.json()["id"]
        resp = await client.post(f"/api/v1/runs/workflows/{wf_id}/run", json={})
        assert resp.status_code == 400

    async def test_start_run_workflow_not_found(self, client: AsyncClient) -> None:
        resp = await client.post(f"/api/v1/runs/workflows/{uuid4()}/run", json={})
        assert resp.status_code == 404

    async def test_get_run(self, client: AsyncClient, run_setup: dict) -> None:
        run_resp = await client.post(
            f"/api/v1/runs/workflows/{run_setup['workflow_id']}/run",
            json={},
        )
        run_id = run_resp.json()["id"]
        resp = await client.get(f"/api/v1/runs/{run_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == run_id

    async def test_get_run_not_found(self, client: AsyncClient) -> None:
        resp = await client.get(f"/api/v1/runs/{uuid4()}")
        assert resp.status_code == 404

    async def test_cancel_run(self, client: AsyncClient, run_setup: dict) -> None:
        run_resp = await client.post(
            f"/api/v1/runs/workflows/{run_setup['workflow_id']}/run",
            json={},
        )
        run_id = run_resp.json()["id"]
        resp = await client.post(f"/api/v1/runs/{run_id}/cancel")
        assert resp.status_code == 200
        assert resp.json()["status"] == "cancelled"

    async def test_cancel_already_cancelled(self, client: AsyncClient, run_setup: dict) -> None:
        run_resp = await client.post(
            f"/api/v1/runs/workflows/{run_setup['workflow_id']}/run",
            json={},
        )
        run_id = run_resp.json()["id"]
        await client.post(f"/api/v1/runs/{run_id}/cancel")
        resp = await client.post(f"/api/v1/runs/{run_id}/cancel")
        assert resp.status_code == 409

    async def test_resume_run_not_found(self, client: AsyncClient) -> None:
        resp = await client.post(f"/api/v1/runs/{uuid4()}/resume", json={})
        assert resp.status_code == 404

    async def test_resume_run_not_paused(self, client: AsyncClient, run_setup: dict) -> None:
        # Create a run (status=pending), then cancel it (terminal state)
        run_resp = await client.post(
            f"/api/v1/runs/workflows/{run_setup['workflow_id']}/run",
            json={},
        )
        run_id = run_resp.json()["id"]
        await client.post(f"/api/v1/runs/{run_id}/cancel")
        # Attempt resume on a cancelled (terminal) run
        resp = await client.post(f"/api/v1/runs/{run_id}/resume", json={})
        assert resp.status_code == 409

    async def test_cancel_run_not_found(self, client: AsyncClient) -> None:
        resp = await client.post(f"/api/v1/runs/{uuid4()}/cancel")
        assert resp.status_code == 404

    async def test_list_node_runs(self, client: AsyncClient, run_setup: dict) -> None:
        run_resp = await client.post(
            f"/api/v1/runs/workflows/{run_setup['workflow_id']}/run",
            json={},
        )
        run_id = run_resp.json()["id"]
        resp = await client.get(f"/api/v1/runs/{run_id}/nodes")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_list_run_events(self, client: AsyncClient, run_setup: dict) -> None:
        run_resp = await client.post(
            f"/api/v1/runs/workflows/{run_setup['workflow_id']}/run",
            json={},
        )
        run_id = run_resp.json()["id"]
        resp = await client.get(f"/api/v1/runs/{run_id}/events")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_list_run_events_with_after(self, client: AsyncClient, run_setup: dict) -> None:
        run_resp = await client.post(
            f"/api/v1/runs/workflows/{run_setup['workflow_id']}/run",
            json={},
        )
        run_id = run_resp.json()["id"]
        resp = await client.get(f"/api/v1/runs/{run_id}/events", params={"after": 0})
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


class TestWebhookTrigger:
    @pytest.fixture
    async def trigger_setup(self, client: AsyncClient) -> dict:
        wf_resp = await client.post("/api/v1/workflows", json={"name": "hook-wf"})
        wf_id = wf_resp.json()["id"]
        defn = {
            "version": "1.0",
            "metadata": {"name": "test-wf", "description": "test"},
            "inputs": {},
            "outputs": {},
            "nodes": [
                {"id": "start", "type": "start", "label": "Start"},
                {"id": "end", "type": "end", "label": "End"},
            ],
            "edges": [{"id": "e1", "source": "start", "target": "end"}],
        }
        await client.post(
            f"/api/v1/workflows/{wf_id}/versions",
            json={"definition": defn, "is_published": True},
        )
        return {"workflow_id": wf_id}

    async def test_create_webhook(self, client: AsyncClient, trigger_setup: dict) -> None:
        resp = await client.post(
            f"/api/v1/workflows/{trigger_setup['workflow_id']}/triggers/webhook",
            json={"key": "my-hook"},
        )
        assert resp.status_code == 201
        assert resp.json()["key"] == "my-hook"

    async def test_fire_webhook(self, client: AsyncClient, trigger_setup: dict) -> None:
        await client.post(
            f"/api/v1/workflows/{trigger_setup['workflow_id']}/triggers/webhook",
            json={"key": "fire-me"},
        )
        resp = await client.post("/api/v1/triggers/webhook/fire-me", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "pending"
        assert "run_id" in data

    async def test_fire_unknown_webhook(self, client: AsyncClient) -> None:
        resp = await client.post("/api/v1/triggers/webhook/unknown", json={})
        assert resp.status_code == 404

    async def test_create_webhook_workflow_not_found(self, client: AsyncClient) -> None:
        resp = await client.post(
            f"/api/v1/workflows/{uuid4()}/triggers/webhook",
            json={"key": "orphan-hook"},
        )
        assert resp.status_code == 404

    async def test_fire_webhook_inactive(self, client: AsyncClient, trigger_setup: dict) -> None:
        # Create webhook, then deactivate it via the DB
        create_resp = await client.post(
            f"/api/v1/workflows/{trigger_setup['workflow_id']}/triggers/webhook",
            json={"key": "inactive-hook"},
        )
        trigger_id = UUID(create_resp.json()["id"])

        # Deactivate via direct DB access
        from flowkit.persistence.models import webhook_triggers

        app = client._transport.app  # type: ignore[attr-defined]
        from flowkit.api.deps import get_db_connection

        async for conn in app.dependency_overrides[get_db_connection]():
            await conn.execute(
                webhook_triggers.update()
                .where(webhook_triggers.c.id == trigger_id)
                .values(is_active=False)
            )

        resp = await client.post("/api/v1/triggers/webhook/inactive-hook", json={})
        assert resp.status_code == 409

    async def test_fire_webhook_no_version(self, client: AsyncClient) -> None:
        # Create workflow WITHOUT a published version
        wf_resp = await client.post("/api/v1/workflows", json={"name": "no-ver-wf"})
        wf_id = wf_resp.json()["id"]
        # Create webhook on it
        await client.post(
            f"/api/v1/workflows/{wf_id}/triggers/webhook",
            json={"key": "no-version-hook"},
        )
        resp = await client.post("/api/v1/triggers/webhook/no-version-hook", json={})
        assert resp.status_code == 400

    async def test_fire_webhook_with_input_mapping(
        self, client: AsyncClient, trigger_setup: dict
    ) -> None:
        # Create webhook with input_mapping
        await client.post(
            f"/api/v1/workflows/{trigger_setup['workflow_id']}/triggers/webhook",
            json={"key": "mapped-hook", "input_mapping": {"workflow_param": "payload_field"}},
        )
        resp = await client.post(
            "/api/v1/triggers/webhook/mapped-hook",
            json={"payload_field": "hello"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "pending"
        assert "run_id" in data
