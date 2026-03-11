"""Tests for database model definitions (structural, no DB needed)."""

import sqlalchemy as sa

from flowkit.persistence.models import (
    metadata,
    node_runs,
    run_events,
    schedule_triggers,
    webhook_triggers,
    workflow_runs,
    workflow_versions,
    workflows,
)


def test_metadata_has_all_tables() -> None:
    table_names = set(metadata.tables.keys())
    expected = {
        "workflows",
        "workflow_versions",
        "workflow_runs",
        "node_runs",
        "run_events",
        "webhook_triggers",
        "schedule_triggers",
    }
    assert table_names == expected


def test_workflows_columns() -> None:
    cols = {c.name for c in workflows.columns}
    assert cols == {"id", "name", "description", "created_at", "updated_at"}
    assert workflows.c.id.primary_key


def test_workflow_versions_columns() -> None:
    cols = {c.name for c in workflow_versions.columns}
    assert "workflow_id" in cols
    assert "version" in cols
    assert "definition" in cols
    assert "checksum" in cols
    assert "is_published" in cols


def test_workflow_versions_unique_constraint() -> None:
    constraints = [c for c in workflow_versions.constraints if isinstance(c, sa.UniqueConstraint)]
    constraint_cols = set()
    for c in constraints:
        constraint_cols.update(col.name for col in c.columns)
    assert "workflow_id" in constraint_cols
    assert "version" in constraint_cols


def test_workflow_runs_columns() -> None:
    cols = {c.name for c in workflow_runs.columns}
    expected = {
        "id",
        "workflow_id",
        "workflow_version_id",
        "status",
        "inputs",
        "outputs",
        "variable_pool",
        "error",
        "trigger_type",
        "trigger_id",
        "started_at",
        "completed_at",
        "created_at",
        "updated_at",
    }
    assert cols == expected


def test_workflow_runs_indexes() -> None:
    index_names = {idx.name for idx in workflow_runs.indexes}
    assert "ix_workflow_runs_workflow_id" in index_names
    assert "ix_workflow_runs_status" in index_names


def test_node_runs_columns() -> None:
    cols = {c.name for c in node_runs.columns}
    expected = {
        "id",
        "workflow_run_id",
        "node_id",
        "node_type",
        "status",
        "inputs",
        "outputs",
        "error",
        "started_at",
        "completed_at",
        "created_at",
    }
    assert cols == expected


def test_node_runs_unique_constraint() -> None:
    constraints = [c for c in node_runs.constraints if isinstance(c, sa.UniqueConstraint)]
    constraint_cols = set()
    for c in constraints:
        constraint_cols.update(col.name for col in c.columns)
    assert "workflow_run_id" in constraint_cols
    assert "node_id" in constraint_cols


def test_run_events_columns() -> None:
    cols = {c.name for c in run_events.columns}
    expected = {
        "id",
        "workflow_run_id",
        "sequence",
        "event_type",
        "node_id",
        "payload",
        "created_at",
    }
    assert cols == expected


def test_run_events_unique_sequence() -> None:
    constraints = [c for c in run_events.constraints if isinstance(c, sa.UniqueConstraint)]
    constraint_cols = set()
    for c in constraints:
        constraint_cols.update(col.name for col in c.columns)
    assert "workflow_run_id" in constraint_cols
    assert "sequence" in constraint_cols


def test_webhook_triggers_columns() -> None:
    cols = {c.name for c in webhook_triggers.columns}
    expected = {
        "id",
        "workflow_id",
        "key",
        "is_active",
        "input_mapping",
        "created_at",
        "updated_at",
    }
    assert cols == expected


def test_webhook_triggers_key_unique() -> None:
    assert webhook_triggers.c.key.unique


def test_schedule_triggers_columns() -> None:
    cols = {c.name for c in schedule_triggers.columns}
    expected = {
        "id",
        "workflow_id",
        "cron_expression",
        "timezone",
        "is_active",
        "inputs",
        "next_fire_at",
        "last_fired_at",
        "created_at",
        "updated_at",
    }
    assert cols == expected


def test_schedule_triggers_index() -> None:
    index_names = {idx.name for idx in schedule_triggers.indexes}
    assert "ix_schedule_triggers_next_fire_at" in index_names


def test_all_tables_have_id_primary_key() -> None:
    for table in metadata.tables.values():
        assert "id" in {c.name for c in table.columns}, f"{table.name} missing id column"
        assert table.c.id.primary_key, f"{table.name}.id not primary key"


def test_all_tables_have_created_at() -> None:
    for table in metadata.tables.values():
        assert "created_at" in {c.name for c in table.columns}, f"{table.name} missing created_at"
