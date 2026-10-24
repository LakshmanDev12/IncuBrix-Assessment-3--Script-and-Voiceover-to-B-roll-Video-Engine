import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.services.video_composer import (
    VideoComposer,
    VideoRenderingError,
    video_composer,
)
from app.services.worker import background_worker
from app.storage import job_store
from tests.fixtures import create_real_h264_clip, make_valid_wav_bytes

client = TestClient(app)


# --- 1. Real MP4 Rendering & Aspect Ratio Conforming Tests ---

@pytest.mark.asyncio
async def test_render_real_1080p_16x9_with_narration_audio(tmp_path: Path):
    """Produces real 16:9 1080p MP4 from conformed clip and narration audio."""
    # 1. Create short input video clip (1920x1080 30fps)
    src_clip = create_real_h264_clip(
        output_path=tmp_path / "src_16x9.mp4",
        width=1920,
        height=1080,
        duration_seconds=2.0,
        fps=30
    )

    # 2. Create matching voiceover WAV
    audio_wav = tmp_path / "voiceover.wav"
    audio_wav.write_bytes(make_valid_wav_bytes(duration_seconds=3.0))

    scenes = [
        {"narration": "Testing real 16:9 1080p composition.", "duration_seconds": 3.0}
    ]
    selected_clips = [
        {"scene_index": 1, "local_path": str(src_clip)}
    ]
    out_video = tmp_path / "rendered_16x9.mp4"

    res = await video_composer.compose_video(
        job_id="job_real_16x9",
        scenes=scenes,
        selected_clips=selected_clips,
        output_path=out_video,
        aspect_ratio="16:9",
        resolution="1080p",
        audio_path=audio_wav
    )

    assert out_video.exists()
    assert res["rendering_engine"] == "ffmpeg"
    assert res["width"] == 1920
    assert res["height"] == 1080

    # FFprobe deep verification
    quality = video_composer.verify_rendered_output(
        output_path=out_video,
        expected_width=1920,
        expected_height=1080,
        expected_duration=3.0,
        tolerance_duration=0.5
    )
    assert quality.validation_passed is True
    assert quality.video_codec == "h264"
    assert quality.audio_codec == "aac"
    assert quality.width == 1920
    assert quality.height == 1080
    assert quality.pix_fmt == "yuv420p"
    assert quality.audio_channels == 2
    assert quality.audio_sample_rate in (44100, 48000)
    assert abs(quality.duration_seconds - 3.0) <= 0.2


@pytest.mark.asyncio
async def test_render_real_9x16_vertical_smart_crop(tmp_path: Path):
    """Verifies 16:9 landscape clip is smartly cropped into 9:16 vertical without distortion."""
    # 16:9 landscape input
    src_clip = create_real_h264_clip(
        output_path=tmp_path / "src_landscape.mp4",
        width=1920,
        height=1080,
        duration_seconds=2.0,
        fps=30
    )
    out_video = tmp_path / "rendered_vertical_9x16.mp4"
    scenes = [{"narration": "Vertical video test", "duration_seconds": 2.5}]
    selected_clips = [{"scene_index": 1, "local_path": str(src_clip)}]

    await video_composer.compose_video(
        job_id="job_real_9x16",
        scenes=scenes,
        selected_clips=selected_clips,
        output_path=out_video,
        aspect_ratio="9:16",
        resolution="1080p"
    )

    assert out_video.exists()
    quality = video_composer.verify_rendered_output(
        output_path=out_video,
        expected_width=1080,
        expected_height=1920,
        expected_duration=2.5,
        tolerance_duration=0.5
    )
    assert quality.width == 1080
    assert quality.height == 1920
    assert quality.video_codec == "h264"
    assert quality.audio_codec == "aac"


@pytest.mark.asyncio
async def test_render_real_1x1_square_smart_crop(tmp_path: Path):
    """Verifies 16:9 landscape clip is smartly cropped into 1:1 square without distortion."""
    src_clip = create_real_h264_clip(
        output_path=tmp_path / "src_for_square.mp4",
        width=1920,
        height=1080,
        duration_seconds=2.0,
        fps=30
    )
    out_video = tmp_path / "rendered_square_1x1.mp4"
    scenes = [{"narration": "Square video test", "duration_seconds": 2.0}]
    selected_clips = [{"scene_index": 1, "local_path": str(src_clip)}]

    await video_composer.compose_video(
        job_id="job_real_1x1",
        scenes=scenes,
        selected_clips=selected_clips,
        output_path=out_video,
        aspect_ratio="1:1",
        resolution="1080p"
    )

    assert out_video.exists()
    quality = video_composer.verify_rendered_output(
        output_path=out_video,
        expected_width=1080,
        expected_height=1080,
        expected_duration=2.0,
        tolerance_duration=0.5
    )
    assert quality.width == 1080
    assert quality.height == 1080


