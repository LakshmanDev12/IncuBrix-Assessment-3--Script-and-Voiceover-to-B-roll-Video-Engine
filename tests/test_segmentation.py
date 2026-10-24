import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.segmentation import (
    SceneSegmenter,
    SegmentationConfig,
    SegmentationError,
    scene_segmenter,
)

client = TestClient(app)


def test_split_coherent_scenes_on_punctuation():
    script = (
        "Welcome to our deep dive into quantum computing! "
        "Today, researchers are breaking new barriers every single week. "
        "Will scalable quantum supremacy arrive sooner than we think? "
        "Let's explore the groundbreaking architecture of qubits and error correction."
    )
    scenes = scene_segmenter.segment_script(script)

    assert len(scenes) >= 3
    # Check that each scene has non-empty narration, visual description, and positive duration
    for s in scenes:
        assert len(s.narration) > 0
        assert s.duration_seconds >= 0.5
        assert len(s.visual_description) >= 3

    # Exact text preservation check
    assert scene_segmenter.verify_text_preservation(script, scenes) is True


def test_handles_abbreviations_without_splitting():
    script = "Dr. Smith and Prof. Jones visited Washington in the U.S. to discuss AI. The meeting began at approx. 9 AM."
    scenes = scene_segmenter.segment_script(script)

    # Should split into 2 sentences, not split on "Dr.", "Prof.", "U.S.", or "approx."
    assert len(scenes) == 2
    assert "Dr. Smith and Prof. Jones" in scenes[0].narration
    assert "approx. 9 AM" in scenes[1].narration
    assert scene_segmenter.verify_text_preservation(script, scenes) is True


def test_allocates_timing_without_zero_or_negative_durations():
    script = "First intro scene. Second short scene. Third concluding scene."
    scenes = scene_segmenter.segment_script(script, total_duration=9.0)

    assert len(scenes) == 3
    total_alloc = sum(s.duration_seconds for s in scenes)
    assert pytest.approx(total_alloc, abs=0.01) == 9.0

    for s in scenes:
        assert s.duration_seconds >= 0.5
        assert s.duration_seconds <= 60.0
        assert not s.duration_seconds <= 0.0


def test_proportional_duration_distribution_with_audio_track():
    script = (
        "Short start. "
        "This middle section contains significantly more words and detailed technical elaboration that requires more visual screen time. "
        "Quick end."
    )
    total_audio = 20.0
    scenes = scene_segmenter.segment_script(script, total_duration=total_audio)

    assert len(scenes) == 3
    assert pytest.approx(sum(s.duration_seconds for s in scenes), abs=0.05) == total_audio

    # The middle scene has far more words, so its duration must be strictly greater than the short scenes
    assert scenes[1].duration_seconds > scenes[0].duration_seconds
    assert scenes[1].duration_seconds > scenes[2].duration_seconds
    assert scene_segmenter.verify_text_preservation(script, scenes) is True


def test_script_only_mode_estimates_by_speech_cadence():
    script = "This is a standard script sentence. And here is another regular sentence."
    cfg = SegmentationConfig(words_per_minute=120)  # 2 words/sec
    scenes = scene_segmenter.segment_script(script, config=cfg)

    assert len(scenes) == 2
    for s in scenes:
        assert s.duration_seconds >= 0.5
    assert scene_segmenter.verify_text_preservation(script, scenes) is True


def test_merges_very_short_sentences():
    # Micro-sentences should be merged to prevent tiny sub-0.5s scenes
    script = "Hi! Welcome. Let's begin our journey through artificial intelligence."
    scenes = scene_segmenter.segment_script(script)

    assert len(scenes) <= 2
    assert scene_segmenter.verify_text_preservation(script, scenes) is True


def test_splits_long_sentences_at_clause_boundaries():
    script = (
        "In the early days of personal computing, engineers worked in small garages across Silicon Valley, "
        "writing assembly code on microprocessors that had only a few kilobytes of RAM, "
        "yet their passionate vision of democratizing technology eventually transformed every aspect of modern civilization."
    )
    cfg = SegmentationConfig(max_words_per_scene=16)
    scenes = scene_segmenter.segment_script(script, config=cfg)

    assert len(scenes) >= 2
    for s in scenes:
        assert len(s.narration.split()) <= 20
        assert s.duration_seconds >= 0.5

    assert scene_segmenter.verify_text_preservation(script, scenes) is True


def test_empty_script_rejected():
    with pytest.raises(SegmentationError) as exc_info:
        scene_segmenter.segment_script("")
    assert exc_info.value.code == "EMPTY_SCRIPT"

    with pytest.raises(SegmentationError) as exc_info2:
        scene_segmenter.segment_script("     \n\t  ")
    assert exc_info2.value.code == "EMPTY_SCRIPT"


