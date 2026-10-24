import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings

client = TestClient(app)

SAMPLE_VALID_SCENE = {
    "narration": "IncuBrix streamlines creator workflows through automated visual curation.",
    "duration_seconds": 5.0,
    "visual_description": "A creator editing video on a dual-monitor workstation with smooth timeline transitions.",
    "source_url": "https://example.com/footage.mp4",
    "license_name": "Creative Commons Zero",
    "attribution": "Public Domain Archive"
}


def test_valid_job_creation():
    payload = {
        "title": "Launch Teaser",
        "aspect_ratio": "16:9",
        "resolution": "1080p",
        "scenes": [SAMPLE_VALID_SCENE]
    }
    response = client.post("/v1/jobs", json=payload)
    assert response.status_code == 202
    data = response.json()
    assert "job_id" in data
    assert data["status"] == "queued"
    assert data["progress"] == 0.0
    assert data["current_stage"] == "queued"
    assert data["aspect_ratio"] == "16:9"
    assert data["resolution"] == "1080p"
    assert data["duration_seconds"] == 5.0
    assert data["scenes_count"] == 1
    assert data["audio_source"] == "none"
    assert data["links"]["self"] == f"/v1/jobs/{data['job_id']}"


@pytest.mark.parametrize("aspect_ratio", ["16:9", "9:16", "1:1"])
def test_valid_aspect_ratios(aspect_ratio):
    payload = {
        "title": f"Aspect Ratio {aspect_ratio}",
        "aspect_ratio": aspect_ratio,
        "scenes": [SAMPLE_VALID_SCENE]
    }
    response = client.post("/v1/jobs", json=payload)
    assert response.status_code == 202
    assert response.json()["aspect_ratio"] == aspect_ratio


def test_invalid_aspect_ratio_rejected():
    payload = {
        "title": "Bad Ratio",
        "aspect_ratio": "4:3",
        "scenes": [SAMPLE_VALID_SCENE]
    }
    response = client.post("/v1/jobs", json=payload)
    assert response.status_code == 422
    data = response.json()
    assert data["error_code"] == "VALIDATION_ERROR"


def test_invalid_resolution_rejected():
    payload = {
        "title": "Bad Resolution",
        "aspect_ratio": "16:9",
        "resolution": "4k",
        "scenes": [SAMPLE_VALID_SCENE]
    }
    response = client.post("/v1/jobs", json=payload)
    assert response.status_code == 422


def test_missing_title_handled_with_default():
    # Title has a default of 'Demo video'
    payload = {
        "aspect_ratio": "16:9",
        "scenes": [SAMPLE_VALID_SCENE]
    }
    response = client.post("/v1/jobs", json=payload)
    assert response.status_code == 202
    assert response.json()["title"] == "Demo video"


def test_empty_or_whitespace_title_rejected():
    payload = {
        "title": "    ",
        "aspect_ratio": "16:9",
        "scenes": [SAMPLE_VALID_SCENE]
    }
    response = client.post("/v1/jobs", json=payload)
    assert response.status_code == 422


def test_title_too_long_rejected():
    payload = {
        "title": "X" * (settings.MAX_TITLE_LENGTH + 1),
        "aspect_ratio": "16:9",
        "scenes": [SAMPLE_VALID_SCENE]
    }
    response = client.post("/v1/jobs", json=payload)
    assert response.status_code == 422


def test_zero_scenes_rejected():
    payload = {
        "title": "No scenes",
        "scenes": []
    }
    response = client.post("/v1/jobs", json=payload)
    assert response.status_code == 422


def test_too_many_scenes_rejected():
    many_scenes = [
        {
            "narration": f"Scene number {i}",
            "duration_seconds": 1.0,
            "visual_description": "Visual scene"
        }
        for i in range(settings.MAX_SCENES + 1)
    ]
    payload = {
        "title": "Overloaded Scenes",
        "scenes": many_scenes
    }
    response = client.post("/v1/jobs", json=payload)
    assert response.status_code == 422


def test_scene_duration_too_short():
    short_scene = dict(SAMPLE_VALID_SCENE, duration_seconds=0.1)  # min is 0.5s
    payload = {
        "title": "Too short scene",
        "scenes": [short_scene]
    }
    response = client.post("/v1/jobs", json=payload)
    assert response.status_code == 422


def test_scene_duration_too_long():
    long_scene = dict(SAMPLE_VALID_SCENE, duration_seconds=75.0)  # max is 60.0s
    payload = {
        "title": "Too long scene",
        "scenes": [long_scene]
    }
    response = client.post("/v1/jobs", json=payload)
    assert response.status_code == 422


def test_total_job_duration_exceeded():
    # 6 scenes of 55s = 330s > 300s max
    scenes = [
        dict(SAMPLE_VALID_SCENE, duration_seconds=55.0) for _ in range(6)
    ]
    payload = {
        "title": "Oversized Job Duration",
        "scenes": scenes
    }
    response = client.post("/v1/jobs", json=payload)
    assert response.status_code == 422
    assert "exceeds maximum allowed" in str(response.json())


def test_get_limits_endpoint():
    response = client.get("/v1/limits")
    assert response.status_code == 200
    data = response.json()
    assert data["min_title_length"] == 1
    assert data["max_title_length"] == 120
    assert data["min_scenes"] == 1
    assert data["max_scenes"] == 30
    assert "16:9" in data["allowed_aspect_ratios"]
    assert "1080p" in data["allowed_resolutions"]
    assert ".wav" in data["allowed_audio_extensions"]