# --- 2. Robust Concatenation & Looping Tests ---

@pytest.mark.asyncio
async def test_robust_concatenation_cross_resolution_and_framerate(tmp_path: Path):
    """Concatenates clips with different resolutions (720p vs 1080p) and frame rates (24fps vs 30fps)."""
    # Clip 1: 720p @ 24fps
    clip1 = create_real_h264_clip(
        output_path=tmp_path / "clip_720p_24fps.mp4",
        width=1280,
        height=720,
        duration_seconds=2.0,
        fps=24,
        pattern="testsrc"
    )
    # Clip 2: 1080p @ 30fps
    clip2 = create_real_h264_clip(
        output_path=tmp_path / "clip_1080p_30fps.mp4",
        width=1920,
        height=1080,
        duration_seconds=2.0,
        fps=30,
        pattern="smptebars"
    )

    out_video = tmp_path / "concatenated_output.mp4"
    scenes = [
        {"narration": "First scene from 720p 24fps source.", "duration_seconds": 2.0},
        {"narration": "Second scene from 1080p 30fps source.", "duration_seconds": 2.0}
    ]
    selected_clips = [
        {"scene_index": 1, "local_path": str(clip1)},
        {"scene_index": 2, "local_path": str(clip2)}
    ]

    await video_composer.compose_video(
        job_id="job_cross_norm",
        scenes=scenes,
        selected_clips=selected_clips,
        output_path=out_video,
        aspect_ratio="16:9",
        resolution="1080p"
    )

    assert out_video.exists()
    quality = video_composer.verify_rendered_output(
        output_path=out_video,
        expected_width=1920,
        expected_height=1080,
        expected_duration=4.0,
        tolerance_duration=0.5
    )
    # Both conformed to standard 1080p 30fps
    assert quality.width == 1920
    assert quality.height == 1080
    assert quality.fps == 30.0
    assert abs(quality.duration_seconds - 4.0) <= 0.3


@pytest.mark.asyncio
async def test_shorter_clip_loops_to_fill_scene_duration(tmp_path: Path):
    """Input clip is 1.0s, scene is 3.5s -> loops seamlessly without freezing on last frame."""
    short_clip = create_real_h264_clip(
        output_path=tmp_path / "short_1s.mp4",
        width=1920,
        height=1080,
        duration_seconds=1.0,
        fps=30
    )
    out_video = tmp_path / "looped_output.mp4"
    scenes = [{"narration": "Extended scene with looping B-roll", "duration_seconds": 3.5}]
    selected_clips = [{"scene_index": 1, "local_path": str(short_clip)}]

    await video_composer.compose_video(
        job_id="job_looping",
        scenes=scenes,
        selected_clips=selected_clips,
        output_path=out_video,
        aspect_ratio="16:9",
        resolution="1080p"
    )

    assert out_video.exists()
    quality = video_composer.verify_rendered_output(
        output_path=out_video,
        expected_width=1920,
        expected_height=1080,
        expected_duration=3.5,
        tolerance_duration=0.5
    )
    assert abs(quality.duration_seconds - 3.5) <= 0.2


# --- 3. Audio Alignment Policy Tests ---

@pytest.mark.asyncio
async def test_audio_alignment_policy_shorter_audio_pads_silence(tmp_path: Path):
    """Audio is 1.5s, video duration is 4.0s -> pads trailing silence so video holds visual pacing."""
    audio_wav = tmp_path / "short_audio.wav"
    audio_wav.write_bytes(make_valid_wav_bytes(duration_seconds=1.5))

    out_video = tmp_path / "padded_audio.mp4"
    scenes = [{"narration": "Scene needing padded audio.", "duration_seconds": 4.0}]

    await video_composer.compose_video(
        job_id="job_audio_pad",
        scenes=scenes,
        selected_clips=[],
        output_path=out_video,
        aspect_ratio="16:9",
        resolution="1080p",
        audio_path=audio_wav
    )

    assert out_video.exists()
    quality = video_composer.verify_rendered_output(
        output_path=out_video,
        expected_width=1920,
        expected_height=1080,
        expected_duration=4.0,
        tolerance_duration=0.5
    )
    assert abs(quality.duration_seconds - 4.0) <= 0.2
    assert quality.audio_codec == "aac"


