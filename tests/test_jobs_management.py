import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import uuid
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.services.worker import background_worker
from app.storage import InvalidStateTransitionError, JobStore, job_store

client = TestClient(app)

SAMPLE_SCENES = [
    {
        "narration": "Testing persistent background job transitions.",
        "duration_seconds": 3.0,
        "visual_description": "Data pipelines and background worker status graphs."
    }
]


# ============================================================================
# 1. STATE MACHINE & INVALID TRANSITIONS
# ============================================================================

def test_valid_lifecycle_transitions():
    job_id = f"test-lifecycle-{uuid.uuid4()}"
    initial = {
        "title": "Lifecycle Test",
        "aspect_ratio": "16:9",
        "resolution": "1080p",
        "duration_seconds": 3.0,
        "scenes_count": 1,
        "scenes": SAMPLE_SCENES
    }
    # 1. Create -> queued
    created = job_store.create_job(job_id, initial)
    assert created["status"] == "queued"
    assert created["progress"] == 0.0

    # 2. Queued -> running
    running = job_store.transition_state(
        job_id, to_status="running", to_stage="rendering", progress=50.0, stage_message="Halfway done."
    )
    assert running["status"] == "running"
    assert running["progress"] == 50.0
    assert running["started_at_utc"] is not None

    # 3. Running -> completed
    completed = job_store.transition_state(
        job_id, to_status="completed", to_stage="completed", progress=100.0, stage_message="Finished.",
        manifest={"test": True}
    )
    assert completed["status"] == "completed"
    assert completed["progress"] == 100.0
    assert completed["completed_at_utc"] is not None


def test_invalid_lifecycle_transitions():
    job_id = f"test-invalid-trans-{uuid.uuid4()}"
    initial = {
        "title": "Invalid Transitions Test",
        "aspect_ratio": "16:9",
        "resolution": "1080p",
        "duration_seconds": 3.0,
        "scenes_count": 1,
        "scenes": SAMPLE_SCENES
    }
    job_store.create_job(job_id, initial)
    job_store.transition_state(job_id, to_status="running")
    job_store.transition_state(job_id, to_status="completed")

    # Completed -> cancelled is illegal
    with pytest.raises(InvalidStateTransitionError) as exc_info:
        job_store.transition_state(job_id, to_status="cancelled")
    assert "Cannot transition job from 'completed' to 'cancelled'" in str(exc_info.value)

    # Completed -> running is illegal
    with pytest.raises(InvalidStateTransitionError) as exc_info:
        job_store.transition_state(job_id, to_status="running")
    assert "Cannot transition job from 'completed' to 'running'" in str(exc_info.value)


# ============================================================================
# 2. SQLITE PERSISTENCE SURVIVES APPLICATION RESTART
# ============================================================================

def test_persistence_survives_restart():
    job_id = f"test-persist-{uuid.uuid4()}"
    initial = {
        "title": "Persistence Test",
        "aspect_ratio": "9:16",
        "resolution": "1080p",
        "duration_seconds": 3.0,
        "scenes_count": 1,
        "scenes": SAMPLE_SCENES
    }
    # Create with first store instance
    job_store.create_job(job_id, initial)
    job_store.transition_state(job_id, to_status="running", to_stage="processing", progress=42.0)

    # Simulate restart by creating a brand-new JobStore instance connecting to SQLite
    restarted_store = JobStore()
    recovered_job = restarted_store.get_job(job_id)

    assert recovered_job is not None
    assert recovered_job["job_id"] == job_id
    assert recovered_job["title"] == "Persistence Test"
    assert recovered_job["status"] == "running"
    assert recovered_job["progress"] == 42.0
    assert recovered_job["current_stage"] == "processing"


# ============================================================================
# 3. IDEMPOTENCY PREVENTS DUPLICATE SUBMISSIONS
# ============================================================================

def test_idempotent_duplicate_submission():
    idempotency_key = f"idemp-key-{uuid.uuid4()}"
    payload = {
        "title": "Idempotent Job Submission",
        "aspect_ratio": "16:9",
        "scenes": SAMPLE_SCENES
    }
    headers = {"Idempotency-Key": idempotency_key}

    # 1. First submission
    res1 = client.post("/v1/jobs", json=payload, headers=headers)
    assert res1.status_code == 202
    job1_data = res1.json()
    job1_id = job1_data["job_id"]

    # 2. Repeated submission with identical key
    res2 = client.post("/v1/jobs", json=payload, headers=headers)
    assert res2.status_code == 202
    job2_data = res2.json()
    job2_id = job2_data["job_id"]

    # Must return exact same job without double queueing
    assert job1_id == job2_id
    assert job2_data["title"] == "Idempotent Job Submission"


