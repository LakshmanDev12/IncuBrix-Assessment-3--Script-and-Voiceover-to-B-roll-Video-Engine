import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.schemas import Scene
from app.services.media_validator import validate_video_file
from app.services.subtitles import (
    format_srt_timestamp,
    format_vtt_timestamp,
    generate_subtitles,
    write_subtitle_files,
)
from app.services.timeline_manifest import (
    build_manifest,
    build_timeline,
    calculate_sha256,
    write_timeline_and_manifest,
)
from app.services.video_composer import (
    RenderingCancelledError,
    VideoComposer,
    VideoRenderingError,
    video_composer,
)
from app.services.worker import background_worker
from app.storage import job_store

client = TestClient(app)


# --- Subtitle Generation Tests ---

def test_timestamp_formatting():
    # 0 seconds
    assert format_srt_timestamp(0.0) == "00:00:00,000"
    assert format_vtt_timestamp(0.0) == "00:00:00.000"

    # 4.5 seconds
    assert format_srt_timestamp(4.5) == "00:00:04,500"
    assert format_vtt_timestamp(4.5) == "00:00:04.500"

    # 65.123 seconds -> 1 min 5 sec 123 ms
    assert format_srt_timestamp(65.123) == "00:01:05,123"
    assert format_vtt_timestamp(65.123) == "00:01:05.123"

    # 3661.045 seconds -> 1 hr 1 min 1 sec 45 ms
    assert format_srt_timestamp(3661.045) == "01:01:01,045"
    assert format_vtt_timestamp(3661.045) == "01:01:01.045"


def test_generate_subtitles_multi_scene():
    scenes = [
        {
            "narration": "Welcome to our comprehensive video demonstration.",
            "duration_seconds": 4.0,
            "visual_description": "Modern studio setup."
        },
        {
            "narration": "In this second scene, we explore artificial intelligence and automation.",
            "duration_seconds": 5.5,
            "visual_description": "Data center servers with glowing blue LEDs."
        }
    ]

    srt, vtt = generate_subtitles(scenes, max_line_chars=40)

    # Check SRT
    assert "1\n00:00:00,000 --> 00:00:04,000" in srt
    assert "Welcome to our comprehensive video" in srt
    assert "2\n00:00:04,000 --> 00:00:09,500" in srt
    assert "artificial intelligence" in srt

    # Check VTT
    assert vtt.startswith("WEBVTT\n")
    assert "1\n00:00:00.000 --> 00:00:04.000" in vtt
    assert "2\n00:00:04.000 --> 00:00:09.500" in vtt


def test_write_subtitle_files(tmp_path: Path):
    scenes = [
        {"narration": "File writing test scene.", "duration_seconds": 3.0}
    ]
    srt_p, vtt_p = write_subtitle_files(tmp_path, scenes, base_name="test_captions")
    assert srt_p.exists()
    assert vtt_p.exists()
    assert "File writing test scene." in srt_p.read_text(encoding="utf-8")
    assert "WEBVTT" in vtt_p.read_text(encoding="utf-8")


# --- Timeline & Manifest Tests ---

def test_build_timeline_structure():
    scenes = [
        {"narration": "Scene 1", "duration_seconds": 4.0, "visual_description": "City traffic"},
        {"narration": "Scene 2", "duration_seconds": 3.5, "visual_description": "Office workers"}
    ]
    selected_clips = [
        {
            "scene_index": 1,
            "candidate": {"id": "clip_city_01", "provider": "local_cc0", "title": "City Skyline"},
            "relevance_score": 0.88,
            "selection_rank": 1,
            "selection_reason": "Top rank",
            "provenance": {"source_page_url": "https://example.com/city", "license_name": "CC0-1.0"}
        }
    ]

    timeline = build_timeline(
        job_id="job_tl_test",
        title="Timeline Test Video",
        scenes=scenes,
        selected_clips=selected_clips,
        aspect_ratio="16:9",
        resolution="1080p",
        fps=30
    )

    assert timeline["job_id"] == "job_tl_test"
    assert timeline["total_duration_seconds"] == 7.5
    assert len(timeline["scenes"]) == 2

    # Scene 1 cuts & timing
    s1 = timeline["scenes"][0]
    assert s1["scene_index"] == 1
    assert s1["start_time_seconds"] == 0.0
    assert s1["end_time_seconds"] == 4.0
    assert s1["cut_points"]["in_point_seconds"] == 0.0
    assert s1["cut_points"]["out_point_seconds"] == 4.0
    assert s1["selected_clip"]["candidate_id"] == "clip_city_01"

    # Scene 2 timing
    s2 = timeline["scenes"][1]
    assert s2["scene_index"] == 2
    assert s2["start_time_seconds"] == 4.0
    assert s2["end_time_seconds"] == 7.5


