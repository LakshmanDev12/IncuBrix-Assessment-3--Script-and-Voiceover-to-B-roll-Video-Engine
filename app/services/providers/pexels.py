from datetime import datetime, timezone
import logging
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

logger = logging.getLogger("video_engine.providers.pexels")


class PexelsProvider(BaseMediaProvider):
    """
    Lawful remote media provider integration with the official Pexels Video REST API.
    
    Adheres strictly to Pexels API Terms of Service, requires PEXELS_API_KEY,
    and applies Pexels License rules and usage restrictions.
    """

    SEARCH_URL = "https://api.pexels.com/videos/search"
    DETAIL_URL = "https://api.pexels.com/videos/videos/{id}"

    def __init__(self, api_key: Optional[str] = None, client: Optional[httpx.Client] = None):
        self.api_key = api_key if api_key is not None else settings.PEXELS_API_KEY
        self._client = client

    @property
    def name(self) -> str:
        return "pexels"

    @property
    def display_name(self) -> str:
        return "Pexels Video API"

    def is_healthy(self) -> bool:
        return bool(self.api_key and self.api_key.strip())

    def _get_client(self) -> httpx.Client:
        if self._client:
            return self._client
        return httpx.Client(timeout=settings.URL_FETCH_TIMEOUT_SECONDS)

    def search(
        self,
        query: str,
        target_duration: Optional[float] = None,
        aspect_ratio: Optional[str] = "16:9",
        limit: int = 10
    ) -> List[MediaCandidate]:
        if not self.api_key or not self.api_key.strip():
            if settings.ENABLE_REMOTE_PROVIDERS:
                raise ProviderAuthError("Pexels API key is not configured in environment variable PEXELS_API_KEY.")
            logger.info("Remote provider Pexels skipped: ENABLE_REMOTE_PROVIDERS is false or API key not set.")
            return []

        clean_query = query.strip()
        if not clean_query:
            return []

        # Map aspect ratio to Pexels orientation parameter: "landscape", "portrait", "square"
        orientation_map = {
            "16:9": "landscape",
            "9:16": "portrait",
            "1:1": "square"
        }
        orientation = orientation_map.get(aspect_ratio, "landscape")

        headers = {
            "Authorization": self.api_key.strip(),
            "User-Agent": "IncuBrix-Video-Broll-Engine/1.0"
        }
        params = {
            "query": clean_query,
            "per_page": min(limit * 2, 50),
            "orientation": orientation
        }

        client = self._get_client()
        try:
            response = client.get(self.SEARCH_URL, headers=headers, params=params)
        except httpx.TimeoutException as exc:
            raise ProviderNetworkError(f"Pexels API request timed out: {exc}")
        except httpx.RequestError as exc:
            raise ProviderNetworkError(f"Pexels API network connection error: {exc}")

        if response.status_code in (401, 403):
            raise ProviderAuthError("Pexels API authentication failed: invalid or unauthorized API key.")
        if response.status_code == 429:
            retry_after = response.headers.get("X-Ratelimit-Reset")
            retry_secs = int(retry_after) if retry_after and retry_after.isdigit() else 60
            raise ProviderRateLimitError("Pexels API rate limit quota exceeded.", retry_after_seconds=retry_secs)
        if response.status_code >= 500:
            raise ProviderNetworkError(f"Pexels API remote server error: HTTP {response.status_code}")
        if response.status_code != 200:
            raise ProviderError(f"Pexels API unexpected response: HTTP {response.status_code}", status_code=response.status_code)

        try:
            data = response.json()
        except Exception as exc:
            raise ProviderError(f"Malformed JSON response from Pexels API: {exc}")

        videos = data.get("videos", [])
        candidates: List[MediaCandidate] = []

        pexels_license = LicenseInfo(
            name="Pexels License",
            url="https://www.pexels.com/license/",
            is_commercial_allowed=True,
            is_derivative_allowed=True,
            attribution_required=False,
            restrictions=[
                "Identifiable people must not be portrayed in a bad light or offensively.",
                "Do not sell unaltered copies of photos or videos.",
                "Do not imply endorsement of your product by people or brands appearing in media."
            ]
        )

        for v in videos:
            candidate = self._parse_video_item(v, pexels_license, aspect_ratio)
            if candidate:
                candidates.append(candidate)
                if len(candidates) >= limit:
                    break

        return candidates

    def get_candidate_by_id(self, candidate_id: str) -> Optional[MediaCandidate]:
        if not self.api_key:
            return None

        # Strip prefix if present
        raw_id = candidate_id.replace("pexels_", "")
        url = self.DETAIL_URL.format(id=raw_id)
        headers = {"Authorization": self.api_key.strip()}

        client = self._get_client()
        try:
            resp = client.get(url, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                license_info = LicenseInfo(
                    name="Pexels License",
                    url="https://www.pexels.com/license/",
                    is_commercial_allowed=True,
                    is_derivative_allowed=True,
                    attribution_required=False
                )
                return self._parse_video_item(data, license_info, aspect_ratio="16:9")
        except Exception as exc:
            logger.warning(f"Failed to fetch Pexels video details for {candidate_id}: {exc}")

        return None

    def _parse_video_item(self, v: Dict[str, Any], license_info: LicenseInfo, aspect_ratio: Optional[str]) -> Optional[MediaCandidate]:
        video_id = v.get("id")
        if not video_id:
            return None

        duration = float(v.get("duration", 0.0))
        if duration <= 0.0:
            return None

        width = v.get("width", 1920)
        height = v.get("height", 1080)
        user = v.get("user", {})
        creator_name = user.get("name", "Pexels Contributor")
        creator_url = user.get("url")
        source_page_url = v.get("url", f"https://www.pexels.com/video/{video_id}/")

        # Pick best downloadable mp4 file (prefer HD/FHD)
        files = v.get("video_files", [])
        if not files:
            return None

        # Sort files to find best resolution <= 1080p
        mp4_files = [f for f in files if f.get("file_type") == "video/mp4" or "mp4" in str(f.get("link", ""))]
        if not mp4_files:
            mp4_files = files

        # Select file with highest height <= 1080
        mp4_files.sort(key=lambda f: (f.get("height") or 0), reverse=True)
        chosen_file = mp4_files[0]
        download_url = chosen_file.get("link")
        if not download_url:
            return None

        # Previews
        pictures = v.get("video_pictures", [])
        preview_url = pictures[0].get("picture") if pictures else None

        # Title and tags synthesized from URL slug or user metadata
        url_slug = source_page_url.rstrip("/").split("/")[-1].replace(f"-{video_id}", "").replace("-", " ")
        title = url_slug.capitalize() if url_slug and not url_slug.isdigit() else f"Pexels Video {video_id}"
        tags = [w.lower() for w in title.split() if len(w) > 2]

        # Determine aspect ratio
        calculated_aspect = "16:9"
        if height > width:
            calculated_aspect = "9:16"
        elif abs(width - height) < 50:
            calculated_aspect = "1:1"

        return MediaCandidate(
            id=f"pexels_{video_id}",
            provider="pexels",
            title=title,
            description=f"Stock video footage '{title}' contributed by {creator_name} on Pexels.",
            tags=tags,
            duration_seconds=round(duration, 2),
            aspect_ratio=calculated_aspect,
            width=chosen_file.get("width") or width,
            height=chosen_file.get("height") or height,
            fps=float(chosen_file.get("fps") or 30.0),
            source_page_url=source_page_url,
            download_url=download_url,
            preview_url=preview_url,
            creator=creator_name,
            creator_url=creator_url,
            license_info=license_info,
            usage_restrictions=license_info.restrictions,
            verification_status="verified",
            verified=True,
            retrieval_timestamp_utc=datetime.now(timezone.utc).isoformat()
        )