# ============================================================================
# 4. RECOVERY OF STUCK / ABANDONED RUNNING JOBS
# ============================================================================

def test_stuck_jobs_recovery_retry_and_exhaustion():
    # Job A: running with retry_count=0 -> recovered and re-queued with retry_count=1
    job_a_id = f"test-stuck-a-{uuid.uuid4()}"
    job_store.create_job(job_a_id, {
        "title": "Stuck Job A", "aspect_ratio": "16:9", "resolution": "1080p",
        "duration_seconds": 3.0, "scenes_count": 1, "scenes": SAMPLE_SCENES
    })
    job_store.transition_state(job_a_id, to_status="running")

    # Job B: running with retry_count=3 -> exceeds max_retries, marked failed
    job_b_id = f"test-stuck-b-{uuid.uuid4()}"
    job_store.create_job(job_b_id, {
        "title": "Stuck Job B", "aspect_ratio": "16:9", "resolution": "1080p",
        "duration_seconds": 3.0, "scenes_count": 1, "scenes": SAMPLE_SCENES
    })
    job_store.update_job(job_b_id, retry_count=3)
    job_store.transition_state(job_b_id, to_status="running")

    # Trigger recovery
    recovered_ids = job_store.recover_stuck_jobs()
    assert job_a_id in recovered_ids
    assert job_b_id in recovered_ids

    job_a = job_store.get_job(job_a_id)
    assert job_a["status"] == "queued"
    assert job_a["retry_count"] == 1
    assert "Recovered after server restart" in job_a["stage_message"]

    job_b = job_store.get_job(job_b_id)
    assert job_b["status"] == "failed"
    assert job_b["error"]["error_code"] == "PROCESS_CRASH_TERMINATION"


# ============================================================================
# 5. PUBLIC SANITIZATION (NO INTERNAL PATHS OR SENSITIVE STACK TRACES)
# ============================================================================

def test_public_responses_sanitize_filesystem_paths():
    job_id = f"test-sanitize-{uuid.uuid4()}"
    job_store.create_job(job_id, {
        "title": "Sanitization Check", "aspect_ratio": "16:9", "resolution": "1080p",
        "duration_seconds": 3.0, "scenes_count": 1, "scenes": SAMPLE_SCENES
    })
    # Simulate an error with internal drive paths
    raw_error_text = f"IOError: Could not open {settings.OUTPUT_DIR}\\raw_stream.mp4 at E:\\Incubrix\\core.py line 42"
    sanitized = background_worker._sanitize_error_text(raw_error_text)

    # Internal Windows paths must be masked
    assert "E:\\Incubrix" not in sanitized
    assert str(settings.OUTPUT_DIR) not in sanitized

    job_store.transition_state(
        job_id, to_status="failed", error_code="PROCESSING_ERROR", error_message=sanitized
    )
    res = client.get(f"/v1/jobs/{job_id}")
    assert res.status_code == 200
    res_data = res.json()
    assert "E:\\" not in json.dumps(res_data)
    assert "output_dir" not in res_data  # Public schema excludes internal output_dir


# ============================================================================
# 6. CONCURRENT JOB SUBMISSIONS
# ============================================================================

def test_concurrent_job_creation():
    job_ids = []
    prefix = uuid.uuid4().hex[:6]
    for i in range(5):
        res = client.post(
            "/v1/jobs",
            json={
                "title": f"Concurrent Job {i}",
                "aspect_ratio": "16:9",
                "scenes": SAMPLE_SCENES
            },
            headers={"Idempotency-Key": f"concurrent-key-{prefix}-{i}"}
        )
        assert res.status_code == 202
        job_ids.append(res.json()["job_id"])

    assert len(set(job_ids)) == 5
    for jid in job_ids:
        job = job_store.get_job(jid)
        assert job is not None
        assert job["status"] in ("queued", "running", "completed")
