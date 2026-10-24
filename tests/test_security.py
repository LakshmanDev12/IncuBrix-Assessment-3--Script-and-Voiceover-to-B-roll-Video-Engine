import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.security import (
    validate_url_security,
    validate_url_syntax,
    validate_safe_filename,
    SecurityValidationError
)
from app.config import settings

client = TestClient(app)

SAMPLE_SCENE = {
    "narration": "Security validation test scene.",
    "duration_seconds": 3.0,
    "visual_description": "Server rack with blinking LEDs representing secure infrastructure."
}


@pytest.mark.parametrize("bad_scheme", [
    "file:///etc/passwd",
    "file:///C:/Windows/System32/drivers/etc/hosts",
    "ftp://example.com/audio.wav",
    "gopher://evil.com/1",
    "data:audio/wav;base64,UklGRi...",
    "javascript:alert(1)"
])
def test_forbidden_schemes(bad_scheme):
    payload = {
        "title": "Bad Scheme Test",
        "aspect_ratio": "16:9",
        "scenes": [SAMPLE_SCENE],
        "audio_url": bad_scheme
    }
    response = client.post("/v1/jobs", json=payload)
    assert response.status_code in (400, 422)
    assert "FORBIDDEN_SCHEME" in str(response.json()) or "INVALID_URL" in str(response.json()) or "VALIDATION_ERROR" in str(response.json())


@pytest.mark.parametrize("ssrf_host", [
    "http://localhost/audio.mp3",
    "http://127.0.0.1/audio.mp3",
    "http://127.0.0.5:8080/audio.mp3",
    "http://[::1]/audio.mp3",
    "http://10.0.0.1/audio.mp3",
    "http://192.168.1.1/audio.mp3",
    "http://172.16.0.1/audio.mp3",
    "http://169.254.169.254/latest/meta-data/",
    "http://metadata.google.internal/computeMetadata/v1/"
])
def test_ssrf_forbidden_destinations(ssrf_host):
    payload = {
        "title": "SSRF Block Test",
        "aspect_ratio": "16:9",
        "scenes": [SAMPLE_SCENE],
        "audio_url": ssrf_host
    }
    response = client.post("/v1/jobs", json=payload)
    assert response.status_code in (400, 422)


def test_embedded_credentials_prohibited():
    with pytest.raises(SecurityValidationError) as exc_info:
        validate_url_syntax("http://admin:secret@public-server.com/audio.mp3")
    assert "Embedded credentials" in str(exc_info.value)


@pytest.mark.parametrize("malicious_filename", [
    "../../etc/passwd",
    "..\\..\\Windows\\win.ini",
    "/etc/shadow",
    "C:\\secret.txt",
    "subdir/../../target.txt"
])
def test_path_traversal_detection(malicious_filename):
    with pytest.raises(SecurityValidationError) as exc_info:
        validate_safe_filename(settings.OUTPUT_DIR, malicious_filename)
    assert "traversal" in str(exc_info.value).lower() or "escapes" in str(exc_info.value).lower()


def test_download_artifact_path_traversal():
    # Submit valid job
    res = client.post("/v1/jobs", json={
        "title": "Path Traversal Job",
        "aspect_ratio": "16:9",
        "scenes": [SAMPLE_SCENE]
    })
    job_id = res.json()["job_id"]

    # Try downloading with directory traversal
    bad_url = f"/v1/jobs/{job_id}/artifacts/..%2f..%2fapp%2fmain.py"
    get_res = client.get(bad_url)
    assert get_res.status_code in (400, 404, 409)
