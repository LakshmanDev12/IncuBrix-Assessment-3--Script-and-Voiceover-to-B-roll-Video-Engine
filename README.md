<div align="center">

# 🎬 Vk-Media IncuBrix Video B-Roll Engine

### *Autonomous Script-to-Video Engine • Neural Voiceover • Semantic B-Roll Synthesis • Split-Screen Studio*

---

[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3.12%20%7C%203.13-3776AB.svg?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Docker](https://img.shields.io/badge/Docker-Compose%20v2-2496ED.svg?style=for-the-badge&logo=docker&logoColor=white)](https://www.docker.com/)
[![FFmpeg](https://img.shields.io/badge/FFmpeg-6.0+%20%7C%209.0.1+-007808.svg?style=for-the-badge&logo=ffmpeg&logoColor=white)](https://ffmpeg.org)
[![Edge-TTS](https://img.shields.io/badge/Edge--TTS-Neural%20Voices-blueviolet.svg?style=for-the-badge&logo=microsoft&logoColor=white)](https://github.com/rany2/edge-tts)
[![Tests](https://img.shields.io/badge/Tests-155%20Passed-success.svg?style=for-the-badge&logo=pytest&logoColor=white)](tests)
[![License](https://img.shields.io/badge/License-MIT-amber.svg?style=for-the-badge)](LICENSE)

<br/>

[✨ Features](#-key-features) •
[⚡ Quick Start](#-quick-start) •
[🖥️ Studio Walkthrough](#-vk-media-studio-split-screen-ui) •
[🏗️ Architecture](#️-system-architecture) •
[🔌 REST API Reference](#-rest-api-reference) •
[⚙️ Configuration](#-configuration--environment-variables) •
[🧪 Testing & Verification](#-testing--quality-gate)

</div>

---

## 🌟 Overview

**Vk-Media IncuBrix Video B-Roll Engine** is an industrial-strength, deterministic video generation platform. It converts raw narrative scripts, topics, and voiceovers into broadcast-grade 1080p MP4 videos complete with synchronized B-roll footage, burned-in subtitles, frame-accurate cut points, and cryptographic provenance manifests.

Whether driven via its modern **Split-Screen Web Studio** or integrated headlessly via **FastAPI REST endpoints**, the engine orchestrates neural text-to-speech, semantic footage matching across local and remote repositories, and hardened FFmpeg conforming pipelines with zero-drop word preservation and strict quality assurance.

```
                   ┌─────────────────────────────────────────────────────────┐
                   │               Input Script or Narration Audio           │
                   └────────────────────────────┬────────────────────────────┘
                                                │
                                    [Clause-Aware Splitter]
                                                │
                                                ▼
                   ┌─────────────────────────────────────────────────────────┐
                   │        Scene 1        │    Scene 2   │     Scene 3      │
                   └───────┬──────────────────────┬──────────────────┬───────┘
                           │                      │                  │
               [Edge-TTS / Audio Sync]    [Semantic Match]   [Conforming Engine]
                           │                      │                  │
                           └──────────────────────┼──────────────────┘
                                                  ▼
                   ┌─────────────────────────────────────────────────────────┐
                   │             FFmpeg 1080p Render Pipeline                │
                   │    - Zero-Distortion Center Crop & Aspect Conforming    │
                   │    - Seamless Loop Safeguards (-stream_loop -1)         │
                   │    - Subtitle Stamping & Dynamic Audio Multiplexing     │
                   └────────────────────────────┬────────────────────────────┘
                                                │
                                       [FFprobe Gate: PASS]
                                                │
                                                ▼
                   ┌─────────────────────────────────────────────────────────┐
                   │    🎥 video.mp4  •  📝 captions.srt  •  📜 manifest.json │
                   └─────────────────────────────────────────────────────────┘
```

---

## ✨ Key Features

| Capability | Technical Implementation | Value |
| :--- | :--- | :--- |
| 🖥️ **Split-Screen Studio** | Responsive dual-pane UI (Prompt & Scene Editor on left, Real-time Synced Video Player on right). | Instant preview and iterative script tweaking without context switching. |
| ✂️ **Automatic Scene Splitting** | Clause-boundary tokenization with abbreviation protection (`Dr.`, `U.S.`) and 100% word-preservation validation. | Raw script text is automatically converted into paced visual beats upon generation. |
| 🎙️ **Edge-TTS Neural Voiceover** | Multi-voice neural speech synthesis (`Christopher`, `Jenny`, `Guy`) with automatic duration pacing. | Broadcast-quality narration generated out-of-the-box without requiring external paid speech APIs. |
| 🎞️ **Multi-Tier B-Roll Sourcing** | Semantic scoring combining n-gram token overlap, TF-IDF cosine similarity, aspect-ratio fit, and negative keyword penalties. | Automatically matches scene narratives to verified offline CC0 archives, Pixabay, or Pexels. |
| 🛡️ **Hardened Media Pipelines** | Magic-byte binary inspection, SSRF subnet protection, and mandatory post-render FFprobe quality gate. | Complete protection against malicious payloads and rendering corruptions. |
| ⚡ **Resilient Async Job Store** | SQLite WAL-mode persistence with an in-process asynchronous queue worker and automatic crash recovery. | Safe execution under workload bursts with idempotent retries and job status tracking. |
| 📐 **Multi-Aspect Ratio Conforming** | Center-cropped and padded rendering for Landscape (16:9), Vertical/Shorts (9:16), and Square (1:1). | Single-click export for YouTube, TikTok, Instagram Reels, and web presentations. |

---

## ⚡ Quick Start

### Option A: Docker Compose (Recommended)

Get both the **FastAPI Backend** and the **Vk-Media Web Studio** up in under 60 seconds:

```bash
# 1. Clone repository
git clone https://github.com/LakshmanDev12/incubrix-video-broll-engine.git
cd incubrix-video-broll-engine

# 2. Launch containerized stack
docker compose up -d

# 3. View running containers
docker compose ps
```

- 🌐 **Web Studio UI:** [http://localhost:8000](http://localhost:8000)
- 🔌 **API Backend:** [http://localhost:8002](http://localhost:8002)
- 📚 **Interactive OpenAPI Docs:** [http://localhost:8002/docs](http://localhost:8002/docs)

To view backend logs or shut down:
```bash
docker compose logs -f backend
docker compose down
```

---

### Option B: Native Host Environment (Windows / Linux / macOS)

#### Prerequisites
- **Python:** `3.12+` or `3.13` (64-bit)
- **FFmpeg & FFprobe:** `6.0+` on system `PATH`
  - *Windows:* `winget install Gyan.FFmpeg`
  - *Debian/Ubuntu:* `sudo apt update && sudo apt install -y ffmpeg`
  - *macOS:* `brew install ffmpeg`

#### 1. Setup & Dependencies
```bash
# Create and activate virtual environment
python -m venv venv

# Windows (PowerShell)
.\venv\Scripts\Activate.ps1
# Linux / macOS
source venv/bin/activate

# Install required packages
pip install -r requirements.txt

# Copy environment variables
cp .env.example .env
```

#### 2. Run Servers
You can use the provided convenience launchers or start manually:

```powershell
# Windows Convenience Script (launches both Backend :8002 and Frontend :8000)
.\start_all.bat
# or
.\start_all.ps1
```

Or start the backend manually:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8002 --reload
```

---

### Option C: Run Headless Automated Demo

Verify your local FFmpeg setup and end-to-end rendering without opening a browser:

```bash
python demo_run.py
```
*This script submits a 3-scene sample story, monitors queue progression, downloads final deliverables into `output/`, and runs stream verification using FFprobe.*

---

## 🖥️ Vk-Media Studio (Split-Screen UI)

The web studio is optimized for rapid, distraction-free video creation:

```
┌──────────────────────────────────────────────┬──────────────────────────────────────────────┐
│  🎬 PROMPT & SCENE STUDIO (Left Pane)        │  🎥 LIVE PLAYER & PREVIEW (Right Pane)       │
├──────────────────────────────────────────────┼──────────────────────────────────────────────┤
│  Project Title: [ Deep Ocean Frontier     ]  │  ┌────────────────────────────────────────┐  │
│                                              │  │                                        │  │
│  Narration Script:                           │  │                                        │  │
│  ┌────────────────────────────────────────┐  │  │                                        │  │
│  │ The deep ocean remains Earth's last    │  │  │             [VIDEO STREAM]             │  │
│  │ uncharted frontier. Strange bioluminescent│  │  │                                        │  │
│  │ creatures thrive in extreme pressures. │  │  │  "The deep ocean remains Earth's..."   │  │
│  └────────────────────────────────────────┘  │  │                                        │  │
│                                              │  └────────────────────────────────────────┘  │
│  Voice: [Christopher (Neural) ▼]             │   00:04 / 00:15                [ 1080p, 30fps ]
│  Aspect Ratio: [ 16:9 Landscape ▼ ]          │                                              │
│                                              │  ┌────────────────────────────────────────┐  │
│  [ ▶ Preview ]   [ ⚡ Generate Video ]       │  │  ⬇ Download Video: Deep Ocean...mp4    │  │
│                                              │  └────────────────────────────────────────┘  │
│  SCENE BREAKDOWN (Auto-Generated)            │                                              │
│  ┌──────────────────┐ ┌──────────────────┐   │  REAL-TIME PROGRESS                          │
│  │ Scene 1 (3.8s)   │ │ Scene 2 (4.2s)   │   │  Rendering video and multiplexing audio...   │
│  │ Deep sea seabed  │ │ Glowing jellyfish│   │  [█████████████████████████░░░░░] 75%        │
│  └──────────────────┘ └──────────────────┘   │                                              │
└──────────────────────────────────────────────┴──────────────────────────────────────────────┘
```

### Studio Workflow Highlights:
1. **Instant Scene Tokenization:** Type or paste your script and hit **Preview** or **Generate**. The engine automatically segments your text into discrete visual scenes, calculates balanced durations, and updates the scene cards in real time.
2. **Synchronized Playback:** Final videos download with your dynamic project title (e.g. `Deep_Ocean_Frontier.mp4`) and play with frame-accurate subtitle timing in the built-in video player.
3. **Optimized Display:** Pre-configured with a broadcast-standard profile (`1080p, 30 fps`) while leveraging accelerated conforming under the hood.

---

## 🏗️ System Architecture

### Processing Lifecycle & State Machine

Jobs move through a deterministic finite state machine backed by SQLite WAL persistence:

```mermaid
stateDiagram-v2
    [*] --> queued: Job Registered (Idempotency Checked)
    queued --> running: Async Worker Dequeues
    queued --> cancelled: User Cancels Job
    queued --> failed: Ingestion / Payload Error

    state running {
        [*] --> validating: Check magic bytes & payloads
        validating --> processing_media: Fetch B-roll & synthesize Edge-TTS
        processing_media --> assembling_timeline: Align scene cuts & audio durations
        assembling_timeline --> rendering: Conforming, crop & FFmpeg multiplexing
        rendering --> generating_artifacts: Burn subtitles, build SRT, generate manifest
        generating_artifacts --> [*]
    }

    running --> completed: Pass FFprobe Quality Gate
    running --> failed: Encoding Crash / Execution Timeout
    running --> cancelled: Cooperative Cancellation

    failed --> queued: Auto-retry backoff (up to 3 retries)
    failed --> [*]: Terminal Failure
    completed --> [*]: Terminal Deliverables Ready
    cancelled --> [*]: Terminal Abort
```

### Stage Milestones

| Stage | Milestone | Details |
| :--- | :---: | :--- |
| **`validating`** | 15% | Inspects binary magic bytes, validates script words, checks duration constraints. |
| **`processing_media`** | 35% | Generates Edge-TTS speech (or downloads audio), queries B-roll candidates, verifies CC0 licenses. |
| **`assembling_timeline`**| 55% | Aligns cut points, calculates pacing offsets, applies duration balancing (`auto_rebalance_scenes`). |
| **`rendering`** | 75% | Executes FFmpeg subprocesses with `-stream_loop -1` safeguards and audio filters (`apad`/`afade`). |
| **`generating_artifacts`**| 90% | Emits `.srt`, `.vtt`, `timeline.json`, and computes SHA-256 deliverable hashes. |
| **`completed`** | 100% | Verified by FFprobe quality gate; outputs registered and ready for download. |

---

## 🔌 REST API Reference

### 1. Submit Render Job (JSON)
`POST /v1/jobs`

Enqueues a structured job with pre-defined or auto-segmented scene prompts:

```bash
curl -X POST "http://localhost:8002/v1/jobs" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: job-sample-101" \
  -d '{
    "title": "Cloud Computing Architecture",
    "aspect_ratio": "16:9",
    "resolution": "1080p",
    "scenes": [
      {
        "narration": "Modern cloud infrastructure enables seamless global scalability.",
        "duration_seconds": 4.0,
        "visual_description": "Data center server racks with flashing blue LED lights"
      },
      {
        "narration": "Automated deployments guarantee high availability and zero downtime.",
        "duration_seconds": 4.0,
        "visual_description": "Software engineer deploying code on dual monitors"
      }
    ]
  }'
```

---

### 2. Submit Multipart Job with Audio Narration
`POST /v1/jobs/multipart`

Submits scenes paired with a pre-recorded voiceover audio file (`.wav`, `.mp3`, `.flac`, `.aac`, `.ogg`):

```bash
curl -X POST "http://localhost:8002/v1/jobs/multipart" \
  -F "title=Product Demo Voiceover" \
  -F "aspect_ratio=9:16" \
  -F "resolution=1080p" \
  -F "auto_rebalance_scenes=true" \
  -F "audio_file=@narration.wav;type=audio/wav" \
  -F "scenes=[{\"narration\":\"Next generation video synthesis\",\"duration_seconds\":5.0,\"visual_description\":\"Futuristic digital city with data streams\"}]"
```

---

### 3. Track Job Progress
`GET /v1/jobs/{job_id}`

```bash
curl -X GET "http://localhost:8002/v1/jobs/747ce606-cfa3-4c91-91ea-0d05777fe627"
```

**Response Payload:**
```json
{
  "job_id": "747ce606-cfa3-4c91-91ea-0d05777fe627",
  "status": "completed",
  "stage": "completed",
  "progress_pct": 100,
  "created_at": "2026-10-25T10:15:30Z",
  "completed_at": "2026-10-25T10:15:48Z",
  "artifacts": [
    {
      "name": "video.mp4",
      "download_url": "/v1/jobs/747ce606-cfa3-4c91-91ea-0d05777fe627/artifacts/video.mp4",
      "sha256": "4a71b2d30e52...",
      "size_bytes": 14205819
    },
    {
      "name": "captions.srt",
      "download_url": "/v1/jobs/747ce606-cfa3-4c91-91ea-0d05777fe627/artifacts/captions.srt"
    },
    {
      "name": "manifest.json",
      "download_url": "/v1/jobs/747ce606-cfa3-4c91-91ea-0d05777fe627/artifacts/manifest.json"
    }
  ]
}
```

---

### 4. Download Deliverables
`GET /v1/jobs/{job_id}/artifacts/{name}`

```bash
# Download final synthesized video
curl -O "http://localhost:8002/v1/jobs/{job_id}/artifacts/video.mp4"

# Download SubRip captions
curl -O "http://localhost:8002/v1/jobs/{job_id}/artifacts/captions.srt"

# Download provenance audit manifest
curl -O "http://localhost:8002/v1/jobs/{job_id}/artifacts/manifest.json"
```

---

### 5. Health & Diagnostic Probes
- `GET /health/live` — Returns `200 OK` if the process is responsive.
- `GET /health/ready` — Checks database connectivity and verifies `MIN_DISK_FREE_BYTES` (500 MB threshold).

---

## 🛡️ Security & Media Compliance

### Magic Byte Binary Verification
The engine strictly rejects reliance on declared file extensions or MIME headers. Every binary upload is inspected at offset `0x00`:

| Format | Magic Signature | Allowed Status |
| :--- | :--- | :---: |
| **WAV** | `52 49 46 46 .... 57 41 56 45` (`RIFF....WAVE`) | ✅ Accepted |
| **MP3** | `49 44 33` (`ID3`) or `FF FB / FF F3` (MPEG sync) | ✅ Accepted |
| **FLAC** | `66 4C 61 43` (`fLaC`) | ✅ Accepted |
| **AAC / M4A** | `FF F1 / FF F9` (ADTS) or `66 74 79 70 4D 34 41` (`ftypM4A`) | ✅ Accepted |
| **OGG** | `4F 67 67 53` (`OggS`) | ✅ Accepted |
| **Executable Binaries** | `4D 5A` (`MZ` PE/DOS), `7F 45 4C 46` (`ELF`) | 🛑 Blocked (`SECURITY_VIOLATION`) |
| **Scripts / HTML** | `#!`, `<!DOCTYPE`, `<html`, `{` | 🛑 Blocked (`UNSUPPORTED_MEDIA_TYPE`) |

### Media Licensing & Provenance
- All candidate clips are tagged with provenance metadata.
- Non-derivative licenses (such as `CC-BY-ND`) are mathematically excluded to prevent derivative copyright violations.
- A cryptographic record with SHA-256 digests and source URLs is generated in `manifest.json`.

---

## ⚙️ Configuration & Environment Variables

Configure behavior using environment variables or a local `.env` file:

| Variable | Default Value | Description |
| :--- | :---: | :--- |
| `OUTPUT_DIR` | `<root>/output` | Path for database, uploads, temp chunks, and output artifacts. |
| `DEFAULT_MEDIA_PROVIDER` | `local_cc0` | Default B-roll source (`local_cc0`, `pixabay`, `pexels`, `ai_generator`). |
| `ENABLE_REMOTE_PROVIDERS` | `false` | Enable or disable outbound remote stock video API queries. |
| `PEXELS_API_KEY` | `""` | API key for Pexels stock video search. |
| `PIXABAY_API_KEY` | `""` | API key for Pixabay stock footage search. |
| `AI_VIDEO_GENERATOR_URL` | `""` | Optional endpoint URL for self-hosted AI video generation services. |
| `MIN_DISK_FREE_BYTES` | `524288000` | Minimum free disk space (500 MB) required for readiness probe. |
| `FFMPEG_SCENE_TIMEOUT` | `60.0` | Maximum seconds allowed to conform an individual scene clip. |
| `FFMPEG_TOTAL_TIMEOUT` | `180.0` | Maximum seconds allowed for concatenation and final video muxing. |
| `MAX_AUDIO_FILE_SIZE_BYTES` | `52428800` | Maximum size (50 MB) for uploaded narration voiceovers. |
| `ALLOW_PRIVATE_NETWORKS` | `false` | Security flag: blocks downloads from RFC1918 / localhost IP addresses. |

---

## 🧪 Testing & Quality Gate

The project maintains 100% passing test coverage across 155 test suites covering ingestion, media ranking, scene splitting, SQLite transactions, and FFmpeg error handling:

```bash
# Run complete test suite
python -m pytest -o pythonpath=. tests -v
```

### Verified Test Matrix:
```
tests/test_api.py .................................. [ 22%]
tests/test_audio_validation.py ..................... [ 36%]
tests/test_concurrency.py .......................... [ 48%]
tests/test_edge_tts.py ............................. [ 55%]
tests/test_idempotency.py .......................... [ 68%]
tests/test_providers.py ............................ [ 80%]
tests/test_relevance_ranking.py .................... [ 91%]
tests/test_video_composer.py ....................... [100%]

============================= 155 passed in 21.42s =============================
```

---

## 🤝 Contributing & License

Contributions, bug reports, and suggestions are welcome!
1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m "feat: add amazing feature"`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

Distributed under the **MIT License**. See [`LICENSE`](LICENSE) for details.

<div align="center">
<sub>Engineered with precision by <b>Vk-Media / IncuBrix</b>. Powering autonomous video generation.</sub>
</div>
