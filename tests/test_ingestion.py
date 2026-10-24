import io
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.services.audio_inspector import (
    AudioInspectionError,
    inspect_audio_file
)
from app.services.ingestion import IngestionError, ingestion_service
from tests.fixtures import (
    make_corrupted_audio_bytes,
    make_executable_disguised_as_audio,
    make_html_disguised_as_audio,
    make_valid_mp3_bytes,
    make_valid_wav_bytes
)

client = TestClient(app)

SAMPLE_SCENES = [
    {
        "narration": "First scene narration.",
        "duration_seconds": 4.0,
        "visual_description": "A creator looking at audio levels in an audio editing tool."
    }
]


# ============================================================================
# 1. AUDIO INSPECTOR TESTS (FORMATS, CODECS, CORRUPTED FILES, SECURITY BLOCKS)
# ============================================================================

def test_inspect_valid_wav(tmp_path: Path):
    wav_file = tmp_path / "test.wav"
    wav_file.write_bytes(make_valid_wav_bytes(duration_seconds=3.5, sample_rate=44100, channels=2))
    result = inspect_audio_file(wav_file)
    assert result.codec in ("pcm_s16le", "pcm_s16")
    assert result.format_name == "wav"
    assert result.duration_seconds == 3.5
    assert result.sample_rate == 44100
    assert result.channels == 2


def test_inspect_valid_mp3(tmp_path: Path):
    mp3_file = tmp_path / "test.mp3"
    mp3_file.write_bytes(make_valid_mp3_bytes(duration_seconds=3.0))
    result = inspect_audio_file(mp3_file)
    assert result.codec == "mp3"
    assert result.format_name == "mp3"
    assert result.duration_seconds >= 2.8
    assert result.sample_rate == 44100


def test_inspect_corrupted_audio_rejected(tmp_path: Path):
    corrupt_file = tmp_path / "corrupt.wav"
    corrupt_file.write_bytes(make_corrupted_audio_bytes())
    with pytest.raises(AudioInspectionError) as exc_info:
        inspect_audio_file(corrupt_file)
    assert exc_info.value.code in ("CORRUPTED_AUDIO_FILE", "TRUNCATED_AUDIO_FILE")


def test_executable_disguised_as_audio_rejected(tmp_path: Path):
    exe_file = tmp_path / "malicious.wav"
    exe_file.write_bytes(make_executable_disguised_as_audio())
    with pytest.raises(AudioInspectionError) as exc_info:
        inspect_audio_file(exe_file)
    assert exc_info.value.code == "SECURITY_VIOLATION"
    assert "Executable binary" in exc_info.value.message


def test_html_disguised_as_audio_rejected(tmp_path: Path):
    html_file = tmp_path / "fake.wav"
    html_file.write_bytes(make_html_disguised_as_audio())
    with pytest.raises(AudioInspectionError) as exc_info:
        inspect_audio_file(html_file)
    assert exc_info.value.code == "UNSUPPORTED_MEDIA_TYPE"


def test_empty_audio_file_rejected(tmp_path: Path):
    empty_file = tmp_path / "empty.wav"
    empty_file.write_bytes(b"")
    with pytest.raises(AudioInspectionError) as exc_info:
        inspect_audio_file(empty_file)
    assert exc_info.value.code == "EMPTY_FILE"


# ============================================================================
# 2. SCENE & SCRIPT VALIDATION (EMPTY SCRIPTS, DURATION MISMATCHES, REBALANCE)
# ============================================================================

def test_empty_script_rejected():
    payload = {
        "title": "Empty Script Job",
        "aspect_ratio": "16:9",
        "scenes": SAMPLE_SCENES,
        "script": "     \n   "
    }
    response = client.post("/v1/jobs", json=payload)
    assert response.status_code == 422
    assert "Script text cannot be empty" in str(response.json())


def test_mismatched_scene_durations_rejected():
    """Audio is 4.0s, but scenes sum to 12.0s (difference 8s > 2s tolerance)."""
    valid_wav = io.BytesIO(make_valid_wav_bytes(duration_seconds=4.0))
    scenes = [
        {"narration": "Scene 1", "duration_seconds": 6.0, "visual_description": "Desc 1"},
        {"narration": "Scene 2", "duration_seconds": 6.0, "visual_description": "Desc 2"}
    ]
    response = client.post(
        "/v1/jobs/multipart",
        data={
            "title": "Mismatched Audio Duration",
            "scenes": json.dumps(scenes),
            "auto_rebalance_scenes": "false"
        },
        files={"audio_file": ("voice.wav", valid_wav, "audio/wav")}
    )
    assert response.status_code == 422
    data = response.json()
    assert data["detail"]["error_code"] == "DURATION_MISMATCH"
    assert "Difference of 8.00s exceeds tolerance" in data["detail"]["message"]


