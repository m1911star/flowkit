"""SQLAlchemy Core table definitions for Flowkit persistence layer.

All 7 tables per the persistence spec: workflows, workflow_versions, workflow_runs,
node_runs, run_events, webhook_triggers, schedule_triggers.
"""


import sqlalchemy as sa
from sqlalchemy import MetaData

metadata = MetaData()

# --------------------------------------------------------------------------- #
# workflows
# --------------------------------------------------------------------------- #
workflows = sa.Table(
    "workflows",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True),
    sa.Column("name", sa.String(255), nullable=False),
    sa.Column("description", sa.Text, nullable=True),
    sa.Column(
        "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    ),
    sa.Column(
        "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    ),
)

# --------------------------------------------------------------------------- #
# workflow_versions
# --------------------------------------------------------------------------- #
workflow_versions = sa.Table(
    "workflow_versions",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True),
    sa.Column(
        "workflow_id",
        sa.Uuid,
        sa.ForeignKey("workflows.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column("version", sa.Integer, nullable=False),
    sa.Column("definition", sa.JSON, nullable=False),
    sa.Column("checksum", sa.String(64), nullable=False),
    sa.Column("is_published", sa.Boolean, nullable=False, server_default=sa.text("false")),
    sa.Column(
        "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    ),
    sa.UniqueConstraint("workflow_id", "version", name="uq_workflow_version"),
)

# --------------------------------------------------------------------------- #
# workflow_runs
# --------------------------------------------------------------------------- #
workflow_runs = sa.Table(
    "workflow_runs",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True),
    sa.Column(
        "workflow_id",
        sa.Uuid,
        sa.ForeignKey("workflows.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column(
        "workflow_version_id",
        sa.Uuid,
        sa.ForeignKey("workflow_versions.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column(
        "status",
        sa.String(20),
        nullable=False,
        server_default=sa.text("'pending'"),
    ),
    sa.Column("inputs", sa.JSON, nullable=True),
    sa.Column("outputs", sa.JSON, nullable=True),
    sa.Column("variable_pool", sa.JSON, nullable=True),
    sa.Column("error", sa.Text, nullable=True),
    sa.Column("trigger_type", sa.String(20), nullable=True),
    sa.Column("trigger_id", sa.Uuid, nullable=True),
    sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column(
        "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    ),
    sa.Column(
        "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    ),
    sa.Index("ix_workflow_runs_workflow_id", "workflow_id"),
    sa.Index("ix_workflow_runs_status", "status"),
)

# --------------------------------------------------------------------------- #
# node_runs
# --------------------------------------------------------------------------- #
node_runs = sa.Table(
    "node_runs",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True),
    sa.Column(
        "workflow_run_id",
        sa.Uuid,
        sa.ForeignKey("workflow_runs.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column("node_id", sa.String(255), nullable=False),
    sa.Column("node_type", sa.String(50), nullable=False),
    sa.Column(
        "status",
        sa.String(20),
        nullable=False,
        server_default=sa.text("'pending'"),
    ),
    sa.Column("inputs", sa.JSON, nullable=True),
    sa.Column("outputs", sa.JSON, nullable=True),
    sa.Column("error", sa.Text, nullable=True),
    sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column(
        "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    ),
    sa.UniqueConstraint("workflow_run_id", "node_id", name="uq_run_node"),
    sa.Index("ix_node_runs_workflow_run_id", "workflow_run_id"),
)

# --------------------------------------------------------------------------- #
# run_events
# --------------------------------------------------------------------------- #
run_events = sa.Table(
    "run_events",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True),
    sa.Column(
        "workflow_run_id",
        sa.Uuid,
        sa.ForeignKey("workflow_runs.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column("sequence", sa.BigInteger, nullable=False),
    sa.Column("event_type", sa.String(50), nullable=False),
    sa.Column("node_id", sa.String(255), nullable=True),
    sa.Column("payload", sa.JSON, nullable=True),
    sa.Column(
        "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    ),
    sa.UniqueConstraint("workflow_run_id", "sequence", name="uq_run_event_sequence"),
    sa.Index("ix_run_events_workflow_run_id", "workflow_run_id"),
)

# --------------------------------------------------------------------------- #
# webhook_triggers
# --------------------------------------------------------------------------- #
webhook_triggers = sa.Table(
    "webhook_triggers",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True),
    sa.Column(
        "workflow_id",
        sa.Uuid,
        sa.ForeignKey("workflows.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column("key", sa.String(255), nullable=False, unique=True),
    sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
    sa.Column("input_mapping", sa.JSON, nullable=True),
    sa.Column(
        "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    ),
    sa.Column(
        "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    ),
)

# --------------------------------------------------------------------------- #
# schedule_triggers
# --------------------------------------------------------------------------- #
schedule_triggers = sa.Table(
    "schedule_triggers",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True),
    sa.Column(
        "workflow_id",
        sa.Uuid,
        sa.ForeignKey("workflows.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column("cron_expression", sa.String(100), nullable=False),
    sa.Column("timezone", sa.String(50), nullable=False, server_default=sa.text("'UTC'")),
    sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
    sa.Column("inputs", sa.JSON, nullable=True),
    sa.Column("next_fire_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("last_fired_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column(
        "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    ),
    sa.Column(
        "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    ),
    sa.Index("ix_schedule_triggers_next_fire_at", "next_fire_at"),
)

# --------------------------------------------------------------------------- #
# dead_letter_queue
# --------------------------------------------------------------------------- #
dead_letter_queue = sa.Table(
    "dead_letter_queue",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True),
    sa.Column(
        "workflow_run_id",
        sa.Uuid,
        sa.ForeignKey("workflow_runs.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column("error", sa.Text, nullable=False),
    sa.Column("node_id", sa.String(100), nullable=True),
    sa.Column("attempt", sa.Integer, nullable=False, server_default=sa.text("1")),
    sa.Column("max_retries", sa.Integer, nullable=False, server_default=sa.text("3")),
    sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'pending'")),
    sa.Column("retried_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column(
        "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    ),
    sa.Index("ix_dead_letter_queue_status", "status"),
    sa.Index("ix_dead_letter_queue_workflow_run_id", "workflow_run_id"),
)