@pytest.mark.asyncio
async def test_audio_alignment_policy_longer_audio_fades_and_trims(tmp_path: Path):
    """Audio is 6.0s, video duration is 3.0s -> gracefully fades out at 2.5s and trims at 3.0s."""
    audio_wav = tmp_path / "long_audio.wav"
    audio_wav.write_bytes(make_valid_wav_bytes(duration_seconds=6.0))

    out_video = tmp_path / "faded_audio.mp4"
    scenes = [{"narration": "Scene with audio exceeding duration.", "duration_seconds": 3.0}]

    await video_composer.compose_video(
        job_id="job_audio_fade",
        scenes=scenes,
        selected_clips=[],
        output_path=out_video,
        aspect_ratio="16:9",
        resolution="1080p",
        audio_path=audio_wav
    )

    assert out_video.exists()
    quality = video_composer.verify_rendered_output(
        output_path=out_video,
        expected_width=1920,
        expected_height=1080,
        expected_duration=3.0,
        tolerance_duration=0.5
    )
    assert abs(quality.duration_seconds - 3.0) <= 0.2


@pytest.mark.asyncio
async def test_audio_alignment_policy_no_audio_synthesizes_stereo_aac(tmp_path: Path):
    """No audio source -> synthesizes silent stereo AAC audio stream so MP4 is standard compliant."""
    out_video = tmp_path / "silent_audio.mp4"
    scenes = [{"narration": "Silent visual scene.", "duration_seconds": 2.5}]

    await video_composer.compose_video(
        job_id="job_no_audio",
        scenes=scenes,
        selected_clips=[],
        output_path=out_video,
        aspect_ratio="16:9",
        resolution="1080p",
        audio_path=None
    )

    assert out_video.exists()
    quality = video_composer.verify_rendered_output(
        output_path=out_video,
        expected_width=1920,
        expected_height=1080,
        expected_duration=2.5,
        tolerance_duration=0.5
    )
    assert quality.audio_codec == "aac"
    assert quality.audio_channels == 2
    assert quality.audio_sample_rate in (44100, 48000)


# --- 4. FFprobe Quality Gate Rejection Tests ---

def test_ffprobe_quality_check_rejects_corrupted_file(tmp_path: Path):
    """Passing a truncated/corrupted video file triggers VideoRenderingError."""
    corrupt_file = tmp_path / "corrupted.mp4"
    corrupt_file.write_bytes(b"\x00\x00\x00\x18ftypisom" + b"\xff" * 50)

    with pytest.raises(VideoRenderingError) as exc:
        video_composer.verify_rendered_output(
            output_path=corrupt_file,
            expected_width=1920,
            expected_height=1080,
            expected_duration=5.0
        )
    assert exc.value.code in ("FFPROBE_ERROR", "CORRUPTED_MEDIA", "NO_VIDEO_STREAM")


# --- 5. End-to-End Pipeline & Manifest Quality Gate Integration ---

@pytest.mark.asyncio
async def test_end_to_end_job_records_quality_verification_in_manifest():
    """Submits full job via API, runs worker, and verifies manifest contains quality_verification."""
    sample_scenes = [
        {
            "narration": "Scene 1 for full quality check pipeline.",
            "duration_seconds": 3.0,
            "visual_description": "Modern software developer coding on multiple monitors in high tech office"
        },
        {
            "narration": "Scene 2 for full quality check pipeline.",
            "duration_seconds": 3.0,
            "visual_description": "Pristine mountain alpine lake with reflection of snowy peaks"
        }
    ]

    res = client.post("/v1/jobs", json={
        "title": "Full Quality Gate Render Video",
        "aspect_ratio": "16:9",
        "resolution": "1080p",
        "scenes": sample_scenes
    })
    assert res.status_code == 202
    job_id = res.json()["job_id"]

    await background_worker._process_job(job_id)

    job = job_store.get_job(job_id)
    assert job["status"] == "completed"

    job_dir = settings.OUTPUT_DIR / job_id
    manifest_file = job_dir / "manifest.json"
    assert manifest_file.exists()

    manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
    assert "quality_verification" in manifest_data
    q_check = manifest_data["quality_verification"]
    assert q_check["validation_passed"] is True
    assert q_check["video_codec"] == "h264"
    assert q_check["audio_codec"] == "aac"
    assert q_check["width"] == 1920
    assert q_check["height"] == 1080
    assert q_check["pix_fmt"] == "yuv420p"
    assert abs(q_check["duration_seconds"] - 6.0) <= 0.3