def test_auto_rebalance_scene_durations_success():
    """Audio is 4.0s and scenes sum to 8.0s; auto_rebalance rescales scenes to 4.0s total."""
    valid_wav = io.BytesIO(make_valid_wav_bytes(duration_seconds=4.0))
    scenes = [
        {"narration": "Scene 1", "duration_seconds": 4.0, "visual_description": "Desc 1"},
        {"narration": "Scene 2", "duration_seconds": 4.0, "visual_description": "Desc 2"}
    ]
    response = client.post(
        "/v1/jobs/multipart",
        data={
            "title": "Rebalanced Audio Duration",
            "scenes": json.dumps(scenes),
            "auto_rebalance_scenes": "true"
        },
        files={"audio_file": ("voice.wav", valid_wav, "audio/wav")}
    )
    assert response.status_code == 202
    data = response.json()
    assert data["duration_seconds"] == 4.0
    assert data["auto_rebalance_scenes"] is True


# ============================================================================
# 3. WORKSPACE DIRECTORY ISOLATION & PATH TRAVERSAL SANITIZATION
# ============================================================================

def test_controlled_directory_and_filename_generation():
    """User uploads audio with malicious filename; engine generates secure path."""
    valid_wav = io.BytesIO(make_valid_wav_bytes(duration_seconds=4.0))
    malicious_user_filename = "../../evil_shell.wav"

    response = client.post(
        "/v1/jobs/multipart",
        data={
            "title": "Path Traversal Audio Upload",
            "scenes": json.dumps(SAMPLE_SCENES)
        },
        files={"audio_file": (malicious_user_filename, valid_wav, "audio/wav")}
    )
    assert response.status_code == 202
    job_id = response.json()["job_id"]

    # Verify directory layout
    job_dir = settings.OUTPUT_DIR / job_id
    assert job_dir.exists()
    assert (job_dir / "audio").exists()
    assert (job_dir / "temp").exists()
    assert (job_dir / "artifacts").exists()

    # The stored voiceover must have a generated name inside the audio directory
    voiceover_file = job_dir / "audio" / "voiceover.wav"
    assert voiceover_file.exists()

    # Temporary files should be cleaned up
    temp_files = list((job_dir / "temp").iterdir())
    assert len(temp_files) == 0


def test_cleanup_after_upload_failure():
    """Corrupted audio upload must clean up temporary files and not leave orphaned artifacts."""
    corrupt_wav = io.BytesIO(make_corrupted_audio_bytes())
    response = client.post(
        "/v1/jobs/multipart",
        data={
            "title": "Corrupt Audio Upload",
            "scenes": json.dumps(SAMPLE_SCENES)
        },
        files={"audio_file": ("corrupt.wav", corrupt_wav, "audio/wav")}
    )
    assert response.status_code in (400, 422)


# ============================================================================
# 4. SAFE AUDIO URL DOWNLOAD PIPELINE
# ============================================================================

def test_safe_audio_url_download(monkeypatch):
    """Mocks a secure remote HTTP server serving valid WAV bytes and verifies download pipeline."""
    sample_wav_bytes = make_valid_wav_bytes(duration_seconds=4.0)

    class MockResponse:
        status_code = 200
        is_redirect = False
        headers = {"Content-Length": str(len(sample_wav_bytes)), "Content-Type": "audio/wav"}

        def iter_bytes(self, chunk_size=65536):
            yield sample_wav_bytes

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    import httpx
    monkeypatch.setattr(httpx.Client, "stream", lambda self, method, url, **kwargs: MockResponse())

    # Mock validate_url_security in both schemas and audio_downloader to allow offline mock URL
    import app.schemas
    import app.security
    import app.services.audio_downloader
    monkeypatch.setattr(app.schemas, "validate_url_security", lambda u: u)
    monkeypatch.setattr(app.security, "validate_url_security", lambda u: u)
    monkeypatch.setattr(app.services.audio_downloader, "validate_url_security", lambda u: u)

    response = client.post("/v1/jobs", json={
        "title": "URL Audio Download Job",
        "aspect_ratio": "16:9",
        "scenes": SAMPLE_SCENES,
        "audio_url": "https://example.com/assets/voiceover.wav"
    })
    assert response.status_code == 202
    data = response.json()
    assert data["audio_source"] == "url"
    assert data["audio_details"]["duration_seconds"] == 4.0
    assert data["audio_details"]["codec"] == "pcm_s16le"
