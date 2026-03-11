"""Unit tests for worker settings."""

from __future__ import annotations

from flowkit.worker.settings import WorkerSettings
from flowkit.worker.tasks import execute_workflow_run, resume_workflow_run


def test_worker_settings_has_required_functions():
    """Test that WorkerSettings contains the required task functions."""
    assert execute_workflow_run in WorkerSettings.functions
    assert resume_workflow_run in WorkerSettings.functions
    assert len(WorkerSettings.functions) == 2


def test_worker_settings_has_redis_settings():
    """Test that WorkerSettings has redis_settings configured."""
    assert hasattr(WorkerSettings, "redis_settings")
    assert WorkerSettings.redis_settings is not None


def test_worker_settings_has_max_jobs():
    """Test that WorkerSettings has max_jobs configured."""
    assert hasattr(WorkerSettings, "max_jobs")
    assert isinstance(WorkerSettings.max_jobs, int)
    assert WorkerSettings.max_jobs > 0


def test_worker_settings_has_job_timeout():
    """Test that WorkerSettings has job_timeout configured."""
    assert hasattr(WorkerSettings, "job_timeout")
    assert isinstance(WorkerSettings.job_timeout, int)
    assert WorkerSettings.job_timeout == 3600
