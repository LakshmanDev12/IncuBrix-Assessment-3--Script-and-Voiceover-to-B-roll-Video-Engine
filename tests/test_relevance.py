import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas import CandidateMediaItem
from app.services.relevance import (
    DeterministicRelevanceRanker,
    EmbeddingRelevanceRanker,
    deterministic_ranker,
    get_relevance_ranker,
)

client = TestClient(app)


def test_known_examples_ranking():
    query = "Software developer writing Python code on a multi-monitor desk in a modern tech office"

    candidate_code = CandidateMediaItem(
        id="clip_code_01",
        title="Developer Coding Python on Dual Monitors",
        description="Close-up of a programmer typing Python source code in a modern office setup.",
        tags=["coding", "python", "software", "office", "developer"],
        duration_seconds=12.0,
        aspect_ratio="16:9"
    )

    candidate_cooking = CandidateMediaItem(
        id="clip_cook_02",
        title="Chef Chopping Fresh Vegetables",
        description="Professional chef slicing vegetables in a restaurant kitchen with sharp knives.",
        tags=["cooking", "food", "kitchen", "restaurant"],
        duration_seconds=12.0,
        aspect_ratio="16:9"
    )

    candidate_nature = CandidateMediaItem(
        id="clip_nature_03",
        title="Snowy Alpine Mountain Peaks",
        description="Drone aerial footage over snow-covered mountain ridges at sunrise.",
        tags=["nature", "mountains", "snow", "winter"],
        duration_seconds=12.0,
        aspect_ratio="16:9"
    )

    ranked = deterministic_ranker.rank(
        query_description=query,
        candidates=[candidate_cooking, candidate_code, candidate_nature],
        target_duration=8.0,
        target_aspect_ratio="16:9"
    )

    assert len(ranked) == 3
    # Candidate 1 (code) must be ranked first by a wide margin
    assert ranked[0].candidate.id == "clip_code_01"
    assert ranked[0].score > 0.4
    assert ranked[0].breakdown.phrase_match > 0.0
    assert ranked[0].breakdown.tag_overlap > 0.0

    # Unrelated candidates must have zero score or near-zero
    assert ranked[1].score == 0.0 or ranked[1].score < 0.1
    assert ranked[2].score == 0.0


def test_negative_matches_produce_zero_score_with_clear_reason():
    query = "Deep ocean scuba diver exploring coral reef with tropical sea turtles"

    desert_clip = CandidateMediaItem(
        id="clip_desert_01",
        title="Sahara Desert Sand Dunes Under Blazing Sun",
        description="Endless dry yellow sand dunes blowing in the scorching heat.",
        tags=["desert", "sand", "heat", "dry"],
        duration_seconds=15.0,
        aspect_ratio="16:9"
    )

    ranked = deterministic_ranker.rank(
        query_description=query,
        candidates=[desert_clip],
        target_duration=10.0
    )

    assert len(ranked) == 1
    assert ranked[0].score == 0.0
    assert "No semantic, phrase, or tag overlap found" in ranked[0].reasons[0]


def test_phrase_match_outranks_scattered_unigrams():
    query = "Autonomous electric vehicle navigating urban city traffic at rush hour"

    # Candidate A matches exact phrases: "autonomous electric vehicle", "urban city"
    candidate_a = CandidateMediaItem(
        id="clip_a",
        title="Autonomous Electric Vehicle in Urban Traffic",
        description="Smart autonomous electric vehicle driving safely through heavy urban traffic.",
        tags=["autonomous", "electric vehicle", "urban", "traffic"],
        duration_seconds=10.0,
        aspect_ratio="16:9"
    )

    # Candidate B contains some shared words ("electric", "city") but in completely different contexts
    candidate_b = CandidateMediaItem(
        id="clip_b",
        title="Electric Guitar Concert in Ancient City Ruins",
        description="Rock band playing loud electric music among historical stone monuments in an old city.",
        tags=["music", "guitar", "concert", "electric"],
        duration_seconds=10.0,
        aspect_ratio="16:9"
    )

    ranked = deterministic_ranker.rank(
        query_description=query,
        candidates=[candidate_b, candidate_a],
        target_duration=8.0
    )

    assert ranked[0].candidate.id == "clip_a"
    assert ranked[0].breakdown.phrase_match > ranked[1].breakdown.phrase_match
    assert ranked[0].score > ranked[1].score


def test_duration_suitability_penalty():
    query = "Sunrise over city skyline with golden morning clouds"

    # Candidate A is 15 seconds (ample length for 10s scene)
    long_clip = CandidateMediaItem(
        id="clip_long",
        title="Sunrise Over City Skyline",
        description="Time-lapse of sunrise over city skyline with golden morning clouds.",
        tags=["sunrise", "skyline", "city"],
        duration_seconds=15.0,
        aspect_ratio="16:9"
    )

    # Candidate B has identical description but is only 2 seconds (too short for 10s scene)
    short_clip = CandidateMediaItem(
        id="clip_short",
        title="Sunrise Over City Skyline",
        description="Time-lapse of sunrise over city skyline with golden morning clouds.",
        tags=["sunrise", "skyline", "city"],
        duration_seconds=2.0,
        aspect_ratio="16:9"
    )

    ranked = deterministic_ranker.rank(
        query_description=query,
        candidates=[short_clip, long_clip],
        target_duration=10.0
    )

    assert ranked[0].candidate.id == "clip_long"
    assert ranked[0].breakdown.duration_fit == 1.0
    assert ranked[1].breakdown.duration_fit < 0.5
    assert ranked[0].score > ranked[1].score


