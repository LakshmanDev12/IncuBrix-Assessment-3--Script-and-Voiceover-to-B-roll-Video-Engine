from datetime import datetime, timezone
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
import httpx

from app.config import settings
from app.services.providers.base import (
    BaseMediaProvider,
    LicenseInfo,
    MediaCandidate,
    ProviderAuthError,
    ProviderError,
    ProviderNetworkError,
    ProviderRateLimitError,
)

logger = logging.getLogger("video_engine.providers.pixabay")


class PixabayProvider(BaseMediaProvider):
    """
    Lawful remote media provider integration with the Pixabay Video REST API.
    
    Adheres strictly to Pixabay API Terms of Service, utilizes PIXABAY_API_KEY,
    and applies Pixabay License rules and usage restrictions (free for commercial
    and non-commercial use, no attribution required).
    """

    SEARCH_URL = "https://pixabay.com/api/videos/"

    def __init__(self, api_key: Optional[str] = None, client: Optional[httpx.Client] = None):
        self.api_key = (api_key or settings.PIXABAY_API_KEY).strip()
        self._client = client
        self._cache_dir = settings.OUTPUT_DIR / "remote_cache"
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._memory_cache: Dict[str, MediaCandidate] = {}
        self._search_cache: Dict[str, List[MediaCandidate]] = {}

    @property
    def name(self) -> str:
        return "pixabay"

    @property
    def display_name(self) -> str:
        return "Pixabay Video API"

    def is_healthy(self) -> bool:
        """Returns True if Pixabay API key is configured."""
        return bool(self.api_key and len(self.api_key) > 5)

    def _get_client(self) -> httpx.Client:
        if self._client:
            return self._client
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) IncuBrix/1.0"}
        return httpx.Client(timeout=settings.URL_FETCH_TIMEOUT_SECONDS, headers=headers)

    def download_clip_to_cache(self, candidate: MediaCandidate) -> Optional[str]:
        """Downloads video stream into persistent local cache so FFmpeg has a local file."""
        if not candidate.download_url:
            return None

        cached_file = self._cache_dir / f"{candidate.id}.mp4"
        if cached_file.exists() and cached_file.stat().st_size > 10240:
            candidate.local_path = str(cached_file.resolve())
            return candidate.local_path

        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        try:
            logger.info(f"Downloading Pixabay video to local cache: {candidate.id} ({candidate.title})")
            with httpx.Client(timeout=settings.MEDIA_DOWNLOAD_TIMEOUT_SECONDS, follow_redirects=True, headers=headers) as client:
                with client.stream("GET", candidate.download_url) as resp:
                    if resp.status_code == 200:
                        with open(cached_file, "wb") as f:
                            for chunk in resp.iter_bytes(chunk_size=65536):
                                f.write(chunk)
                        if cached_file.exists() and cached_file.stat().st_size > 10240:
                            candidate.local_path = str(cached_file.resolve())
                            logger.info(f"Successfully cached Pixabay video: {cached_file} ({cached_file.stat().st_size} bytes)")
                            return candidate.local_path
        except Exception as exc:
            logger.warning(f"Failed to pre-cache Pixabay clip {candidate.id}: {exc}")
            if cached_file.exists():
                try:
                    cached_file.unlink()
                except Exception:
                    pass
        return None

    def search(
        self,
        query: str,
        target_duration: Optional[float] = None,
        aspect_ratio: Optional[str] = "16:9",
        limit: int = 10
    ) -> List[MediaCandidate]:
        if not self.is_healthy():
            if settings.ENABLE_REMOTE_PROVIDERS:
                logger.warning("Pixabay provider skipped: PIXABAY_API_KEY not configured in environment.")
            return []

        # Sanitize and condense query to meet Pixabay API strict <=100 char requirement
        import re
        stripped = re.sub(r'^(visual showing|visual|representing:)\s*', '', query, flags=re.I)
        stripped = re.sub(r'representing:.*', '', stripped, flags=re.I)
        stripped = re.sub(r'[^a-zA-Z0-9\s]', ' ', stripped)
        stop_words = {
            'visual', 'showing', 'representing', 'video', 'footage', 'scene', 'shot',
            'beneath', 'across', 'lies', 'into', 'with', 'and', 'the', 'for', 'this', 'that', 'our', 'are', 'was', 'were'
        }
        words = [w.lower() for w in stripped.split() if w.lower() not in stop_words and len(w) > 2]
        clean_query = ' '.join(words[:4]) if words else query[:60]
        clean_query = clean_query[:90].strip()

        if not clean_query:
            clean_query = "ocean nature"

        cache_key = f"{clean_query}_{aspect_ratio}_{limit}"
        if cache_key in self._search_cache:
            return self._search_cache[cache_key]

        params = {
            "key": self.api_key,
            "q": clean_query,
            "video_type": "all",
            "per_page": min(max(limit * 2, 5), 50),
            "safesearch": "true"
        }

        client = self._get_client()
        try:
            response = client.get(self.SEARCH_URL, params=params)
            # If Pixabay returns 400 on query, retry with a single generic subject keyword
            if response.status_code == 400 and len(words) > 1:
                params["q"] = words[0]
                response = client.get(self.SEARCH_URL, params=params)
        except httpx.TimeoutException as exc:
            raise ProviderNetworkError(f"Pixabay API request timed out: {exc}")
        except httpx.RequestError as exc:
            raise ProviderNetworkError(f"Pixabay API network connection error: {exc}")

        if response.status_code in (401, 403):
            raise ProviderAuthError("Pixabay API authentication failed: invalid or unauthorized API key.")
        if response.status_code == 429:
            raise ProviderRateLimitError("Pixabay API rate limit quota exceeded.")
        if response.status_code >= 500:
            raise ProviderNetworkError(f"Pixabay API remote server error: HTTP {response.status_code}")
        if response.status_code != 200:
            raise ProviderError(f"Pixabay API unexpected response: HTTP {response.status_code}", status_code=response.status_code)

        try:
            data = response.json()
        except Exception as exc:
            raise ProviderError(f"Malformed JSON response from Pixabay API: {exc}")

        hits = data.get("hits", [])
        candidates: List[MediaCandidate] = []

        pixabay_license = LicenseInfo(
            name="Pixabay License",
            url="https://pixabay.com/service/license-summary/",
            is_commercial_allowed=True,
            is_derivative_allowed=True,
            attribution_required=False,
            restrictions=[
                "Do not sell unaltered copies of photos or videos.",
                "Do not imply endorsement of your product by people or brands appearing in media.",
                "Identifiable people may not appear in a bad light or offensive way."
            ]
        )

        for item in hits:
            cand = self._parse_hit(item, pixabay_license, aspect_ratio)
            if cand:
                # Reuse from local disk cache if already downloaded
                cached_file = self._cache_dir / f"{cand.id}.mp4"
                if cached_file.exists() and cached_file.stat().st_size > 10240:
                    cand.local_path = str(cached_file.resolve())

                candidates.append(cand)
                self._memory_cache[cand.id] = cand
                if len(candidates) >= limit:
                    break

        self._search_cache[cache_key] = candidates
        return candidates

    def get_candidate_by_id(self, candidate_id: str) -> Optional[MediaCandidate]:
        if candidate_id in self._memory_cache:
            cand = self._memory_cache[candidate_id]
            if not cand.local_path:
                self.download_clip_to_cache(cand)
            return cand

        if not self.is_healthy():
            return None

        raw_id = candidate_id.replace("pixabay_", "")
        client = self._get_client()
        try:
            resp = client.get(self.SEARCH_URL, params={"key": self.api_key, "id": raw_id})
            if resp.status_code == 200:
                hits = resp.json().get("hits", [])
                if hits:
                    pixabay_license = LicenseInfo(
                        name="Pixabay License",
                        url="https://pixabay.com/service/license-summary/",
                        is_commercial_allowed=True,
                        is_derivative_allowed=True,
                        attribution_required=False
                    )
                    cand = self._parse_hit(hits[0], pixabay_license, aspect_ratio="16:9")
                    if cand:
                        self.download_clip_to_cache(cand)
                        self._memory_cache[cand.id] = cand
                        return cand
        except Exception as exc:
            logger.warning(f"Failed to fetch Pixabay video details for {candidate_id}: {exc}")

        return None

    def _parse_hit(
        self,
        item: Dict[str, Any],
        license_info: LicenseInfo,
        aspect_ratio: Optional[str]
    ) -> Optional[MediaCandidate]:
        vid_id = item.get("id")
        if not vid_id:
            return None

        duration = float(item.get("duration", 0.0))
        if duration <= 0.0:
            return None

        videos = item.get("videos", {})
        # Prefer medium (1280x720 / 1920x1080 optimized download size) -> large -> small
        chosen_variant = videos.get("medium") or videos.get("large") or videos.get("small")
        if not chosen_variant or not chosen_variant.get("url"):
            return None

        download_url = chosen_variant.get("url")
        width = int(chosen_variant.get("width") or 1920)
        height = int(chosen_variant.get("height") or 1080)

        # Tags and Title
        raw_tags = item.get("tags", "")
        tag_list = [t.strip().lower() for t in raw_tags.split(",") if t.strip()]
        title = (" ".join(tag_list[:4])).title() if tag_list else f"Pixabay Video {vid_id}"

        # Creator
        creator = item.get("user", "Pixabay Contributor")
        creator_url = f"https://pixabay.com/users/{item.get('user', '')}-{item.get('user_id', '')}/"
        source_page_url = item.get("pageURL", f"https://pixabay.com/videos/id-{vid_id}/")

        # Preview thumbnail
        preview_url = (
            chosen_variant.get("thumbnail")
            or videos.get("tiny", {}).get("thumbnail")
            or f"https://i.vimeocdn.com/video/{item.get('picture_id')}_640x360.jpg"
        )

        # Aspect ratio
        calculated_aspect = "16:9"
        if height > width:
            calculated_aspect = "9:16"
        elif abs(width - height) < 50:
            calculated_aspect = "1:1"

        cached_file = self._cache_dir / f"pixabay_{vid_id}.mp4"
        local_path = str(cached_file.resolve()) if (cached_file.exists() and cached_file.stat().st_size > 10240) else None

        return MediaCandidate(
            id=f"pixabay_{vid_id}",
            provider="pixabay",
            title=title,
            description=f"Stock video footage '{title}' by {creator} on Pixabay.",
            tags=tag_list,
            duration_seconds=round(duration, 2),
            aspect_ratio=calculated_aspect,
            width=width,
            height=height,
            fps=30.0,
            source_page_url=source_page_url,
            download_url=download_url,
            local_path=local_path,
            preview_url=preview_url,
            creator=creator,
            creator_url=creator_url,
            license_info=license_info,
            usage_restrictions=license_info.restrictions,
            verification_status="verified",
            verified=True,
            retrieval_timestamp_utc=datetime.now(timezone.utc).isoformat()
        )
