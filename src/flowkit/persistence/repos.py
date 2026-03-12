"""Repository layer — async CRUD operations for all Flowkit entities.

Uses SQLAlchemy Core with async connections. All methods take an AsyncConnection
as first argument for transaction control by the caller.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa

from flowkit.persistence.models import (
    node_runs,
    run_events,
    schedule_triggers,
    webhook_triggers,
    workflow_runs,
    workflow_versions,
    workflows,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncConnection


def _now() -> datetime:
    return datetime.now(UTC)


# --------------------------------------------------------------------------- #
# WorkflowRepo
# --------------------------------------------------------------------------- #
class WorkflowRepo:
    """CRUD for the workflows table."""

    async def create(
        self,
        conn: AsyncConnection,
        *,
        name: str,
        description: str | None = None,
    ) -> dict[str, Any]:
        row_id = uuid.uuid4()
        now = _now()
        await conn.execute(
            workflows.insert().values(
                id=row_id,
                name=name,
                description=description,
                created_at=now,
                updated_at=now,
            )
        )
        return {
            "id": row_id,
            "name": name,
            "description": description,
            "created_at": now,
            "updated_at": now,
        }

    async def get(self, conn: AsyncConnection, workflow_id: uuid.UUID) -> dict[str, Any] | None:
        result = await conn.execute(workflows.select().where(workflows.c.id == workflow_id))
        row = result.mappings().first()
        return dict(row) if row else None

    async def list_all(
        self, conn: AsyncConnection, *, limit: int = 50, offset: int = 0
    ) -> list[dict[str, Any]]:
        result = await conn.execute(
            workflows.select().order_by(workflows.c.created_at.desc()).limit(limit).offset(offset)
        )
        return [dict(r) for r in result.mappings().all()]

    async def update(
        self,
        conn: AsyncConnection,
        workflow_id: uuid.UUID,
        **fields: Any,
    ) -> bool:
        fields["updated_at"] = _now()
        result = await conn.execute(
            workflows.update().where(workflows.c.id == workflow_id).values(**fields)
        )
        return result.rowcount > 0

    async def delete(self, conn: AsyncConnection, workflow_id: uuid.UUID) -> bool:
        result = await conn.execute(workflows.delete().where(workflows.c.id == workflow_id))
        return result.rowcount > 0


# --------------------------------------------------------------------------- #
# WorkflowVersionRepo
# --------------------------------------------------------------------------- #
class WorkflowVersionRepo:
    """CRUD for workflow_versions table."""

    async def create(
        self,
        conn: AsyncConnection,
        *,
        workflow_id: uuid.UUID,
        version: int,
        definition: dict[str, Any],
        checksum: str,
        is_published: bool = False,
    ) -> dict[str, Any]:
        row_id = uuid.uuid4()
        now = _now()
        await conn.execute(
            workflow_versions.insert().values(
                id=row_id,
                workflow_id=workflow_id,
                version=version,
                definition=definition,
                checksum=checksum,
                is_published=is_published,
                created_at=now,
            )
        )
        return {
            "id": row_id,
            "workflow_id": workflow_id,
            "version": version,
            "definition": definition,
            "checksum": checksum,
            "is_published": is_published,
            "created_at": now,
        }

    async def get(self, conn: AsyncConnection, version_id: uuid.UUID) -> dict[str, Any] | None:
        result = await conn.execute(
            workflow_versions.select().where(workflow_versions.c.id == version_id)
        )
        row = result.mappings().first()
        return dict(row) if row else None

    async def get_by_workflow_and_version(
        self,
        conn: AsyncConnection,
        workflow_id: uuid.UUID,
        version: int,
    ) -> dict[str, Any] | None:
        result = await conn.execute(
            workflow_versions.select().where(
                sa.and_(
                    workflow_versions.c.workflow_id == workflow_id,
                    workflow_versions.c.version == version,
                )
            )
        )
        row = result.mappings().first()
        return dict(row) if row else None

    async def get_latest(
        self, conn: AsyncConnection, workflow_id: uuid.UUID
    ) -> dict[str, Any] | None:
        result = await conn.execute(
            workflow_versions.select()
            .where(workflow_versions.c.workflow_id == workflow_id)
            .order_by(workflow_versions.c.version.desc())
            .limit(1)
        )
        row = result.mappings().first()
        return dict(row) if row else None

    async def get_published(
        self, conn: AsyncConnection, workflow_id: uuid.UUID
    ) -> dict[str, Any] | None:
        result = await conn.execute(
            workflow_versions.select().where(
                sa.and_(
                    workflow_versions.c.workflow_id == workflow_id,
                    workflow_versions.c.is_published == True,  # noqa: E712
                )
            )
        )
        row = result.mappings().first()
        return dict(row) if row else None

    async def list_by_workflow(
        self,
        conn: AsyncConnection,
        workflow_id: uuid.UUID,
    ) -> list[dict[str, Any]]:
        result = await conn.execute(
            workflow_versions.select()
            .where(workflow_versions.c.workflow_id == workflow_id)
            .order_by(workflow_versions.c.version.desc())
        )
        return [dict(r) for r in result.mappings().all()]

    async def publish(self, conn: AsyncConnection, version_id: uuid.UUID) -> bool:
        result = await conn.execute(
            workflow_versions.update()
            .where(workflow_versions.c.id == version_id)
            .values(is_published=True)
        )
        return result.rowcount > 0


# --------------------------------------------------------------------------- #
# WorkflowRunRepo
# --------------------------------------------------------------------------- #
class WorkflowRunRepo:
    """CRUD for workflow_runs table."""

    async def create(
        self,
        conn: AsyncConnection,
        *,
        workflow_id: uuid.UUID,
        workflow_version_id: uuid.UUID,
        inputs: dict[str, Any] | None = None,
        trigger_type: str | None = None,
        trigger_id: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        row_id = uuid.uuid4()
        now = _now()
        await conn.execute(
            workflow_runs.insert().values(
                id=row_id,
                workflow_id=workflow_id,
                workflow_version_id=workflow_version_id,
                status="pending",
                inputs=inputs,
                trigger_type=trigger_type,
                trigger_id=trigger_id,
                created_at=now,
                updated_at=now,
            )
        )
        return {
            "id": row_id,
            "workflow_id": workflow_id,
            "workflow_version_id": workflow_version_id,
            "status": "pending",
            "inputs": inputs,
            "trigger_type": trigger_type,
            "trigger_id": trigger_id,
            "created_at": now,
            "updated_at": now,
        }

    async def get(self, conn: AsyncConnection, run_id: uuid.UUID) -> dict[str, Any] | None:
        result = await conn.execute(workflow_runs.select().where(workflow_runs.c.id == run_id))
        row = result.mappings().first()
        return dict(row) if row else None

    async def update_status(
        self,
        conn: AsyncConnection,
        run_id: uuid.UUID,
        *,
        status: str,
        expected_status: str | None = None,
        **extra_fields: Any,
    ) -> bool:
        """Update run status with optimistic locking via expected_status."""
        conditions = [workflow_runs.c.id == run_id]
        if expected_status is not None:
            conditions.append(workflow_runs.c.status == expected_status)
        values: dict[str, Any] = {"status": status, "updated_at": _now(), **extra_fields}
        result = await conn.execute(
            workflow_runs.update().where(sa.and_(*conditions)).values(**values)
        )
        return result.rowcount > 0

    async def list_by_workflow(
        self,
        conn: AsyncConnection,
        workflow_id: uuid.UUID,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        result = await conn.execute(
            workflow_runs.select()
            .where(workflow_runs.c.workflow_id == workflow_id)
            .order_by(workflow_runs.c.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return [dict(r) for r in result.mappings().all()]


# --------------------------------------------------------------------------- #
# NodeRunRepo
# --------------------------------------------------------------------------- #
class NodeRunRepo:
    """CRUD for node_runs table."""

    async def create(
        self,
        conn: AsyncConnection,
        *,
        workflow_run_id: uuid.UUID,
        node_id: str,
        node_type: str,
    ) -> dict[str, Any]:
        row_id = uuid.uuid4()
        now = _now()
        await conn.execute(
            node_runs.insert().values(
                id=row_id,
                workflow_run_id=workflow_run_id,
                node_id=node_id,
                node_type=node_type,
                status="pending",
                created_at=now,
            )
        )
        return {
            "id": row_id,
            "workflow_run_id": workflow_run_id,
            "node_id": node_id,
            "node_type": node_type,
            "status": "pending",
            "created_at": now,
        }

    async def get(self, conn: AsyncConnection, node_run_id: uuid.UUID) -> dict[str, Any] | None:
        result = await conn.execute(node_runs.select().where(node_runs.c.id == node_run_id))
        row = result.mappings().first()
        return dict(row) if row else None

    async def get_by_run_and_node(
        self,
        conn: AsyncConnection,
        workflow_run_id: uuid.UUID,
        node_id: str,
    ) -> dict[str, Any] | None:
        result = await conn.execute(
            node_runs.select().where(
                sa.and_(
                    node_runs.c.workflow_run_id == workflow_run_id,
                    node_runs.c.node_id == node_id,
                )
            )
        )
        row = result.mappings().first()
        return dict(row) if row else None

    async def update_status(
        self,
        conn: AsyncConnection,
        node_run_id: uuid.UUID,
        *,
        status: str,
        **extra_fields: Any,
    ) -> bool:
        values: dict[str, Any] = {"status": status, **extra_fields}
        result = await conn.execute(
            node_runs.update().where(node_runs.c.id == node_run_id).values(**values)
        )
        return result.rowcount > 0

    async def list_by_run(
        self,
        conn: AsyncConnection,
        workflow_run_id: uuid.UUID,
    ) -> list[dict[str, Any]]:
        result = await conn.execute(
            node_runs.select()
            .where(node_runs.c.workflow_run_id == workflow_run_id)
            .order_by(node_runs.c.created_at.asc())
        )
        return [dict(r) for r in result.mappings().all()]


# --------------------------------------------------------------------------- #
# RunEventRepo
# --------------------------------------------------------------------------- #
class RunEventRepo:
    """CRUD for run_events table."""

    async def create(
        self,
        conn: AsyncConnection,
        *,
        workflow_run_id: uuid.UUID,
        sequence: int,
        event_type: str,
        node_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        row_id = uuid.uuid4()
        now = _now()
        await conn.execute(
            run_events.insert().values(
                id=row_id,
                workflow_run_id=workflow_run_id,
                sequence=sequence,
                event_type=event_type,
                node_id=node_id,
                payload=payload,
                created_at=now,
            )
        )
        return {
            "id": row_id,
            "workflow_run_id": workflow_run_id,
            "sequence": sequence,
            "event_type": event_type,
            "node_id": node_id,
            "payload": payload,
            "created_at": now,
        }

    async def list_by_run(
        self,
        conn: AsyncConnection,
        workflow_run_id: uuid.UUID,
        *,
        after_sequence: int | None = None,
    ) -> list[dict[str, Any]]:
        query = run_events.select().where(run_events.c.workflow_run_id == workflow_run_id)
        if after_sequence is not None:
            query = query.where(run_events.c.sequence > after_sequence)
        result = await conn.execute(query.order_by(run_events.c.sequence.asc()))
        return [dict(r) for r in result.mappings().all()]

    async def get_latest_sequence(
        self,
        conn: AsyncConnection,
        workflow_run_id: uuid.UUID,
    ) -> int:
        result = await conn.execute(
            sa.select(sa.func.coalesce(sa.func.max(run_events.c.sequence), 0)).where(
                run_events.c.workflow_run_id == workflow_run_id
            )
        )
        value: int = result.scalar_one()
        return value


# --------------------------------------------------------------------------- #
# WebhookTriggerRepo
# --------------------------------------------------------------------------- #
class WebhookTriggerRepo:
    """CRUD for webhook_triggers table."""

    async def create(
        self,
        conn: AsyncConnection,
        *,
        workflow_id: uuid.UUID,
        key: str,
        input_mapping: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        row_id = uuid.uuid4()
        now = _now()
        await conn.execute(
            webhook_triggers.insert().values(
                id=row_id,
                workflow_id=workflow_id,
                key=key,
                is_active=True,
                input_mapping=input_mapping,
                created_at=now,
                updated_at=now,
            )
        )
        return {
            "id": row_id,
            "workflow_id": workflow_id,
            "key": key,
            "is_active": True,
            "input_mapping": input_mapping,
            "created_at": now,
            "updated_at": now,
        }

    async def get_by_key(self, conn: AsyncConnection, key: str) -> dict[str, Any] | None:
        result = await conn.execute(webhook_triggers.select().where(webhook_triggers.c.key == key))
        row = result.mappings().first()
        return dict(row) if row else None

    async def set_active(
        self, conn: AsyncConnection, trigger_id: uuid.UUID, *, active: bool
    ) -> bool:
        result = await conn.execute(
            webhook_triggers.update()
            .where(webhook_triggers.c.id == trigger_id)
            .values(is_active=active, updated_at=_now())
        )
        return result.rowcount > 0


# --------------------------------------------------------------------------- #
# ScheduleTriggerRepo
# --------------------------------------------------------------------------- #
class ScheduleTriggerRepo:
    """CRUD for schedule_triggers table."""

    async def create(
        self,
        conn: AsyncConnection,
        *,
        workflow_id: uuid.UUID,
        cron_expression: str,
        timezone: str = "UTC",
        inputs: dict[str, Any] | None = None,
        next_fire_at: datetime | None = None,
    ) -> dict[str, Any]:
        row_id = uuid.uuid4()
        now = _now()
        await conn.execute(
            schedule_triggers.insert().values(
                id=row_id,
                workflow_id=workflow_id,
                cron_expression=cron_expression,
                timezone=timezone,
                is_active=True,
                inputs=inputs,
                next_fire_at=next_fire_at,
                created_at=now,
                updated_at=now,
            )
        )
        return {
            "id": row_id,
            "workflow_id": workflow_id,
            "cron_expression": cron_expression,
            "timezone": timezone,
            "is_active": True,
            "inputs": inputs,
            "next_fire_at": next_fire_at,
            "created_at": now,
            "updated_at": now,
        }

    async def get_due_triggers(
        self,
        conn: AsyncConnection,
        now: datetime,
    ) -> list[dict[str, Any]]:
        """Get active triggers that are due to fire."""
        result = await conn.execute(
            schedule_triggers.select()
            .where(
                sa.and_(
                    schedule_triggers.c.is_active == True,  # noqa: E712
                    schedule_triggers.c.next_fire_at <= now,
                )
            )
            .order_by(schedule_triggers.c.next_fire_at.asc())
        )
        return [dict(r) for r in result.mappings().all()]

    async def update_after_fire(
        self,
        conn: AsyncConnection,
        trigger_id: uuid.UUID,
        *,
        last_fired_at: datetime,
        next_fire_at: datetime,
    ) -> bool:
        result = await conn.execute(
            schedule_triggers.update()
            .where(schedule_triggers.c.id == trigger_id)
            .values(
                last_fired_at=last_fired_at,
                next_fire_at=next_fire_at,
                updated_at=_now(),
            )
        )
        return result.rowcount > 0