def test_build_manifest_and_sha256(tmp_path: Path):
    # Create sample files
    test_file = tmp_path / "sample.txt"
    test_file.write_text("SHA256 test payload", encoding="utf-8")
    calc_hash = calculate_sha256(test_file)
    assert len(calc_hash) == 64

    manifest = build_manifest(
        job_id="job_mf_test",
        title="Manifest Test",
        status="completed",
        aspect_ratio="9:16",
        resolution="1080p",
        width=1080,
        height=1920,
        duration_seconds=7.5,
        fps=30,
        audio_source="none",
        audio_details=None,
        artifacts_dir=tmp_path,
        scenes_count=2,
        rendering_engine="offline_synthesizer"
    )

    assert manifest["job_id"] == "job_mf_test"
    assert manifest["video_specification"]["width"] == 1080
    assert manifest["video_specification"]["height"] == 1920
    assert manifest["video_specification"]["aspect_ratio"] == "9:16"
    assert manifest["video_specification"]["rendering_engine"] == "offline_synthesizer"
    assert any(a["name"] == "sample.txt" for a in manifest["artifacts"])


# --- Video Composer Tests ---

def test_video_composer_dimension_mappings():
    assert VideoComposer.get_dimensions("16:9", "1080p") == (1920, 1080)
    assert VideoComposer.get_dimensions("9:16", "1080p") == (1080, 1920)
    assert VideoComposer.get_dimensions("1:1", "1080p") == (1080, 1080)
    assert VideoComposer.get_dimensions("16:9", "720p") == (1280, 720)
    assert VideoComposer.get_dimensions("9:16", "720p") == (720, 1280)
    assert VideoComposer.get_dimensions("1:1", "720p") == (720, 720)


def test_video_composer_fallback_mp4_passes_validator(tmp_path: Path):
    output_video = tmp_path / "test_synthesized.mp4"
    video_composer.generate_fallback_mp4(
        dest_path=output_video,
        width=1920,
        height=1080,
        duration_sec=8.5,
        fps=30.0
    )

    assert output_video.exists()
    assert output_video.stat().st_size > 0

    # Pass through strict pre-render media inspection
    inspection = validate_video_file(output_video)
    assert inspection.is_valid is True
    assert inspection.width == 1920
    assert inspection.height == 1080
    assert inspection.duration_seconds == 8.5
    assert inspection.aspect_ratio == "16:9"
    assert inspection.fps == 30.0


@pytest.mark.asyncio
async def test_video_composer_cooperative_cancellation(tmp_path: Path):
    output_video = tmp_path / "cancelled_video.mp4"
    scenes = [{"duration_seconds": 5.0, "narration": "Cancel test"}]

    with pytest.raises(RenderingCancelledError):
        await video_composer.compose_video(
            job_id="job_cancel_comp",
            scenes=scenes,
            selected_clips=[],
            output_path=output_video,
            cancel_check=lambda: True  # Immediate cancellation
        )


# --- End-to-End Worker Pipeline Test ---

