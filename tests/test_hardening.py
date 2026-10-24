import asyncio
import logging
from pathlib import Path
import shutil
import sys
from unittest.mock import MagicMock, patch
import uuid

from fastapi import status
from fastapi.testclient import TestClient
import pytest

from app.config import settings
from app.main import (
    SecretMaskingFilter,
    app,
    correlation_id_ctx
)
from app.security import (
    SecurityValidationError,
    validate_safe_filename
)
from app.services.video_composer import VideoRenderingError, video_composer
from app.storage import job_store


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


# ==============================================================================
# 1. Path Traversal & Windows Device Name Hardening Tests
# ==============================================================================

def test_windows_reserved_device_names_rejected(tmp_path):
    """Verifies that DOS/Windows reserved device names are blocked."""
    reserved = ["CON", "PRN", "AUX", "NUL", "COM1", "COM9", "LPT1", "LPT9", "con.txt", "NUL.mp4", "aux.json"]
    for dev_name in reserved:
        with pytest.raises(SecurityValidationError) as exc_info:
            validate_safe_filename(tmp_path, dev_name)
        assert exc_info.value.code == "FORBIDDEN_FILE_ACCESS"


def test_alternate_data_streams_rejected(tmp_path):
    """Verifies that NTFS Alternate Data Stream (ADS) colon syntax is rejected."""
    ads_names = ["video.mp4:hidden_stream", "file.txt:$DATA", "payload.bin:stream"]
    for ads in ads_names:
        with pytest.raises(SecurityValidationError) as exc_info:
            validate_safe_filename(tmp_path, ads)
        assert exc_info.value.code == "FORBIDDEN_FILE_ACCESS"


def test_hidden_dotfiles_rejected(tmp_path):
    """Verifies that hidden dotfiles are blocked from external access."""
    dotfiles = [".env", ".git", ".htaccess", ".secrets.json", ".hidden"]
    for df in dotfiles:
        with pytest.raises(SecurityValidationError) as exc_info:
            validate_safe_filename(tmp_path, df)
        assert exc_info.value.code == "FORBIDDEN_FILE_ACCESS"


def test_internal_state_files_blacklisted(tmp_path):
    """Verifies that internal database and state files are explicitly forbidden."""
    internal_files = ["jobs.db", "jobs.db-wal", "jobs.db-shm", "job_state.json", "web.config", "main.py"]
    for internal in internal_files:
        with pytest.raises(SecurityValidationError) as exc_info:
            validate_safe_filename(tmp_path, internal)
        assert exc_info.value.code == "FORBIDDEN_FILE_ACCESS"


def test_standard_directory_traversal_rejected(tmp_path):
    """Verifies that directory traversal sequences are blocked."""
    traversal_names = ["../etc/passwd", "..\\boot.ini", "subdir/../../secrets", "....//escape"]
    for trav in traversal_names:
        with pytest.raises(SecurityValidationError) as exc_info:
            validate_safe_filename(tmp_path, trav)
        assert exc_info.value.code == "PATH_TRAVERSAL_ATTEMPT"


# ==============================================================================
# 2. Public Artifact Access Hardening (HTTP 403 / 400 Enforcement)
# ==============================================================================

def test_download_artifact_forbids_internal_and_device_files(client, tmp_path):
    """Ensures forbidden files return HTTP 403 rather than leaking contents."""
    job_id = f"test-harden-{uuid.uuid4().hex[:8]}"
    job_folder = settings.OUTPUT_DIR / job_id
    job_folder.mkdir(parents=True, exist_ok=True)

    # Seed job in completed state (queued -> running -> completed)
    job_store.create_job(job_id, {
        "title": "Completed Hardening Test",
        "aspect_ratio": "16:9",
        "resolution": "1080p",
        "duration_seconds": 5.0,
        "scenes_count": 1,
        "scenes": [{"narration": "Test scene", "duration_seconds": 5.0, "visual_description": "Office"}]
    })
    job_store.transition_state(job_id, to_status="running")
    job_store.transition_state(job_id, to_status="completed")

    # 1. Attempt downloading internal database
    res = client.get(f"/v1/jobs/{job_id}/artifacts/jobs.db")
    assert res.status_code == status.HTTP_403_FORBIDDEN
    assert "FORBIDDEN_FILE_ACCESS" in str(res.json())

    # 2. Attempt downloading Windows device name
    res = client.get(f"/v1/jobs/{job_id}/artifacts/CON")
    assert res.status_code == status.HTTP_403_FORBIDDEN
    assert "FORBIDDEN_FILE_ACCESS" in str(res.json())

    # 3. Attempt downloading hidden file
    res = client.get(f"/v1/jobs/{job_id}/artifacts/.env")
    assert res.status_code == status.HTTP_403_FORBIDDEN
    assert "FORBIDDEN_FILE_ACCESS" in str(res.json())

    # Cleanup
    shutil.rmtree(job_folder, ignore_errors=True)


