from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

VerificationStatus = Literal["verified", "unverified", "incompatible_license", "revoked"]


class ProviderError(Exception):
    """Base exception for media provider operations."""
    def __init__(self, message: str, code: str = "PROVIDER_ERROR", status_code: int = 500):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


class ProviderAuthError(ProviderError):
    """Raised when provider credentials are missing, invalid, or expired."""
    def __init__(self, message: str = "Provider authentication failed or API key missing."):
        super().__init__(message, code="PROVIDER_AUTH_ERROR", status_code=401)


class ProviderRateLimitError(ProviderError):
    """Raised when a provider's rate limit quota is exceeded."""
    def __init__(self, message: str = "Provider rate limit quota exceeded.", retry_after_seconds: Optional[int] = None):
        super().__init__(message, code="PROVIDER_RATE_LIMIT", status_code=429)
        self.retry_after_seconds = retry_after_seconds


class ProviderNetworkError(ProviderError):
    """Raised on network timeouts or connectivity failures."""
    def __init__(self, message: str = "Provider network request failed."):
        super().__init__(message, code="PROVIDER_NETWORK_ERROR", status_code=502)


@dataclass
class LicenseInfo:
    name: str
    url: Optional[str] = None
    is_commercial_allowed: bool = True
    is_derivative_allowed: bool = True
    attribution_required: bool = False
    restrictions: List[str] = field(default_factory=list)


@dataclass
class MediaCandidate:
    id: str
    provider: str
    title: str
    description: str
    tags: List[str]
    duration_seconds: float
    aspect_ratio: str  # "16:9", "9:16", "1:1"
    width: int
    height: int
    fps: float
    source_page_url: str
    download_url: str
    preview_url: Optional[str]
    creator: str
    creator_url: Optional[str]
    license_info: LicenseInfo
    usage_restrictions: List[str] = field(default_factory=list)
    verification_status: VerificationStatus = "verified"
    verified: bool = True
    local_path: Optional[str] = None
    retrieval_timestamp_utc: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "provider": self.provider,
            "title": self.title,
            "description": self.description,
            "tags": self.tags,
            "duration_seconds": self.duration_seconds,
            "aspect_ratio": self.aspect_ratio,
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "source_page_url": self.source_page_url,
            "download_url": self.download_url,
            "local_path": self.local_path,
            "preview_url": self.preview_url,
            "creator": self.creator,
            "creator_url": self.creator_url,
            "license_name": self.license_info.name,
            "license_url": self.license_info.url,
            "attribution_required": self.license_info.attribution_required,
            "usage_restrictions": self.usage_restrictions,
            "verification_status": self.verification_status,
            "verified": self.verified,
            "retrieval_timestamp_utc": self.retrieval_timestamp_utc,
        }


class BaseMediaProvider(ABC):
    """Common interface for lawful B-roll media providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this provider (e.g. 'local_cc0', 'pexels')."""
        pass

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable provider name."""
        pass

    @abstractmethod
    def search(
        self,
        query: str,
        target_duration: Optional[float] = None,
        aspect_ratio: Optional[str] = "16:9",
        limit: int = 10
    ) -> List[MediaCandidate]:
        """Searches the provider for visual media candidates matching the query."""
        pass

    @abstractmethod
    def get_candidate_by_id(self, candidate_id: str) -> Optional[MediaCandidate]:
        """Retrieves a specific media candidate by its identifier."""
        pass

    @abstractmethod
    def is_healthy(self) -> bool:
        """Checks if the provider is currently operational and properly configured."""
        pass
