"""Tests for API routes."""

from __future__ import annotations

from uuid import uuid4

import pytest
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