def test_repeated_text_handled_cleanly():
    script = "The sun rises over the horizon. The sun rises over the horizon. The sun rises over the horizon."
    scenes = scene_segmenter.segment_script(script)

    assert len(scenes) == 3
    assert scene_segmenter.verify_text_preservation(script, scenes) is True


def test_duration_insufficient_for_scenes_rejected():
    script = "One sentence here. Two sentence here. Three sentence here. Four sentence here."
    with pytest.raises(SegmentationError) as exc_info:
        # 4 scenes cannot fit in 1.0 second (min is 4 * 0.5 = 2.0s)
        scene_segmenter.segment_script(script, total_duration=1.0)
    assert exc_info.value.code == "DURATION_TOO_SHORT_FOR_SCENES"


def test_segmentation_api_endpoint():
    response = client.post(
        "/v1/scenes/segment",
        json={
            "script": "Artificial intelligence is reshaping software. Engineers can now build products at lightning speed.",
            "total_duration_seconds": 12.0
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["scene_count"] >= 2
    assert data["total_duration_seconds"] == 12.0
    assert data["original_text_preserved"] is True
    assert len(data["scenes"]) == data["scene_count"]


def test_segment_scene_list_validates_timing_and_rejects_negative_or_zero():
    valid_scenes = [
        {"narration": "First scene narration.", "duration_seconds": 4.0},
        {"narration": "Second scene narration.", "duration_seconds": 6.0, "visual_description": "Custom visual"}
    ]
    res = scene_segmenter.segment_input(scenes=valid_scenes)
    assert len(res) == 2
    assert res[0].duration_seconds == 4.0
    assert len(res[0].visual_description) >= 3  # Auto-generated description
    assert res[1].visual_description == "Custom visual"

    # Reject zero duration
    zero_scene = [{"narration": "Zero length scene.", "duration_seconds": 0.0}]
    with pytest.raises(SegmentationError) as exc_zero:
        scene_segmenter.segment_input(scenes=zero_scene)
    assert exc_zero.value.code == "INVALID_SCENE_DURATION"

    # Reject negative duration
    negative_scene = [{"narration": "Negative length scene.", "duration_seconds": -3.5}]
    with pytest.raises(SegmentationError) as exc_neg:
        scene_segmenter.segment_input(scenes=negative_scene)
    assert exc_neg.value.code == "INVALID_SCENE_DURATION"


def test_segment_aligned_segments_coalescing_and_preservation():
    # Whisper-style word or phrase timestamps
    segments = [
        {"text": "Welcome to", "start_seconds": 0.0, "end_seconds": 1.2},
        {"text": "the future of", "start_seconds": 1.2, "end_seconds": 2.5},
        {"text": "autonomous driving.", "start_seconds": 2.5, "end_seconds": 4.8},
        {"text": "Vehicles will navigate", "start_seconds": 5.0, "end_seconds": 7.1},
        {"text": "cities without human drivers.", "start_seconds": 7.1, "end_seconds": 10.2}
    ]

    scenes = scene_segmenter.segment_input(aligned_segments=segments)
    assert len(scenes) >= 2
    # Verify timing is strictly positive
    for s in scenes:
        assert s.duration_seconds >= 0.5
        assert len(s.visual_description) >= 3

    # Check verbatim preservation of segment text
    full_text = " ".join(s["text"] for s in segments)
    assert scene_segmenter.verify_text_preservation(full_text, scenes) is True


def test_segment_aligned_segments_rejects_negative_or_zero_timing():
    bad_segments = [
        {"text": "Valid start", "start_seconds": 0.0, "end_seconds": 2.0},
        {"text": "Backwards timing", "start_seconds": 3.0, "end_seconds": 1.5}
    ]
    with pytest.raises(SegmentationError) as exc:
        scene_segmenter.segment_input(aligned_segments=bad_segments)
    assert exc.value.code == "INVALID_SEGMENT_TIMING"


def test_segmentation_endpoint_with_aligned_segments_and_scenes():
    # API test with aligned_segments
    res_aligned = client.post(
        "/v1/scenes/segment",
        json={
            "aligned_segments": [
                {"text": "First chapter starts now.", "start_seconds": 0.0, "end_seconds": 3.5},
                {"text": "Second chapter begins right here.", "start_seconds": 3.5, "end_seconds": 7.0}
            ]
        }
    )
    assert res_aligned.status_code == 200
    data_aligned = res_aligned.json()
    assert data_aligned["scene_count"] >= 2
    assert data_aligned["original_text_preserved"] is True

    # API test with pre-existing scenes
    res_scenes = client.post(
        "/v1/scenes/segment",
        json={
            "scenes": [
                {"narration": "Opening scene.", "duration_seconds": 5.0},
                {"narration": "Closing scene.", "duration_seconds": 5.0}
            ]
        }
    )
    assert res_scenes.status_code == 200
    data_scenes = res_scenes.json()
    assert data_scenes["scene_count"] == 2
    assert data_scenes["total_duration_seconds"] == 10.0

