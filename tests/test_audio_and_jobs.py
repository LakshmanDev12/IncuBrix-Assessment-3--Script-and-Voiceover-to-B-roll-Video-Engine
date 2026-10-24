import io
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.storage import job_store
from tests.fixtures import make_valid_wav_bytes

client = TestClient(app)

SAMPLE_SCENES = [
    {
        "narration": "First scene narration testing audio and job lifecycles.",
        "duration_seconds": 4.0,
        "visual_description": "A bustling creative studio with cameras and light panels."
    }
]


def test_ambiguous_audio_both_upload_and_url_rejected():
    """Explicitly verify rejection when BOTH audio upload and audio URL are provided."""
    dummy_audio = io.BytesIO(b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00")
    response = client.post(
        "/v1/jobs/multipart",
        data={
            "title": "Conflicting Audio Job",
            "aspect_ratio": "16:9",
            "scenes": json.dumps(SAMPLE_SCENES),
            "audio_url": "https://example.com/audio.mp3"
        },
        files={"audio_file": ("test.wav", dummy_audio, "audio/wav")}
    )
    assert response.status_code == 400
    detail = response.json().get("detail", {})
    assert detail.get("error_code") == "AMBIGUOUS_AUDIO_INPUT"
    assert "both 'audio_file' and 'audio_url'" in detail.get("message", "")


def test_valid_audio_upload_job():
    """Verify successful multipart job creation with uploaded audio."""
    valid_wav = io.BytesIO(make_valid_wav_bytes(duration_seconds=4.0))
    response = client.post(
        "/v1/jobs/multipart",
        data={
            "title": "Upload Audio Job",
            "aspect_ratio": "9:16",
            "resolution": "1080p",
            "scenes": json.dumps(SAMPLE_SCENES)
        },
        files={"audio_file": ("narration.wav", valid_wav, "audio/wav")}
    )
    assert response.status_code == 202
    data = response.json()
    assert data["audio_source"] == "upload"
    assert data["aspect_ratio"] == "9:16"
    assert data["status"] == "queued"
    assert data["audio_details"]["codec"] == "pcm_s16le"
    assert data["audio_details"]["duration_seconds"] == 4.0


def test_unsupported_audio_extension_rejected():
    """Verify rejection of non-audio files (e.g. .exe, .sh, .txt)."""
    fake_exe = io.BytesIO(b"MZ\x90\x00\x03\x00\x00\x00")
    response = client.post(
        "/v1/jobs/multipart",
        data={
            "title": "Bad File Job",
            "scenes": json.dumps(SAMPLE_SCENES)
        },
        files={"audio_file": ("malicious.exe", fake_exe, "application/octet-stream")}
    )
    assert response.status_code == 415
    detail = response.json().get("detail", {})
    assert detail.get("error_code") == "UNSUPPORTED_AUDIO_FORMAT"


def test_job_cancellation_lifecycle():
    # 1. Create a queued job
    res = client.post("/v1/jobs", json={
        "title": "Cancellable Job",
        "aspect_ratio": "1:1",
        "scenes": SAMPLE_SCENES
    })
    assert res.status_code == 202
    job_id = res.json()["job_id"]

    # 2. Cancel the job
    cancel_res = client.post(f"/v1/jobs/{job_id}/cancel")
    assert cancel_res.status_code == 200
    cancel_data = cancel_res.json()
    assert cancel_data["job_id"] == job_id
    assert cancel_data["status"] == "cancelled"

    # 3. Status now reflects cancellation
    status_res = client.get(f"/v1/jobs/{job_id}")
    assert status_res.status_code == 200
    assert status_res.json()["status"] == "cancelled"

    # 4. Cancel again (idempotent)
    cancel_again = client.post(f"/v1/jobs/{job_id}/cancel")
    assert cancel_again.status_code == 200
    assert cancel_again.json()["status"] == "cancelled"


def test_cancel_non_existent_job_is_404():
    res = client.post("/v1/jobs/00000000-0000-0000-0000-000000000000/cancel")
    assert res.status_code == 404


def test_cancel_terminal_completed_job_is_409():
    res = client.post("/v1/jobs", json={
        "title": "Completed Job",
        "aspect_ratio": "16:9",
        "scenes": SAMPLE_SCENES
    })
    job_id = res.json()["job_id"]

    # Mark as completed in store
    job_store.update_job(job_id, status="completed", progress=100.0)

    cancel_res = client.post(f"/v1/jobs/{job_id}/cancel")
    assert cancel_res.status_code == 409
    assert "Cannot cancel job in terminal state" in str(cancel_res.json())


def test_artifacts_in_progress_job_is_409():
    res = client.post("/v1/jobs", json={
        "title": "Queued Artifacts Check",
        "aspect_ratio": "16:9",
        "scenes": SAMPLE_SCENES
    })
    job_id = res.json()["job_id"]

    # Artifacts request should be 409 conflict while queued
    art_res = client.get(f"/v1/jobs/{job_id}/artifacts")
    assert art_res.status_code == 409
    assert art_res.json()["detail"]["error_code"] == "JOB_NOT_COMPLETED"


def test_artifacts_completed_job_lists_and_downloads():
    res = client.post("/v1/jobs", json={
        "title": "Artifact Delivery Job",
        "aspect_ratio": "16:9",
        "scenes": SAMPLE_SCENES
    })
    job_id = res.json()["job_id"]
    job_folder = settings.OUTPUT_DIR / job_id
    job_folder.mkdir(parents=True, exist_ok=True)

    # Place sample test artifacts
    (job_folder / "manifest.json").write_text('{"title": "Artifact Delivery Job"}', encoding="utf-8")
    (job_folder / "timeline.json").write_text('[{"scene_index": 1}]', encoding="utf-8")
    (job_folder / "captions.srt").write_text("1\n00:00:00,000 --> 00:00:04,000\nHello", encoding="utf-8")

    # Mark completed
    job_store.update_job(job_id, status="completed", progress=100.0)

    # 1. List artifacts
    art_res = client.get(f"/v1/jobs/{job_id}/artifacts")
    assert art_res.status_code == 200
    artifacts_data = art_res.json()["artifacts"]
    artifact_names = [a["name"] for a in artifacts_data]
    assert "manifest.json" in artifact_names
    assert "timeline.json" in artifact_names
    assert "captions.srt" in artifact_names
    assert "job_state.json" not in artifact_names  # Internal state must not be leaked as public artifact

    # 2. Download an artifact
    dl_res = client.get(f"/v1/jobs/{job_id}/artifacts/manifest.json")
    assert dl_res.status_code == 200
    assert "Artifact Delivery Job" in dl_res.text