def test_artifact_listing_filters_internal_and_hidden_files(client):
    """Ensures that internal DB/state files located in job directory are omitted from artifact manifests."""
    job_id = f"test-filter-{uuid.uuid4().hex[:8]}"
    job_folder = settings.OUTPUT_DIR / job_id
    job_folder.mkdir(parents=True, exist_ok=True)

    # Place allowed artifact alongside internal files
    (job_folder / "video.mp4").write_bytes(b"dummy_mp4_bytes")
    (job_folder / "jobs.db").write_bytes(b"sqlite_data")
    (job_folder / "job_state.json").write_bytes(b"{\"state\": true}")
    (job_folder / ".secret_key").write_bytes(b"secret")

    job_store.create_job(job_id, {
        "title": "Listing Filter Test",
        "aspect_ratio": "16:9",
        "resolution": "1080p",
        "duration_seconds": 3.0,
        "scenes_count": 1,
        "scenes": [{"narration": "Test", "duration_seconds": 3.0, "visual_description": "Desk"}]
    })
    job_store.transition_state(job_id, to_status="running")
    job_store.transition_state(job_id, to_status="completed")

    res = client.get(f"/v1/jobs/{job_id}/artifacts")
    assert res.status_code == status.HTTP_200_OK
    data = res.json()
    artifact_names = [a["name"] for a in data["artifacts"]]

    assert "video.mp4" in artifact_names
    assert "jobs.db" not in artifact_names
    assert "job_state.json" not in artifact_names
    assert ".secret_key" not in artifact_names

    shutil.rmtree(job_folder, ignore_errors=True)


# ==============================================================================
# 3. Correlation ID & Secret Masking Tests
# ==============================================================================

def test_correlation_id_propagation_and_generation(client):
    """Verifies that incoming X-Correlation-ID is preserved and generated when absent."""
    # Custom correlation ID
    custom_cid = "client-trace-abc-123"
    res1 = client.get("/health", headers={"X-Correlation-ID": custom_cid})
    assert res1.status_code == status.HTTP_200_OK
    assert res1.headers.get("X-Correlation-ID") == custom_cid

    # Auto-generated correlation ID
    res2 = client.get("/health")
    assert res2.status_code == status.HTTP_200_OK
    generated_cid = res2.headers.get("X-Correlation-ID")
    assert generated_cid is not None
    assert len(generated_cid) >= 16


def test_secret_masking_filter():
    """Verifies that secrets in log records are securely masked."""
    flt = SecretMaskingFilter()

    # Bearer token
    rec1 = logging.LogRecord("test", logging.INFO, "path", 1, "Sending auth header: Bearer abc123xyz_token_secret", (), None)
    flt.filter(rec1)
    assert "[MASKED]" in rec1.msg
    assert "abc123xyz" not in rec1.msg

    # Query param API key
    rec2 = logging.LogRecord("test", logging.INFO, "path", 1, "Requesting https://api.pexels.com/v1/search?api_key=secret_key_value&page=1", (), None)
    flt.filter(rec2)
    assert "api_key=[MASKED]" in rec2.msg

    # Env key pattern
    rec3 = logging.LogRecord("test", logging.INFO, "path", 1, "Configured PEXELS_API_KEY = live_production_secret_key", (), None)
    flt.filter(rec3)
    assert "PEXELS_API_KEY = [MASKED]" in rec3.msg


def test_unhandled_exception_sanitization():
    """Ensures unhandled runtime errors return clean JSON without exposing Python stack traces or host paths."""
    unhandled_client = TestClient(app, raise_server_exceptions=False)
    with patch("app.storage.job_store.get_job", side_effect=RuntimeError("Internal system breakdown at C:\\Windows\\System32\\app.py")):
        res = unhandled_client.get("/v1/jobs/non-existent-uuid")
        assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        data = res.json()
        assert data["error_code"] == "INTERNAL_SERVER_ERROR"
        # Host path and Python traceback must NOT be present
        assert "C:\\Windows" not in str(data)
        assert "Traceback" not in str(data)
        assert "RuntimeError" not in str(data)
        assert res.headers.get("X-Correlation-ID") is not None


