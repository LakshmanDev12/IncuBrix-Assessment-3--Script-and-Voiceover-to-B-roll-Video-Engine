from unittest.mock import MagicMock
from fastapi.testclient import TestClient
import httpx
import pytest

from app.main import app
from app.services.providers import (
    AttributionLedger,
    LicenseInfo,
    LicenseValidator,
    LocalCC0ArchiveProvider,
    MediaCandidate,
    PexelsProvider,
    ProviderAuthError,
    ProviderNetworkError,
    ProviderRateLimitError,
    provider_registry,
)

client = TestClient(app)


def test_local_cc0_archive_search():
    provider = LocalCC0ArchiveProvider()
    assert provider.name == "local_cc0"
    assert provider.is_healthy() is True

    # Search for software / coding
    results = provider.search(query="software developer coding python", limit=5)
    assert len(results) >= 1
    top = results[0]
    assert "software" in top.tags or "developer" in top.tags
    assert top.source_page_url.startswith("https://commons.wikimedia.org")
    assert top.license_info.name == "CC0-1.0"
    assert top.verification_status == "verified"
    assert top.verified is True
    assert top.creator != ""
    assert top.duration_seconds > 0.0


def test_local_cc0_archive_aspect_ratio_filtering():
    provider = LocalCC0ArchiveProvider()

    # Search vertical 9:16 mobile clip
    results = provider.search(query="mobile phone vertical", aspect_ratio="9:16", limit=5)
    assert len(results) >= 1
    assert any(c.aspect_ratio == "9:16" for c in results)


def test_license_validator_permissible_licenses():
    # CC0-1.0
    cc0 = LicenseInfo(name="CC0-1.0", is_commercial_allowed=True, is_derivative_allowed=True)
    valid, status, reasons = LicenseValidator.validate_license(cc0)
    assert valid is True
    assert status == "verified"

    # Pexels License
    pexels_lic = LicenseInfo(name="Pexels License", is_commercial_allowed=True, is_derivative_allowed=True)
    valid_p, status_p, _ = LicenseValidator.validate_license(pexels_lic)
    assert valid_p is True
    assert status_p == "verified"

    # CC-BY-4.0
    cc_by = LicenseInfo(name="CC-BY-4.0", is_commercial_allowed=True, is_derivative_allowed=True, attribution_required=True)
    valid_by, status_by, _ = LicenseValidator.validate_license(cc_by)
    assert valid_by is True
    assert status_by == "verified"


def test_license_validator_rejects_incompatible_licenses():
    # No-Derivatives (ND) violates video composition
    cc_nd = LicenseInfo(name="CC-BY-ND-4.0", is_commercial_allowed=True, is_derivative_allowed=False)
    valid, status, reasons = LicenseValidator.validate_license(cc_nd)
    assert valid is False
    assert status == "incompatible_license"
    assert any("No-Derivatives" in r for r in reasons)

    # Non-Commercial for commercial job
    cc_nc = LicenseInfo(name="CC-BY-NC-4.0", is_commercial_allowed=False, is_derivative_allowed=True)
    valid_nc, status_nc, reasons_nc = LicenseValidator.validate_license(cc_nc, is_commercial_job=True)
    assert valid_nc is False
    assert status_nc == "incompatible_license"
    assert any("Non-Commercial" in r for r in reasons_nc)

    # All Rights Reserved / Unknown
    unknown_lic = LicenseInfo(name="All Rights Reserved", is_commercial_allowed=False, is_derivative_allowed=False)
    valid_u, status_u, _ = LicenseValidator.validate_license(unknown_lic)
    assert valid_u is False
    assert status_u == "incompatible_license"


def test_attribution_ledger_compilation():
    ledger = AttributionLedger(job_id="test_job_123")
    provider = LocalCC0ArchiveProvider()
    clip = provider.search(query="software coding")[0]

    ledger.record_clip(scene_index=1, candidate=clip, selected_duration=5.0)

    data = ledger.to_dict()
    assert data["job_id"] == "test_job_123"
    assert data["total_clips"] == 1
    assert data["verified_count"] == 1
    assert data["all_verified"] is True
    assert len(data["credits"]) == 1
    assert "Software Developer" in data["formatted_credit_roll"]
    assert clip.source_page_url in data["formatted_credit_roll"]


