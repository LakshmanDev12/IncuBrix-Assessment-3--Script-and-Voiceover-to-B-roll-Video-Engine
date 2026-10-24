from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.config import settings
from app.services.providers.base import LicenseInfo, MediaCandidate, VerificationStatus


class LicenseValidator:
    """
    Validates license permissions, flags incompatible restrictions (such as No-Derivatives or Non-Commercial),
    and assigns auditable verification statuses.
    """

    @staticmethod
    def validate_license(license_info: LicenseInfo, is_commercial_job: bool = True) -> Tuple[bool, VerificationStatus, List[str]]:
        """
        Validates if a given license permits use in the video composition pipeline.
        Returns: (is_permissible: bool, verification_status: VerificationStatus, reasons: List[str])
        """
        reasons: List[str] = []
        name = license_info.name.strip()
        upper_name = name.upper()

        # Rule 1: No-Derivatives is unconditionally prohibited
        # Video synthesis, trimming, and overlay constitute derivative works under copyright law
        if "ND" in upper_name or "NO-DERIVATIVES" in upper_name:
            reasons.append("Incompatible license: No-Derivatives (ND) prohibits video trimming, cropping, and stitching.")
            return False, "incompatible_license", reasons

        if not license_info.is_derivative_allowed:
            reasons.append("Incompatible license: Derivative works are not permitted by this media license.")
            return False, "incompatible_license", reasons

        # Rule 2: Non-Commercial restrictions
        if is_commercial_job and ("NC" in upper_name or "NON-COMMERCIAL" in upper_name or not license_info.is_commercial_allowed):
            reasons.append("Incompatible license: Non-Commercial (NC) restriction prohibits use in commercial video jobs.")
            return False, "incompatible_license", reasons

        # Rule 3: All Rights Reserved or Unspecified
        if upper_name in ("ALL RIGHTS RESERVED", "UNKNOWN", "UNSPECIFIED", "PROPRIETARY"):
            reasons.append(f"Incompatible license: '{name}' does not grant automated reproduction or distribution rights.")
            return False, "incompatible_license", reasons

        # Rule 4: Match against allowed licenses whitelist
        is_known_allowed = any(
            allowed.upper() in upper_name for allowed in settings.ALLOWED_LICENSES
        )

        if not is_known_allowed:
            reasons.append(f"Unverified license: '{name}' is not in the recognized lawful open license whitelist.")
            return False, "unverified", reasons

        reasons.append(f"Verified lawful license: '{name}' permits derivative composition and distribution.")
        return True, "verified", reasons


class AttributionLedger:
    """
    Tracks and compiles the provenance, attribution requirements, and legal verification
    for all media clips selected in a video render job.
    """

    def __init__(self, job_id: str):
        self.job_id = job_id
        self.entries: List[Dict[str, Any]] = []
        self.created_at_utc = datetime.now(timezone.utc).isoformat()

    def record_clip(
        self,
        scene_index: int,
        candidate: MediaCandidate,
        selected_duration: float
    ) -> Dict[str, Any]:
        """Records a selected clip into the attribution ledger."""
        entry = {
            "scene_index": scene_index,
            "clip_id": candidate.id,
            "provider": candidate.provider,
            "title": candidate.title,
            "creator": candidate.creator,
            "creator_url": candidate.creator_url,
            "source_page_url": candidate.source_page_url,
            "download_url": candidate.download_url,
            "license_name": candidate.license_info.name,
            "license_url": candidate.license_info.url,
            "attribution_required": candidate.license_info.attribution_required,
            "attribution_statement": self._format_attribution_statement(candidate),
            "usage_restrictions": candidate.usage_restrictions,
            "verification_status": candidate.verification_status,
            "verified": candidate.verified,
            "selected_duration_seconds": round(selected_duration, 3),
            "recorded_at_utc": datetime.now(timezone.utc).isoformat()
        }
        self.entries.append(entry)
        return entry

    def _format_attribution_statement(self, candidate: MediaCandidate) -> str:
        """Constructs a standard, publication-ready credit line."""
        creator_part = candidate.creator if candidate.creator else "Unknown Creator"
        return f"'{candidate.title}' by {creator_part} ({candidate.license_info.name}), via {candidate.provider}. Source: {candidate.source_page_url}"

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the complete attribution ledger."""
        total_clips = len(self.entries)
        verified_count = sum(1 for e in self.entries if e.get("verification_status") == "verified")
        attribution_needed = any(e.get("attribution_required") for e in self.entries)

        credits_summary = [e["attribution_statement"] for e in self.entries]

        return {
            "job_id": self.job_id,
            "total_clips": total_clips,
            "verified_count": verified_count,
            "all_verified": verified_count == total_clips if total_clips > 0 else True,
            "attribution_required": attribution_needed,
            "unique_licenses": list({e["license_name"] for e in self.entries}),
            "credits": self.entries,
            "formatted_credit_roll": "\n".join(credits_summary) if credits_summary else "No visual media clips."
        }