# ==============================================================================
# 4. Liveness & Readiness Probes Tests
# ==============================================================================

def test_health_live_endpoint(client):
    """Verifies the fast /health/live probe returns alive status."""
    res = client.get("/health/live")
    assert res.status_code == status.HTTP_200_OK
    data = res.json()
    assert data["status"] == "alive"
    assert data["service"] == "video-broll-engine"


def test_health_ready_endpoint_success(client):
    """Verifies that /health/ready passes when all components are operational."""
    res = client.get("/health/ready")
    assert res.status_code == status.HTTP_200_OK
    data = res.json()
    assert data["status"] == "ready"
    assert data["checks"]["database"]["status"] == "ok"
    assert data["checks"]["storage"]["writable"] is True
    assert data["checks"]["storage"]["status"] == "ok"
    assert data["checks"]["worker"]["status"] == "ok"


def test_health_ready_endpoint_storage_exhaustion_simulation(client):
    """Simulates insufficient disk space and verifies /health/ready returns HTTP 503."""
    # Mock disk_usage to return 100 bytes free (< 500MB threshold)
    mock_usage = MagicMock()
    mock_usage.free = 100
    mock_usage.total = 1000000000

    with patch("shutil.disk_usage", return_value=mock_usage):
        res = client.get("/health/ready")
        assert res.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        data = res.json()
        assert data["status"] == "not_ready"
        assert data["checks"]["storage"]["status"] == "failed"
        assert data["checks"]["storage"]["free_bytes"] == 100


# ==============================================================================
# 5. FFmpeg Subprocess Governance & Timeout Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_subprocess_timeout_governance_kills_process():
    """Verifies that _run_subprocess_safe terminates and reaps subprocesses exceeding timeout limit."""
    # Use python executable running an indefinite sleep loop to simulate a hung FFmpeg process
    hang_cmd = [sys.executable, "-c", "import time; time.sleep(10)"]

    with pytest.raises(VideoRenderingError) as exc_info:
        await video_composer._run_subprocess_safe(
            cmd=hang_cmd,
            timeout_seconds=0.2,  # Very short timeout
            error_code="FFMPEG_TIMEOUT_TEST"
        )

    assert exc_info.value.code == "FFMPEG_TIMEOUT"
    assert "exceeded timeout limit" in exc_info.value.message


# ==============================================================================
# 6. Crash Recovery & Corrupt Artifact Purge Tests
# ==============================================================================

def test_crash_recovery_purges_partial_artifacts():
    """Verifies that recover_stuck_jobs deletes interrupted video.mp4 and temp files before re-queuing."""
    job_id = f"crash-test-{uuid.uuid4().hex[:8]}"
    job_dir = settings.OUTPUT_DIR / job_id
    temp_dir = job_dir / "temp"
    temp_dir.mkdir(parents=True, exist_ok=True)

    # Create partial video.mp4 and partial scene
    partial_video = job_dir / "video.mp4"
    partial_video.write_bytes(b"corrupt_partial_mp4_header")
    partial_scene = temp_dir / "scene_000.mp4"
    partial_scene.write_bytes(b"scene_chunk")

    # Insert job into database directly in 'running' state
    job_store.create_job(job_id, {
        "title": "Crash Recovery Purge Test",
        "aspect_ratio": "16:9",
        "resolution": "1080p",
        "duration_seconds": 4.0,
        "scenes_count": 1,
        "scenes": [{"narration": "Recovering", "duration_seconds": 4.0, "visual_description": "Data center"}]
    })
    job_store.transition_state(job_id, to_status="running")

    # Run crash recovery
    recovered = job_store.recover_stuck_jobs()
    assert job_id in recovered

    # Verify corrupt video.mp4 and temp directory are deleted
    assert not partial_video.exists(), "Partial video.mp4 was not purged on crash recovery!"
    assert not temp_dir.exists(), "Partial temp/ directory was not purged on crash recovery!"

    # Verify job status was reset to 'queued'
    rec = job_store.get_job(job_id)
    assert rec["status"] == "queued"
    assert rec["retry_count"] == 1

    shutil.rmtree(job_dir, ignore_errors=True)
