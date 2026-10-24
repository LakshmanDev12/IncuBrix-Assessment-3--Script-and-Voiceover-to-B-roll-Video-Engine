from app.config import settings
from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional, Set

from app.schemas import CandidateMediaItem, MediaMetadata, Scene
from app.services.providers import (
    AttributionLedger,
    BaseMediaProvider,
    MediaCandidate,
    MediaProviderRegistry,
    provider_registry,
)
from app.services.relevance import (
    BaseRelevanceRanker,
    RankedCandidateItem,
    deterministic_ranker,
)

logger = logging.getLogger("video_engine.media_selector")


class MediaSelectionError(ValueError):
    """Raised when media candidate selection fails."""
    def __init__(self, message: str, code: str = "MEDIA_SELECTION_ERROR", details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}


@dataclass
class SelectedMediaClip:
    scene_index: int
    candidate: MediaCandidate
    relevance_score: float
    selection_rank: int
    selection_reason: str
    reasons: List[str]
    score_breakdown: Dict[str, float]
    provenance: Dict[str, Any]
    local_path: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scene_index": self.scene_index,
            "clip_id": self.candidate.id,
            "title": self.candidate.title,
            "download_url": self.candidate.download_url,
            "relevance_score": self.relevance_score,
            "selection_rank": self.selection_rank,
            "selection_reason": self.selection_reason,
            "reasons": self.reasons,
            "score_breakdown": self.score_breakdown,
            "provenance": self.provenance,
            "local_path": self.local_path or getattr(self.candidate, "local_path", None)
        }


@dataclass
class SelectionResult:
    selected_clips: List[SelectedMediaClip]
    updated_scenes: List[Scene]
    duplicate_clips_prevented: int
    attribution_ledger: AttributionLedger
    total_scenes: int


