# Lawful Media Sources & Licensing Ledger Specification

This document establishes the verified media sources, access requirements, licensing constraints, and legal compliance rules enforced by the **Script and Voiceover to B-roll Video Engine**.

---

## 1. Compliance Principles & Ethical Access Rules

1. **No Scraping or Access Bypass:** The engine accesses third-party media **exclusively through documented, authorized REST APIs** or local curated repositories. It never executes web scraping, HTML parsing of unauthenticated pages, CAPTCHA circumvention, or paywall bypass.
2. **Explicit License Verification Required:** A provider name, platform brand, or public URL is **never treated as inherent proof of a license**. Every candidate media asset must possess explicit license metadata, identifiable author/creator attribution, and a canonical source page URL.
3. **Audit Trail & Provenance Storage:** For every media clip retrieved and selected for video synthesis, the engine records an immutable provenance record:
   - Canonical source page URL
   - Direct download URL and preview thumbnail
   - Creator / artist name and profile link
   - License identifier (e.g., `CC0-1.0`, `Pexels License`, `CC-BY-4.0`)
   - Mandatory attribution statement
   - Retrieval timestamp (UTC ISO-8601)
   - Verification status (`verified`, `unverified`, `incompatible_license`, `revoked`)

---

## 2. Verified Media Sources

### Provider 1: Local Verified CC0 Archive (`local_cc0`)
- **Status:** **Active / Fully Verified (Offline Baseline)**
- **Source Repositories:** Curated public domain and CC0 media from Wikimedia Commons, NASA, US National Park Service, and open cultural archives.
- **Access Protocol:** Local directory storage and embedded catalog index. Zero external API calls required.
- **License:** **Creative Commons Zero 1.0 Universal (`CC0-1.0`)** and **Public Domain Mark 1.0**.
- **Commercial Use:** Allowed without restriction.
- **Modification & Derivative Works:** Unconditionally permitted.
- **Attribution Policy:** Not legally required under CC0; however, creator and institution attribution are recorded in the engine's Attribution Ledger as an ethical best practice.

### Provider 2: Pexels Video API (`pexels`)
- **Status:** **Active (Conditional on `PEXELS_API_KEY`)**
- **Official Documentation:** [Pexels API Documentation](https://www.pexels.com/api/documentation/)
- **License Terms:** [Pexels License Terms](https://www.pexels.com/license/)
- **Access Requirements:** Requires a registered API Key supplied via the `Authorization` HTTP header. Keys must be stored in the `PEXELS_API_KEY` environment variable.
- **Default Rate Limits:** 200 requests/hour; 20,000 requests/month on free tiers. The engine includes backoff and rate-limit handling for `HTTP 429`.
- **Permitted Usage:**
  - Free for commercial and non-commercial projects.
  - Video editing, stitching, trimming, and B-roll overlay are explicitly permitted.
- **Usage Restrictions (Enforced via Metadata):**
  - Identifiable people must not appear in a bad light or in a way that is offensive.
  - Do not sell unaltered copies of a photo or video (e.g. sell it as a standalone stock video).
  - Do not imply endorsement of your product by people or brands on the imagery.
- **Attribution:** Attribution is not legally required by Pexels, but the creator's name and Pexels URL are logged into the Attribution Ledger.

---

## 3. License Compatibility Matrix

The engine's `LicenseValidator` enforces the following compatibility rules for video composition:

| License | Status | Commercial Allowed | Derivatives Allowed | Attribution Required | Engine Action |
|---|---|---|---|---|---|
| **CC0-1.0 / Public Domain** | **COMPATIBLE** | Yes | Yes | No (Recommended) | Auto-approved; verified. |
| **Pexels License** | **COMPATIBLE** | Yes | Yes | No (Recommended) | Auto-approved; verified. |
| **Pixabay License** | **COMPATIBLE** | Yes | Yes | No (Recommended) | Auto-approved; verified. |
| **CC-BY-4.0 / 3.0** | **COMPATIBLE** | Yes | Yes | **YES (Mandatory)** | Approved; credit required in manifest & captions. |
| **CC-BY-SA-4.0** | **RESTRICTED** | Yes | Yes (Copyleft) | **YES** | Flagged. Requires resulting video to be released under CC-BY-SA. |
| **CC-BY-NC-4.0** | **INCOMPATIBLE** | **NO** | Yes | **YES** | Rejected for commercial jobs. Permitted only if non-commercial flag is explicitly set. |
| **CC-BY-ND-4.0** | **PROHIBITED** | Yes | **NO** | **YES** | **Strictly Rejected.** Video stitching and editing creates a derivative work, violating No-Derivatives licenses. |
| **All Rights Reserved** | **PROHIBITED** | No | No | N/A | **Strictly Rejected.** |
| **Unknown / Unspecified**| **PROHIBITED** | Unknown | Unknown | Unknown | **Strictly Rejected.** Flagged as `unverified` with rendering blocked. |

---

## 4. Attribution Ledger in Artifact Deliverables

Every completed video job generates an `attribution_ledger.json` (also embedded in `timeline.json` and `manifest.json`) detailing all visual assets used:

```json
{
  "total_clips": 3,
  "verified_count": 3,
  "licenses": ["CC0-1.0", "Pexels License"],
  "attribution_required": false,
  "credits": [
    {
      "scene_index": 1,
      "clip_id": "cc0_office_coding",
      "title": "Software Developer Coding at Desk",
      "creator": "Wikimedia Commons / US Public Domain Archive",
      "source_page_url": "https://commons.wikimedia.org/wiki/File:Software_developer_working.webm",
      "license_name": "CC0-1.0",
      "verification_status": "verified"
    }
  ],
  "formatted_credit_roll": "Video 1: 'Software Developer Coding at Desk' by US Public Domain Archive (CC0-1.0)"
}
```

---

## 5. Software Dependencies & Open Source Licensing

The engine utilizes open-source libraries and utilities licensed under permissive, business-friendly terms:

| Dependency | Purpose | Version Constraint | License | Notice / Attribution |
|---|---|---|---|---|
| **Python** | Runtime Environment | `3.12+` / `3.13` | PSF License | Python Software Foundation |
| **FastAPI** | REST API & Documentation | `>=0.115,<1.0` | MIT License | Copyright (c) Sebastián Ramírez |
| **Pydantic** | Schema Validation & Serialization | `>=2.8,<3.0` | MIT License | Copyright (c) Samuel Colvin |
| **SQLAlchemy** | Database ORM & Persistence | `>=2.0,<3.0` | MIT License | Copyright (c) Michael Bayer |
| **Starlette** | ASGI Toolkit & Middleware | `>=0.38` | BSD-3-Clause | Copyright (c) Encode OSS Ltd |
| **HTTPX** | Async & Sync HTTP Client | `>=0.27` | BSD-3-Clause | Copyright (c) Encode OSS Ltd |
| **Uvicorn** | ASGI Web Server | `>=0.30,<1.0` | BSD-3-Clause | Copyright (c) Encode OSS Ltd |
| **python-multipart**| Streaming Multipart File Uploads | `>=0.0.9` | Apache-2.0 | Copyright (c) Andrew Gallagher |
| **pytest** | Test Framework | `>=8.0` | MIT License | Copyright (c) Holger Krekel and others |
| **FFmpeg / FFprobe**| Video Encoding & Stream Verification | `9.0.1` / `6.0+` | LGPL v2.1+ | Copyright (c) the FFmpeg developers |

FFmpeg binaries are invoked externally as independent subprocesses, complying strictly with LGPL dynamic execution guidelines without linking proprietary code into the FFmpeg binary itself.