def test_aspect_ratio_compatibility_bonus():
    query = "Modern boardroom business presentation"

    clip_16_9 = CandidateMediaItem(
        id="clip_landscape",
        title="Boardroom Business Presentation",
        description="Corporate team in modern boardroom business presentation.",
        tags=["business", "presentation"],
        duration_seconds=10.0,
        aspect_ratio="16:9"
    )

    clip_9_16 = CandidateMediaItem(
        id="clip_vertical",
        title="Boardroom Business Presentation",
        description="Corporate team in modern boardroom business presentation.",
        tags=["business", "presentation"],
        duration_seconds=10.0,
        aspect_ratio="9:16"
    )

    ranked = deterministic_ranker.rank(
        query_description=query,
        candidates=[clip_9_16, clip_16_9],
        target_aspect_ratio="16:9"
    )

    assert ranked[0].candidate.id == "clip_landscape"
    assert ranked[0].breakdown.aspect_ratio_fit == 1.0
    assert ranked[1].breakdown.aspect_ratio_fit == 0.85
    assert ranked[0].score > ranked[1].score


def test_auditable_reasons_and_breakdown_structures():
    query = "Futuristic robot working on assembly line in smart factory"

    robot_clip = CandidateMediaItem(
        id="clip_robot",
        title="Industrial Robot on Automated Assembly Line",
        description="High-tech smart factory robot welding parts on an automated assembly line.",
        tags=["robot", "factory", "automation", "assembly"],
        duration_seconds=10.0,
        aspect_ratio="16:9"
    )

    ranked = deterministic_ranker.rank(
        query_description=query,
        candidates=[robot_clip],
        target_duration=5.0
    )

    item = ranked[0]
    assert len(item.reasons) >= 3
    # Confirm auditable strings exist
    assert any("Duration fit" in r for r in item.reasons)
    assert any("Final composite score" in r for r in item.reasons)

    # Check breakdown fields
    bd = item.breakdown
    assert bd.duration_fit == 1.0
    assert bd.aspect_ratio_fit == 1.0
    assert bd.text_similarity > 0.0
    assert bd.penalties == 0.0


def test_pluggable_interface_and_embedding_adapter_fallback():
    # Deterministic ranker
    ranker_det = get_relevance_ranker("deterministic")
    assert isinstance(ranker_det, DeterministicRelevanceRanker)
    assert ranker_det.ranker_name == "deterministic_baseline"
    assert "No neural model loaded" in ranker_det.model_info

    # Embedding adapter
    ranker_emb = get_relevance_ranker("embedding")
    assert isinstance(ranker_emb, EmbeddingRelevanceRanker)

    # In an environment without sentence-transformers installed, it must report fallback
    assert "fallback" in ranker_emb.ranker_name or ranker_emb.ranker_name == "embedding_neural_adapter"
    assert "Fallback Active" in ranker_emb.model_info or "all-MiniLM-L6-v2" in ranker_emb.model_info

    # Rank with embedding adapter (gracefully runs fallback without crashing)
    clip = CandidateMediaItem(
        id="c1",
        title="Mountain Sunset",
        description="Vibrant colors of mountain sunset over pines.",
        tags=["sunset", "mountains"],
        duration_seconds=8.0
    )
    res = ranker_emb.rank(query_description="Mountain sunset over pine forest", candidates=[clip])
    assert len(res) == 1
    assert res[0].score > 0.0


def test_ambiguous_candidates_tie_breaking():
    query = "Sunset over lake"

    # Two clips with identical matching text but different durations
    cand1 = CandidateMediaItem(id="b_clip", title="Sunset Over Lake", tags=["sunset"], duration_seconds=5.0)
    cand2 = CandidateMediaItem(id="a_clip", title="Sunset Over Lake", tags=["sunset"], duration_seconds=10.0)

    # With a target duration of 8.0s, cand2 (10s) fits better than cand1 (5s)
    ranked = deterministic_ranker.rank(query_description=query, candidates=[cand1, cand2], target_duration=8.0)
    assert ranked[0].candidate.id == "a_clip"


def test_empty_candidates_returns_empty_list():
    res = deterministic_ranker.rank(query_description="Whatever", candidates=[])
    assert res == []


def test_media_ranking_api_endpoint():
    payload = {
        "query_description": "Data scientist training neural networks on cloud GPU cluster",
        "target_duration": 6.0,
        "target_aspect_ratio": "16:9",
        "ranker_type": "deterministic",
        "candidates": [
            {
                "id": "c_ai",
                "title": "Cloud Server Room GPU Cluster",
                "description": "Blinking lights in modern data center training neural networks.",
                "tags": ["cloud", "gpu", "neural network", "data"],
                "duration_seconds": 10.0,
                "aspect_ratio": "16:9"
            },
            {
                "id": "c_coffee",
                "title": "Morning Coffee Brewing",
                "description": "Barista pouring espresso in cup.",
                "tags": ["coffee", "morning"],
                "duration_seconds": 10.0,
                "aspect_ratio": "16:9"
            }
        ]
    }

    response = client.post("/v1/media/rank", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["active_ranker"] == "deterministic_baseline"
    assert len(data["ranked_candidates"]) == 2
    assert data["ranked_candidates"][0]["candidate"]["id"] == "c_ai"
    assert data["ranked_candidates"][0]["score"] > 0.3
    assert data["ranked_candidates"][1]["score"] == 0.0
