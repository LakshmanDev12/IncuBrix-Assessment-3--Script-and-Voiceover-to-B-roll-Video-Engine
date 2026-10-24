import struct
from pathlib import Path
from unittest.mock import MagicMock
import httpx
import pytest

from app.schemas import Scene
from app.services.media_selector import (
    MediaSelectionError,
    MediaSelector,
    media_selector,
)
from app.services.media_validator import (
    MediaValidationError,
    download_media_clip,
    validate_video_file,
)
from app.services.providers import (
    BaseMediaProvider,
    LicenseInfo,
    MediaCandidate,
    MediaProviderRegistry,
)


def create_synthetic_mp4_bytes(duration_sec: float = 5.0, width: int = 1920, height: int = 1080) -> bytes:
    """
    Constructs a deterministic minimal valid ISO-BMFF (MP4) container.
    Clearly designated as an internal test fixture asset.
    """
    def make_box(box_type: str, payload: bytes) -> bytes:
        return struct.pack(">I4s", len(payload) + 8, box_type.encode("latin1")) + payload

    timescale = 1000
    dur_ticks = int(duration_sec * timescale)

    ftyp = make_box("ftyp", b"isom\x00\x00\x02\x00isommp41mp42")
    mvhd = make_box(
        "mvhd",
        b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
        + struct.pack(">II", timescale, dur_ticks)
        + b"\x00\x01\x00\x00\x01\x00"
        + b"\x00" * 10
        + b"\x00\x01\x00\x00"
        + b"\x00" * 12
        + b"\x00\x01\x00\x00"
        + b"\x00" * 12
        + b"\x40\x00\x00\x00"
        + b"\x00" * 24
        + struct.pack(">I", 2)
    )
    tkhd = make_box(
        "tkhd",
        b"\x00\x00\x00\x07\x00\x00\x00\x00\x00\x00\x00\x00"
        + struct.pack(">I", 1)
        + b"\x00" * 4
        + struct.pack(">I", dur_ticks)
        + b"\x00" * 8
        + b"\x00" * 6
        + b"\x00\x01\x00\x00"
        + b"\x00" * 12
        + b"\x00\x01\x00\x00"
        + b"\x00" * 12
        + b"\x40\x00\x00\x00"
        + struct.pack(">II", width << 16, height << 16)
    )
    trak = make_box("trak", tkhd)
    moov = make_box("moov", mvhd + trak)
    mdat = make_box("mdat", b"\x00" * 64)
    return ftyp + moov + mdat


# --- Selection Tests ---

def test_media_selection_avoids_repeating_clips():
    # Two scenes with identical visual requirements
    scene1 = Scene(narration="First developer scene.", duration_seconds=5.0, visual_description="Software developer coding python on computer in office")
    scene2 = Scene(narration="Second developer scene.", duration_seconds=5.0, visual_description="Software developer coding python on computer in office")

    result = media_selector.select_media_for_scenes(
        job_id="job_dup_test",
        scenes=[scene1, scene2],
        allow_repeated_clips=False
    )

    assert len(result.selected_clips) == 2
    clip1 = result.selected_clips[0]
    clip2 = result.selected_clips[1]

    # Guarantees different clips were chosen to prevent duplication
    assert clip1.candidate.id != clip2.candidate.id
    assert result.duplicate_clips_prevented == 1
    assert clip1.selection_rank == 1
    assert clip2.selection_rank >= 2
    assert "prevent repeating" in clip2.selection_reason


def test_media_selection_allows_repeating_when_explicitly_set():
    scene1 = Scene(narration="First developer scene.", duration_seconds=5.0, visual_description="Software developer coding python on computer in office")
    scene2 = Scene(narration="Second developer scene.", duration_seconds=5.0, visual_description="Software developer coding python on computer in office")

    result = media_selector.select_media_for_scenes(
        job_id="job_allow_dup_test",
        scenes=[scene1, scene2],
        allow_repeated_clips=True
    )

    assert len(result.selected_clips) == 2
    # Both can select the highest-ranked candidate
    assert result.selected_clips[0].candidate.id == result.selected_clips[1].candidate.id
    assert result.duplicate_clips_prevented == 0


def test_media_selection_records_reasons_scores_and_provenance():
    scene = Scene(narration="Nature scene.", duration_seconds=8.0, visual_description="Cascading forest mountain waterfall and river stream")

    result = media_selector.select_media_for_scenes(
        job_id="job_provenance_test",
        scenes=[scene]
    )

    assert len(result.selected_clips) == 1
    selected = result.selected_clips[0]

    assert selected.relevance_score > 0.3
    assert len(selected.reasons) >= 1
    assert selected.selection_reason.startswith("Top-ranked")
    assert selected.score_breakdown["duration_fit"] == 1.0

    # Provenance assertions
    prov = selected.provenance
    assert prov["source_page_url"].startswith("http")
    assert prov["creator"] != ""
    assert prov["license_name"] in ("CC0-1.0", "CC0")
    assert prov["verification_status"] == "verified"
    assert prov["verified"] is True

    # Ledger audit
    ledger_data = result.attribution_ledger.to_dict()
    assert ledger_data["all_verified"] is True
    assert len(ledger_data["credits"]) == 1


