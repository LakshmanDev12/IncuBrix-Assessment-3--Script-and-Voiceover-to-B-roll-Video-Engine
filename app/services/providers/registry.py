import logging
from typing import Any, Dict, List, Optional

from app.config import settings
from app.services.providers.base import BaseMediaProvider, MediaCandidate
from app.services.providers.license_ledger import LicenseValidator
from app.services.providers.local_archive import LocalCC0ArchiveProvider
from app.services.providers.pexels import PexelsProvider
from app.services.providers.pixabay import PixabayProvider

logger = logging.getLogger("video_engine.providers.registry")


class MediaProviderRegistry:
    """
    Central registry and dispatcher for lawful media providers.
    
    Coordinates search queries across local and remote sources, validates licensing
    and rights compliance, and filters out unverified or incompatible media assets.
    """

    def __init__(self):
        self._providers: Dict[str, BaseMediaProvider] = {}
        self._register_default_providers()

    def _register_default_providers(self):
        # Register local verified CC0 catalog (always active, zero external dependency)
        self.register(LocalCC0ArchiveProvider())

        # Register Pexels provider
        self.register(PexelsProvider())
        self.register(PixabayProvider())

    def register(self, provider: BaseMediaProvider):
        """Registers a media provider adapter."""
        self._providers[provider.name] = provider
        logger.info(f"Registered media provider: '{provider.name}' ({provider.display_name})")

    def get_provider(self, name: str) -> Optional[BaseMediaProvider]:
        return self._providers.get(name)

    def list_providers(self) -> List[Dict[str, Any]]:
        """Returns metadata and health status for all registered providers."""
        return [
            {
                "name": p.name,
                "display_name": p.display_name,
                "is_healthy": p.is_healthy(),
                "is_remote": p.name != "local_cc0"
            }
            for p in self._providers.values()
        ]

    def search(
        self,
        query: str,
        provider_name: Optional[str] = None,
        target_duration: Optional[float] = None,
        aspect_ratio: Optional[str] = "16:9",
        limit: int = 10,
        require_verified: bool = True
    ) -> List[MediaCandidate]:
        """
        Searches one or all active providers, validates candidate licenses,
        and returns compliant candidates.
        """
        target_provider = provider_name or settings.DEFAULT_MEDIA_PROVIDER

        candidates: List[MediaCandidate] = []

        if target_provider in self._providers and target_provider != "composite":
            provider = self._providers[target_provider]
            try:
                candidates = provider.search(
                    query=query,
                    target_duration=target_duration,
                    aspect_ratio=aspect_ratio,
                    limit=limit
                )
            except Exception as exc:
                logger.error(f"Error querying provider '{target_provider}': {exc}")

            if not candidates and target_provider != "local_cc0":
                logger.info(f"Provider '{target_provider}' returned 0 results. Falling back to local_cc0 provider.")
                local_p = self._providers.get("local_cc0")
                if local_p:
                    candidates = local_p.search(query, target_duration, aspect_ratio, limit)
        else:
            # Composite search: query local first, then remote if healthy
            local_p = self._providers.get("local_cc0")
            if local_p:
                candidates.extend(local_p.search(query, target_duration, aspect_ratio, limit))

            remote_p = self._providers.get("pexels")
            if remote_p and remote_p.is_healthy() and settings.ENABLE_REMOTE_PROVIDERS:
                try:
                    remote_candidates = remote_p.search(query, target_duration, aspect_ratio, limit)
                    candidates.extend(remote_candidates)
                except Exception as exc:
                    logger.warning(f"Composite search remote query failed: {exc}")

        # Rights and License Verification Filter
        compliant_candidates: List[MediaCandidate] = []
        for cand in candidates:
            is_valid, status, reasons = LicenseValidator.validate_license(cand.license_info)
            cand.verification_status = status
            cand.verified = (status == "verified")

            if require_verified and not cand.verified:
                logger.warning(f"Candidate '{cand.id}' rejected due to license issues: {reasons}")
                continue

            compliant_candidates.append(cand)

        # Deduplicate candidates by ID while preserving order
        seen_ids = set()
        deduped = []
        for c in compliant_candidates:
            if c.id not in seen_ids:
                seen_ids.add(c.id)
                deduped.append(c)
                if len(deduped) >= limit:
                    break

        return deduped


provider_registry = MediaProviderRegistry()
