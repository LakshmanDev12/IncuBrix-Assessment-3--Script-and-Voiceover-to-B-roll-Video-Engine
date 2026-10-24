import base64
import hashlib
import logging
from pathlib import Path
import re
from typing import Dict, List, Optional
import httpx

from app.config import settings
from app.services.providers.base import (
    BaseMediaProvider,
    LicenseInfo,
    MediaCandidate,
    ProviderNetworkError,
)

logger = logging.getLogger("video_engine.providers.ai_generator")


class AIGeneratedMediaProvider(BaseMediaProvider):
    """
    Lawful AI Video Generation Provider utilizing CogVideoX-2B.
    
    Connects to a Colab, local GPU, or self-hosted inference endpoint running
    CogVideoX-2B text-to-video diffusion pipeline. Automatically caches generated
    MP4 clips locally, validates output, and provides fallback resilience if the
    inference service is temporarily unavailable.
    """

    def __init__(self, base_url: Optional[str] = None):
        self.base_url = (base_url or settings.AI_VIDEO_GENERATOR_URL).rstrip("/")
        self.timeout = settings.AI_GENERATOR_TIMEOUT_SECONDS
        self._cache_dir = settings.OUTPUT_DIR / "ai_cache"
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._memory_cache: Dict[str, MediaCandidate] = {}

    @property
    def name(self) -> str:
        return "ai_generated"

    @property
    def display_name(self) -> str:
        return "AI Video Generator (CogVideoX-2B)"

    def is_healthy(self) -> bool:
        """
        Polls the AI generator endpoint's /health route.
        Returns False if unreachable, timed out, or disabled in settings.
        """
        if not settings.ENABLE_AI_GENERATOR or not self.base_url:
            return False

        try:
            with httpx.Client(timeout=2.0) as client:
                res = client.get(f"{self.base_url}/health")
                return res.status_code == 200
        except Exception as exc:
            logger.debug(f"AI generator health check failed ({self.base_url}): {exc}")
            return False

    def get_candidate_by_id(self, candidate_id: str) -> Optional[MediaCandidate]:
        return self._memory_cache.get(candidate_id)

    def search(
        self,
        query: str,
        target_duration: Optional[float] = None,
        aspect_ratio: Optional[str] = "16:9",
        limit: int = 10
    ) -> List[MediaCandidate]:
        """
        Generates or retrieves a cached AI video matching the prompt query.
        Falls back gracefully if the endpoint is offline.
        """
        if not query or not query.strip():
            return []

        cleaned_prompt = query.strip()
        aspect = aspect_ratio or "16:9"
        duration = float(target_duration or 4.0)

        # Cache key based on cleaned prompt and aspect ratio
        cache_key = f"{cleaned_prompt.lower()}_{aspect}_{duration:.1f}"
        hash_digest = hashlib.sha256(cache_key.encode("utf-8")).hexdigest()[:16]
        cached_file = self._cache_dir / f"ai_{hash_digest}.mp4"
        candidate_id = f"ai_cogvideox_{hash_digest}"

        # 1. Return immediately if already cached on disk and in memory
        if cached_file.exists() and cached_file.stat().st_size > 1024:
            if candidate_id in self._memory_cache:
                return [self._memory_cache[candidate_id]]
            candidate = self._build_candidate(
                candidate_id=candidate_id,
                prompt=cleaned_prompt,
                aspect_ratio=aspect,
                duration=duration,
                local_file=cached_file
            )
            self._memory_cache[candidate_id] = candidate
            return [candidate]

        # 2. Check endpoint availability
        if not self.is_healthy():
            logger.info(
                f"AI Video Generator ({self.base_url}) is offline or unconfigured. "
                "Skipping AI generation candidate."
            )
            return []

        # 3. Request generation from Colab / CogVideoX service
        logger.info(f"Submitting prompt to AI Video Generator: '{cleaned_prompt[:60]}...'")
        try:
            with httpx.Client(timeout=self.timeout) as client:
                payload = {
                    "prompt": cleaned_prompt,
                    "aspect_ratio": aspect,
                    "duration_seconds": duration,
                    "num_inference_steps": 30,
                    "guidance_scale": 6.0
                }
                response = client.post(f"{self.base_url}/generate", json=payload)
                
                if response.status_code != 200:
                    logger.warning(
                        f"AI generation endpoint returned status {response.status_code}: {response.text[:200]}"
                    )
                    return []

                content_type = response.headers.get("content-type", "")

                # Handle direct binary MP4 stream
                if "video" in content_type or "octet-stream" in content_type or response.content.startswith(b"\x00\x00\x00"):
                    with open(cached_file, "wb") as f:
                        f.write(response.content)
                else:
                    # Handle JSON response format
                    data = response.json()
                    if "video_base64" in data:
                        video_bytes = base64.b64decode(data["video_base64"])
                        with open(cached_file, "wb") as f:
                            f.write(video_bytes)
                    elif "video_url" in data:
                        video_url = data["video_url"]
                        if video_url.startswith("/"):
                            video_url = f"{self.base_url}{video_url}"
                        dl_res = client.get(video_url)
                        if dl_res.status_code == 200:
                            with open(cached_file, "wb") as f:
                                f.write(dl_res.content)
                        else:
                            logger.error(f"Failed to download video from {video_url}")
                            return []
                    else:
                        logger.error(f"Unrecognized response format from AI generator: {data}")
                        return []

        except httpx.TimeoutException:
            logger.warning(f"AI generation timed out after {self.timeout}s for prompt '{cleaned_prompt[:40]}'.")
            return []
        except Exception as exc:
            logger.error(f"AI generation network call failed: {exc}")
            return []

        # 4. Build and return candidate
        if cached_file.exists() and cached_file.stat().st_size > 1024:
            candidate = self._build_candidate(
                candidate_id=candidate_id,
                prompt=cleaned_prompt,
                aspect_ratio=aspect,
                duration=duration,
                local_file=cached_file
            )
            self._memory_cache[candidate_id] = candidate
            return [candidate]

        return []

    def _build_candidate(
        self,
        candidate_id: str,
        prompt: str,
        aspect_ratio: str,
        duration: float,
        local_file: Path
    ) -> MediaCandidate:
        dims = settings.ASPECT_RATIOS.get(aspect_ratio, (1920, 1080))
        terms = re.findall(r"\b[a-zA-Z0-9_-]+\b", prompt.lower())
        tags = ["ai_generated", "cogvideox", "synthetic", *terms[:8]]

        ai_license = LicenseInfo(
            name="CC0-1.0",
            url="https://creativecommons.org/publicdomain/zero/1.0/",
            is_commercial_allowed=True,
            is_derivative_allowed=True,
            attribution_required=False,
            restrictions=["Open Source AI Synthetic Generation; permissive usage."]
        )

        return MediaCandidate(
            id=candidate_id,
            provider="ai_generated",
            title=f"AI Generated: {prompt[:40]}",
            description=f"AI-synthesized B-roll clip via CogVideoX-2B for prompt: '{prompt}'",
            tags=tags,
            duration_seconds=duration,
            aspect_ratio=aspect_ratio,
            width=dims[0],
            height=dims[1],
            fps=30.0,
            source_page_url=self.base_url,
            download_url=str(local_file.resolve()),
            local_path=str(local_file.resolve()),
            preview_url=None,
            creator="CogVideoX-2B Model (THUDM)",
            creator_url="https://huggingface.co/THUDM/CogVideoX-2b",
            license_info=ai_license,
            usage_restrictions=["Synthetic Media - Permissive Commercial Use"],
            verification_status="verified",
            verified=True
        )