def test_media_selection_low_relevance_warning():
    # Completely disjoint query
    scene = Scene(narration="Extraterrestrial landing.", duration_seconds=5.0, visual_description="Alien spacecraft hovering over active volcanic lava caldera")

    result = media_selector.select_media_for_scenes(
        job_id="job_low_rel_test",
        scenes=[scene],
        min_relevance_threshold=0.5
    )

    assert len(result.selected_clips) == 1
    selected = result.selected_clips[0]
    assert "Low relevance notice" in selected.selection_reason


def test_media_selection_handles_provider_failure_with_fallback():
    # Mock a failing remote provider in the registry
    mock_failing_provider = MagicMock(spec=BaseMediaProvider)
    mock_failing_provider.name = "failing_provider"
    mock_failing_provider.search.side_effect = RuntimeError("Remote API 500 internal error")

    registry = MediaProviderRegistry()
    registry.register(mock_failing_provider)

    selector = MediaSelector(registry=registry)
    scene = Scene(narration="Office team.", duration_seconds=5.0, visual_description="Corporate business team presentation meeting")

    # When querying failing_provider, should cleanly fall back to local_cc0
    result = selector.select_media_for_scenes(
        job_id="job_fallback_test",
        scenes=[scene],
        provider_name="failing_provider"
    )

    assert len(result.selected_clips) == 1
    assert result.selected_clips[0].candidate.provider == "local_cc0"


# --- Video Validation & Download Tests ---

def test_validate_video_file_valid_synthetic_mp4(tmp_path: Path):
    mp4_bytes = create_synthetic_mp4_bytes(duration_sec=6.5, width=1920, height=1080)
    test_file = tmp_path / "valid_test.mp4"
    test_file.write_bytes(mp4_bytes)

    res = validate_video_file(test_file)
    assert res.is_valid is True
    assert res.format_name == "mp4"
    assert res.width == 1920
    assert res.height == 1080
    assert res.duration_seconds == 6.5
    assert res.aspect_ratio == "16:9"
    assert res.fps == 30.0


def test_validate_video_file_rejects_corrupted_truncated(tmp_path: Path):
    # Only ftyp box without moov metadata
    truncated = struct.pack(">I4s", 16, b"ftyp") + b"isom\x00\x00\x02\x00"
    test_file = tmp_path / "corrupted_truncated.mp4"
    test_file.write_bytes(truncated)

    with pytest.raises(MediaValidationError) as exc:
        validate_video_file(test_file)
    assert exc.value.code == "CORRUPTED_MEDIA"
    assert "missing 'moov'" in exc.value.message or "truncated" in exc.value.message


def test_validate_video_file_rejects_disguised_executable(tmp_path: Path):
    fake_exe = b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xff\xff\x00\x00" + b"\x00" * 100
    test_file = tmp_path / "malicious.mp4"
    test_file.write_bytes(fake_exe)

    with pytest.raises(MediaValidationError) as exc:
        validate_video_file(test_file)
    assert exc.value.code == "SECURITY_VIOLATION"


def test_validate_video_file_rejects_disguised_html(tmp_path: Path):
    fake_html = b"<!DOCTYPE html><html><body>Error 404 Not Found</body></html>"
    test_file = tmp_path / "error_page.mp4"
    test_file.write_bytes(fake_html)

    with pytest.raises(MediaValidationError) as exc:
        validate_video_file(test_file)
    assert exc.value.code == "UNSUPPORTED_MEDIA_TYPE"


def test_validate_video_file_rejects_empty_file(tmp_path: Path):
    empty_file = tmp_path / "empty.mp4"
    empty_file.write_bytes(b"")

    with pytest.raises(MediaValidationError) as exc:
        validate_video_file(empty_file)
    assert exc.value.code == "EMPTY_FILE"


def test_download_media_clip_enforces_ssrf_protection(tmp_path: Path):
    dest = tmp_path / "dest.mp4"

    # Blocked SSRF loopback
    with pytest.raises(MediaValidationError) as exc1:
        download_media_clip("http://127.0.0.1/video.mp4", dest)
    assert "SSRF" in exc1.value.code or "PRIVATE" in exc1.value.code

    # Blocked cloud metadata
    with pytest.raises(MediaValidationError) as exc2:
        download_media_clip("http://169.254.169.254/latest/meta-data", dest)
    assert "SSRF" in exc2.value.code or "PRIVATE" in exc2.value.code


def test_download_media_clip_enforces_max_size_limit(tmp_path: Path, monkeypatch):
    dest = tmp_path / "oversized.mp4"

    # Mock response returning a stream of bytes larger than max_bytes
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"Content-Length": "2000"}
    mock_resp.iter_bytes.return_value = [b"A" * 500, b"B" * 500, b"C" * 500]

    mock_client = MagicMock()
    mock_client.__enter__.return_value.stream.return_value.__enter__.return_value = mock_resp
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: mock_client)

    with pytest.raises(MediaValidationError) as exc:
        # Limit to 600 bytes
        download_media_clip("https://example.com/huge_video.mp4", dest, max_bytes=600)
    assert exc.value.code == "FILE_TOO_LARGE"


def test_download_media_clip_handles_broken_urls(tmp_path: Path, monkeypatch):
    dest = tmp_path / "broken.mp4"

    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_client = MagicMock()
    mock_client.__enter__.return_value.stream.return_value.__enter__.return_value = mock_resp
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: mock_client)

    with pytest.raises(MediaValidationError) as exc:
        download_media_clip("https://example.com/non_existent.mp4", dest)
    assert exc.value.code == "DOWNLOAD_HTTP_ERROR"
    assert exc.value.details["status_code"] == 404