def test_pexels_provider_mock_successful_response():
    mock_client = MagicMock(spec=httpx.Client)

    # Mock Pexels search API JSON response
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "page": 1,
        "per_page": 1,
        "total_results": 1,
        "videos": [
            {
                "id": 855564,
                "width": 1920,
                "height": 1080,
                "duration": 15,
                "url": "https://www.pexels.com/video/people-coding-855564/",
                "image": "https://images.pexels.com/videos/855564/pictures/preview.jpg",
                "user": {"name": "Tech Videographer", "url": "https://www.pexels.com/@tech"},
                "video_files": [
                    {
                        "id": 1,
                        "quality": "hd",
                        "file_type": "video/mp4",
                        "width": 1920,
                        "height": 1080,
                        "fps": 30.0,
                        "link": "https://download.pexels.com/855564_1080p.mp4"
                    }
                ],
                "video_pictures": [
                    {"id": 1, "picture": "https://images.pexels.com/855564_thumb.jpg"}
                ]
            }
        ]
    }
    mock_client.get.return_value = mock_response

    provider = PexelsProvider(api_key="valid_dummy_key", client=mock_client)
    assert provider.name == "pexels"
    assert provider.is_healthy() is True

    results = provider.search(query="people coding", limit=1)
    assert len(results) == 1
    candidate = results[0]
    assert candidate.id == "pexels_855564"
    assert candidate.provider == "pexels"
    assert candidate.creator == "Tech Videographer"
    assert candidate.license_info.name == "Pexels License"
    assert candidate.source_page_url == "https://www.pexels.com/video/people-coding-855564/"
    assert candidate.download_url == "https://download.pexels.com/855564_1080p.mp4"
    assert candidate.verified is True


def test_pexels_provider_mock_rate_limit_error():
    mock_client = MagicMock(spec=httpx.Client)
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 429
    mock_response.headers = {"X-Ratelimit-Reset": "45"}
    mock_client.get.return_value = mock_response

    provider = PexelsProvider(api_key="valid_key", client=mock_client)
    with pytest.raises(ProviderRateLimitError) as exc_info:
        provider.search("nature")
    assert exc_info.value.retry_after_seconds == 45


def test_pexels_provider_mock_auth_error():
    mock_client = MagicMock(spec=httpx.Client)
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 401
    mock_client.get.return_value = mock_response

    provider = PexelsProvider(api_key="invalid_key", client=mock_client)
    with pytest.raises(ProviderAuthError):
        provider.search("mountains")


def test_pexels_provider_mock_network_error():
    mock_client = MagicMock(spec=httpx.Client)
    mock_client.get.side_effect = httpx.TimeoutException("Connection timed out")

    provider = PexelsProvider(api_key="valid_key", client=mock_client)
    with pytest.raises(ProviderNetworkError):
        provider.search("forest")


def test_pexels_provider_empty_key_gracefully_skips_when_remote_disabled():
    # Without remote providers enabled, empty key returns empty list without error
    provider = PexelsProvider(api_key="")
    assert provider.is_healthy() is False
    res = provider.search("anything")
    assert res == []


def test_provider_registry_listing_and_dispatch():
    providers = provider_registry.list_providers()
    assert len(providers) >= 2
    names = [p["name"] for p in providers]
    assert "local_cc0" in names
    assert "pexels" in names

    # Search local_cc0 via registry
    candidates = provider_registry.search(query="corporate presentation meeting", provider_name="local_cc0")
    assert len(candidates) >= 1
    assert candidates[0].verification_status == "verified"


def test_api_providers_endpoint():
    response = client.get("/v1/providers")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 2
    local_p = next(p for p in data if p["name"] == "local_cc0")
    assert local_p["is_healthy"] is True
    assert local_p["is_remote"] is False


def test_api_media_search_endpoint():
    response = client.get("/v1/media/search?query=waterfall%20forest&provider=local_cc0")
    assert response.status_code == 200
    data = response.json()
    assert data["provider"] == "local_cc0"
    assert data["count"] >= 1
    clip = data["candidates"][0]
    assert "waterfall" in clip["tags"] or "forest" in clip["tags"]
    assert clip["verification_status"] == "verified"
    assert clip["source_page_url"].startswith("http")
    assert clip["license_name"] == "CC0-1.0"


def test_api_media_search_endpoint_with_q_param():
    response = client.get("/v1/media/search?q=waterfall%20forest&provider=local_cc0")
    assert response.status_code == 200
    data = response.json()
    assert data["provider"] == "local_cc0"
    assert data["count"] >= 1

    # Also test count alias
    response2 = client.get("/v1/media/search?q=ocean&count=2")
    assert response2.status_code == 200