class MediaSelector:
    """
    Selects optimal B-roll media clips for scenes using multi-feature relevance ranking,
    strict duplicate prevention rules, and full provenance tracking.
    """

    def __init__(
        self,
        registry: Optional[MediaProviderRegistry] = None,
        ranker: Optional[BaseRelevanceRanker] = None
    ):
        self.registry = registry or provider_registry
        self.ranker = ranker or deterministic_ranker

    def select_media_for_scenes(
        self,
        job_id: str,
        scenes: List[Scene],
        aspect_ratio: str = "16:9",
        target_aspect_ratio: Optional[str] = None,
        allow_repeated_clips: bool = False,
        min_relevance_threshold: float = 0.1,
        provider_name: Optional[str] = None
    ) -> SelectionResult:
        if target_aspect_ratio is not None:
            aspect_ratio = target_aspect_ratio
        if not scenes:
            raise MediaSelectionError("Scene list cannot be empty.", code="EMPTY_SCENES")

        used_clip_ids: Set[str] = set()
        selected_clips: List[SelectedMediaClip] = []
        updated_scenes: List[Scene] = []
        duplicate_prevented_count = 0

        ledger = AttributionLedger(job_id=job_id)

        for i, scene in enumerate(scenes):
            scene_idx = i + 1
            query = scene.visual_description or scene.narration

            # 1. Retrieve candidate pool from registry
            try:
                candidates = self.registry.search(
                    query=query,
                    provider_name=provider_name,
                    target_duration=scene.duration_seconds,
                    aspect_ratio=aspect_ratio,
                    limit=15
                )
            except Exception as exc:
                logger.error(f"Provider search failed for scene {scene_idx}: {exc}")
                # Fallback to local_cc0 archive directly
                local_provider = self.registry.get_provider("local_cc0")
                candidates = local_provider.search(query=query, limit=10) if local_provider else []

            if not candidates:
                # Query fallback with relaxed terms if no candidates found
                local_provider = self.registry.get_provider("local_cc0")
                candidates = local_provider.search(query="", limit=5) if local_provider else []

            if not candidates:
                raise MediaSelectionError(
                    f"No candidate media available for scene {scene_idx} ('{scene.visual_description[:50]}').",
                    code="NO_CANDIDATES_AVAILABLE",
                    details={"scene_index": scene_idx}
                )

            # 2. Convert to CandidateMediaItem for the ranker
            ranker_items = [
                CandidateMediaItem(
                    id=c.id,
                    provider=c.provider,
                    title=c.title,
                    description=c.description,
                    tags=c.tags,
                    duration_seconds=c.duration_seconds,
                    aspect_ratio=c.aspect_ratio if c.aspect_ratio in ("16:9", "9:16", "1:1") else "16:9",
                    source_url=c.download_url,
                    source_page_url=c.source_page_url,
                    download_url=c.download_url,
                    preview_url=c.preview_url,
                    creator=c.creator,
                    creator_url=c.creator_url,
                    license_name=c.license_info.name,
                    attribution=f"'{c.title}' by {c.creator} ({c.license_info.name})",
                    verification_status=c.verification_status,
                    verified=c.verified,
                    media_type="video"
                )
                for c in candidates
            ]
            candidate_map = {c.id: c for c in candidates}

            # 3. Rank candidates using relevance module
            ranked = self.ranker.rank(
                query_description=scene.visual_description,
                candidates=ranker_items,
                target_duration=scene.duration_seconds,
                target_aspect_ratio=aspect_ratio
            )

            # 4. Select candidate applying duplicate prevention rules
            chosen_ranked: Optional[RankedCandidateItem] = None
            selection_reason = ""
            rank_position = 0

            for rank_idx, item in enumerate(ranked):
                clip_id = item.candidate.id
                if not allow_repeated_clips and clip_id in used_clip_ids:
                    duplicate_prevented_count += 1
                    logger.info(f"Skipping duplicate clip '{clip_id}' for scene {scene_idx}; evaluating next candidate.")
                    continue

                chosen_ranked = item
                rank_position = rank_idx + 1
                if rank_position == 1:
                    selection_reason = f"Top-ranked relevance match (score: {item.score:.3f})."
                else:
                    selection_reason = f"Selected #{rank_position} candidate to prevent repeating clip used in a previous scene."
                break

            # If all candidates in the pool were already used and allow_repeated_clips is False
            if chosen_ranked is None:
                if ranked:
                    chosen_ranked = ranked[0]
                    rank_position = 1
                    selection_reason = "Reused top-ranked clip because candidate pool was exhausted."
                else:
                    raise MediaSelectionError(f"No usable candidates for scene {scene_idx}.", code="SELECTION_EXHAUSTED")

            chosen_candidate = candidate_map[chosen_ranked.candidate.id]
            used_clip_ids.add(chosen_candidate.id)

            # Quick check if candidate is already in disk cache
            if not getattr(chosen_candidate, "local_path", None) and chosen_candidate.download_url:
                cache_dir = settings.OUTPUT_DIR / "remote_cache"
                cached_file = cache_dir / f"{chosen_candidate.id}.mp4"
                if cached_file.exists() and cached_file.stat().st_size > 10240:
                    chosen_candidate.local_path = str(cached_file.resolve())

            # Check low relevance warning
            if chosen_ranked.score < min_relevance_threshold:
                selection_reason += f" (Low relevance notice: score {chosen_ranked.score:.3f} < {min_relevance_threshold})"

            # 5. Record provenance and licensing in attribution ledger
            ledger.record_clip(
                scene_index=scene_idx,
                candidate=chosen_candidate,
                selected_duration=scene.duration_seconds
            )

            provenance = {
                "clip_id": chosen_candidate.id,
                "provider": chosen_candidate.provider,
                "title": chosen_candidate.title,
                "source_page_url": chosen_candidate.source_page_url,
                "download_url": chosen_candidate.download_url,
                "preview_url": chosen_candidate.preview_url,
                "creator": chosen_candidate.creator,
                "creator_url": chosen_candidate.creator_url,
                "license_name": chosen_candidate.license_info.name,
                "license_url": chosen_candidate.license_info.url,
                "attribution_required": chosen_candidate.license_info.attribution_required,
                "attribution": f"'{chosen_candidate.title}' by {chosen_candidate.creator} ({chosen_candidate.license_info.name})",
                "usage_restrictions": chosen_candidate.usage_restrictions,
                "verification_status": chosen_candidate.verification_status,
                "verified": chosen_candidate.verified,
                "retrieval_timestamp_utc": chosen_candidate.retrieval_timestamp_utc
            }

            local_clip_path = getattr(chosen_candidate, "local_path", None)
            provenance["local_path"] = local_clip_path

            selected_clips.append(SelectedMediaClip(
                scene_index=scene_idx,
                candidate=chosen_candidate,
                relevance_score=chosen_ranked.score,
                selection_rank=rank_position,
                selection_reason=selection_reason,
                reasons=chosen_ranked.reasons,
                score_breakdown=chosen_ranked.breakdown.model_dump(),
                provenance=provenance,
                local_path=local_clip_path
            ))

            # 6. Update Scene with selected media metadata
            updated_scenes.append(Scene(
                narration=scene.narration,
                duration_seconds=scene.duration_seconds,
                visual_description=scene.visual_description,
                source_url=chosen_candidate.download_url,
                license_name=chosen_candidate.license_info.name,
                attribution=provenance["attribution"],
                media_metadata=MediaMetadata(
                    source_url=chosen_candidate.download_url,
                    license_name=chosen_candidate.license_info.name,
                    attribution=provenance["attribution"],
                    media_type="video",
                    verified=chosen_candidate.verified
                )
            ))

        # Batch parallel download of winning clips that need caching
        unique_to_dl = {}
        for clip in selected_clips:
            cand = clip.candidate
            if not getattr(cand, "local_path", None) and cand.download_url:
                cache_dir = settings.OUTPUT_DIR / "remote_cache"
                cached_file = cache_dir / f"{cand.id}.mp4"
                if cached_file.exists() and cached_file.stat().st_size > 10240:
                    cand.local_path = str(cached_file.resolve())
                    clip.local_path = cand.local_path
                    clip.provenance["local_path"] = cand.local_path
                elif cand.download_url.startswith("http") and "commons/demo" not in cand.download_url:
                    unique_to_dl[cand.id] = cand

        if unique_to_dl:
            from concurrent.futures import ThreadPoolExecutor
            logger.info(f"Downloading {len(unique_to_dl)} unique selected clips in parallel (max 6 workers)...")

            def _dl_one(c):
                prov = self.registry.get_provider(c.provider)
                if prov and hasattr(prov, "download_clip_to_cache"):
                    c.local_path = prov.download_clip_to_cache(c)
                elif c.download_url and c.download_url.startswith("http"):
                    cache_dir = settings.OUTPUT_DIR / "remote_cache"
                    cache_dir.mkdir(parents=True, exist_ok=True)
                    cached_file = cache_dir / f"{c.id}.mp4"
                    if not cached_file.exists() or cached_file.stat().st_size < 10240:
                        try:
                            import httpx
                            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) IncuBrix/1.0"}
                            with httpx.Client(timeout=settings.MEDIA_DOWNLOAD_TIMEOUT_SECONDS, follow_redirects=True, headers=headers) as dl_client:
                                with dl_client.stream("GET", c.download_url) as resp:
                                    if resp.status_code == 200:
                                        with open(cached_file, "wb") as f:
                                            for chunk in resp.iter_bytes(chunk_size=65536):
                                                f.write(chunk)
                        except Exception as exc:
                            logger.warning(f"Could not pre-download clip {c.id}: {exc}")
                    if cached_file.exists() and cached_file.stat().st_size > 10240:
                        c.local_path = str(cached_file.resolve())

            with ThreadPoolExecutor(max_workers=6) as executor:
                list(executor.map(_dl_one, unique_to_dl.values()))

            for clip in selected_clips:
                cand = clip.candidate
                if getattr(cand, "local_path", None):
                    clip.local_path = cand.local_path
                    clip.provenance["local_path"] = cand.local_path

        return SelectionResult(
            selected_clips=selected_clips,
            updated_scenes=updated_scenes,
            duplicate_clips_prevented=duplicate_prevented_count,
            attribution_ledger=ledger,
            total_scenes=len(scenes)
        )


media_selector = MediaSelector()