@pytest.mark.asyncio
async def test_full_worker_pipeline_creates_all_artifacts():
    # 1. Submit a real job via API
    sample_scenes = [
        {
            "narration": "First scene demonstrating automated B-roll assembly.",
            "duration_seconds": 4.0,
            "visual_description": "Modern software developer coding on multiple monitors in high tech office"
        },
        {
            "narration": "Second scene highlighting high quality video output and subtitle tracks.",
            "duration_seconds": 5.0,
            "visual_description": "Pristine mountain alpine lake with reflection of snowy peaks"
        }
    ]

    res = client.post("/v1/jobs", json={
        "title": "Full Pipeline Test Video",
        "aspect_ratio": "16:9",
        "resolution": "1080p",
        "scenes": sample_scenes
    })
    assert res.status_code == 202
    job_id = res.json()["job_id"]

    # 2. Directly trigger worker processing for deterministic execution
    await background_worker._process_job(job_id)

    # 3. Verify final job status in SQLite store
    job = job_store.get_job(job_id)
    assert job["status"] == "completed"
    assert job["progress"] == 100.0
    assert job["current_stage"] == "completed"

    # 4. Verify all 5 deliverables exist on disk
    job_dir = settings.OUTPUT_DIR / job_id
    assert (job_dir / "video.mp4").exists()
    assert (job_dir / "captions.srt").exists()
    assert (job_dir / "captions.vtt").exists()
    assert (job_dir / "timeline.json").exists()
    assert (job_dir / "manifest.json").exists()

    # 5. Inspect video.mp4 integrity
    video_inspection = validate_video_file(job_dir / "video.mp4")
    assert video_inspection.is_valid is True
    assert video_inspection.width == 1920
    assert video_inspection.height == 1080
    assert video_inspection.aspect_ratio == "16:9"
    assert video_inspection.duration_seconds == 9.0

    # 6. Inspect manifest.json
    manifest_data = json.loads((job_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest_data["status"] == "completed"
    assert manifest_data["video_specification"]["aspect_ratio"] == "16:9"
    assert manifest_data["video_specification"]["resolution"] == "1080p"
    assert manifest_data["scene_summary"]["total_scenes"] == 2
    assert manifest_data["scene_summary"]["total_duration_seconds"] == 9.0

    # Ensure all artifacts have valid SHA-256 digests in manifest
    artifact_names = [a["name"] for a in manifest_data["artifacts"]]
    assert "video.mp4" in artifact_names
    assert "captions.srt" in artifact_names
    assert "captions.vtt" in artifact_names
    assert "timeline.json" in artifact_names
    for art in manifest_data["artifacts"]:
        assert len(art["sha256"]) == 64
        assert art["size_bytes"] > 0

    # 7. Test HTTP API artifacts endpoints for the completed job
    art_res = client.get(f"/v1/jobs/{job_id}/artifacts")
    assert art_res.status_code == 200
    artifacts_resp = art_res.json()["artifacts"]
    assert len(artifacts_resp) >= 5

    # Download video.mp4 via API
    dl_video = client.get(f"/v1/jobs/{job_id}/artifacts/video.mp4")
    assert dl_video.status_code == 200
    assert len(dl_video.content) > 0

    # Download captions.srt via API
    dl_srt = client.get(f"/v1/jobs/{job_id}/artifacts/captions.srt")
    assert dl_srt.status_code == 200
    assert "automated B-roll" in dl_srt.text and "assembly" in dl_srt.text

    # Legacy file map endpoint
    files_res = client.get(f"/v1/jobs/{job_id}/files")
    assert files_res.status_code == 200
    files_map = files_res.json()
    assert "video.mp4" in files_map
    assert "timeline.json" in files_map
    assert "captions.srt" in files_map
    assert "manifest.json" in files_map


@pytest.mark.asyncio
async def test_full_worker_pipeline_with_audio_upload():
    import io
    from tests.fixtures import make_valid_wav_bytes

    valid_wav = io.BytesIO(make_valid_wav_bytes(duration_seconds=4.0))
    sample_scenes = [
        {
            "narration": "Narration matching uploaded voiceover track exactly.",
            "duration_seconds": 4.0,
            "visual_description": "Studio recording microphone with sound waves visualization"
        }
    ]

    res = client.post(
        "/v1/jobs/multipart",
        data={
            "title": "Audio Upload Render Video",
            "aspect_ratio": "1:1",
            "resolution": "1080p",
            "scenes": json.dumps(sample_scenes)
        },
        files={"audio_file": ("narration.wav", valid_wav, "audio/wav")}
    )
    assert res.status_code == 202
    job_id = res.json()["job_id"]

    # Execute worker processing
    await background_worker._process_job(job_id)

    job = job_store.get_job(job_id)
    assert job["status"] == "completed"
    assert job["audio_source"] == "upload"

    job_dir = settings.OUTPUT_DIR / job_id
    assert (job_dir / "video.mp4").exists()
    assert (job_dir / "manifest.json").exists()

    manifest = json.loads((job_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["video_specification"]["audio_source"] == "upload"
    assert manifest["video_specification"]["aspect_ratio"] == "1:1"
    assert manifest["video_specification"]["width"] == 1080
    assert manifest["video_specification"]["height"] == 1080


@pytest.mark.asyncio
async def test_video_rendering_failure_handling_and_sanitization(monkeypatch):
    sample_scenes = [
        {
            "narration": "Failing render scene.",
            "duration_seconds": 4.0,
            "visual_description": "Abstract test failure"
        }
    ]

    res = client.post("/v1/jobs", json={
        "title": "Failing Job",
        "aspect_ratio": "16:9",
        "scenes": sample_scenes
    })
    job_id = res.json()["job_id"]

    # Mock video_composer to raise VideoRenderingError with an internal path
    async def mock_failing_compose(*args, **kwargs):
        raise VideoRenderingError("Subprocess failed: E:\\Incubrix\\video-broll-engine\\output\\job123\\temp.mp4 broken")

    monkeypatch.setattr(video_composer, "compose_video", mock_failing_compose)

    # Process job - should fail and schedule retry, sanitizing paths
    await background_worker._process_job(job_id)

    job = job_store.get_job(job_id)
    assert job["retry_count"] == 1
    # Verify no raw drive letters leaked in stage message
    assert "E:\\" not in job["stage_message"]
