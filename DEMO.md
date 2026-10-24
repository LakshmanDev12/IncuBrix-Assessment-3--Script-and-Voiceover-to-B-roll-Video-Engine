# IncuBrix Video Engine — Demo Guide & Output Checklist

This guide provides step-by-step instructions for running a reproducible end-to-end demonstration of the Video Engine, along with an expected output verification checklist.

---

## 1. Quickstart: One-Command Demonstration

The repository includes a self-contained demonstration script that initializes the database, enqueues a multi-scene render job, monitors pipeline progress, verifies the output with FFprobe, and inspects deliverable artifacts:

```bash
# Execute from workspace root
python video-broll-engine/demo_run.py
```

### Expected Console Output:
```text
======================================================================
  IncuBrix Video Engine — Reproducible End-to-End Demo
======================================================================
[1/5] Database initialized and background queue worker active.
[2/5] Creating demo job 'demo-...' with 3 scenes (10.0s total)...
[3/5] Polling worker progress across pipeline stages...
  -> Stage: queued                 | Progress:   0.0% | Message: Job accepted and queued for processing.
  -> Stage: rendering              | Progress:  75.0% | Message: Rendering 1080p video composition and multiplexing audio.
  -> Stage: completed              | Progress: 100.0% | Message: Video processing completed successfully.

[4/5] Video generation finished successfully!

[5/5] Verifying deliverable artifacts in output/demo-...:
  [OK] video.mp4          (  973.52 KB)
  [OK] captions.srt       (    0.33 KB)
  [OK] captions.vtt       (    0.34 KB)
  [OK] timeline.json      (    3.01 KB)
  [OK] manifest.json      (    6.96 KB)

--- FFprobe Quality Verification Results ---
  Verified With:    ffprobe
  Validation Passed:True
  Format:           mov,mp4,m4a,3gp,3g2,mj2
  Video Codec:      h264 (1920x1080 @ 30.0 fps)
  Audio Codec:      aac (2 channels @ 44100 Hz)
  Duration:         10.00s (Expected: 10.00s)
  File Size:        0.95 MB
```

---

## 2. Interactive REST API Walkthrough

To demonstrate the engine interactively via HTTP endpoints:

### Step 1: Start the FastAPI Server
```bash
# From workspace root
uvicorn app.main:app --app-dir video-broll-engine --host 0.0.0.0 --port 8000 --reload
```

### Step 2: Check Service Readiness
```bash
curl -X GET "http://127.0.0.1:8000/health/ready"
```
**Expected Response (HTTP 200):**
```json
{
  "status": "ready",
  "checks": {
    "database": {"status": "ok", "message": "Database query succeeded."},
    "storage": {"status": "ok", "writable": true},
    "media_binaries": {"ffmpeg_available": true, "ffprobe_available": true},
    "worker": {"status": "ok", "active": true}
  }
}
```

### Step 3: Submit a Render Job (`POST /v1/jobs`)
```bash
curl -X POST "http://127.0.0.1:8000/v1/jobs" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: demo-submission-001" \
  -d '{
    "title": "IncuBrix Product Launch",
    "aspect_ratio": "16:9",
    "resolution": "1080p",
    "scenes": [
      {
        "narration": "IncuBrix streamlines creator workflows through intelligent visual curation.",
        "duration_seconds": 3.5,
        "visual_description": "Software engineer typing code at modern workstation",
        "keywords": ["developer", "coding", "software"]
      },
      {
        "narration": "Automated B-roll selection pairs your script with lawful, verified footage.",
        "duration_seconds": 3.5,
        "visual_description": "Server hardware racks with blinking network activity lights",
        "keywords": ["server", "technology", "network"]
      },
      {
        "narration": "Export synchronized 1080p video, captions, and timelines in seconds.",
        "duration_seconds": 3.0,
        "visual_description": "Modern creative digital studio with video production timeline on screen",
        "keywords": ["studio", "video editing", "timeline"]
      }
    ]
  }'
```
**Expected Response (HTTP 202 Accepted):**
```json
{
  "job_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
  "title": "IncuBrix Product Launch",
  "status": "queued",
  "progress": 0.0,
  "aspect_ratio": "16:9",
  "resolution": "1080p",
  "duration_seconds": 10.0,
  "scenes_count": 3
}
```

### Step 4: Poll Job Status & Progress (`GET /v1/jobs/{job_id}`)
```bash
curl -X GET "http://127.0.0.1:8000/v1/jobs/9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d"
```
**Expected Response Once Completed (HTTP 200 OK):**
```json
{
  "job_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
  "status": "completed",
  "current_stage": "completed",
  "progress": 100.0,
  "stage_message": "Video processing completed successfully."
}
```

### Step 5: List & Download Artifacts
```bash
# List all artifacts with hashes and sizes
curl -X GET "http://127.0.0.1:8000/v1/jobs/9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d/artifacts"

# Download final MP4 video deliverable
curl -O "http://127.0.0.1:8000/v1/jobs/9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d/artifacts/video.mp4"

# Download subtitle track
curl -O "http://127.0.0.1:8000/v1/jobs/9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d/artifacts/captions.srt"
```

---

## 3. Expected Output Verification Checklist

| Deliverable | Expected Format | Validation Criteria | Verified By |
| :--- | :--- | :--- | :--- |
| `video.mp4` | MP4 (H.264 / AAC) | Width: 1920, Height: 1080, FPS: 30.0, Duration: 10.00s ($\pm 0.5\text{s}$), non-zero byte size. | FFprobe Quality Gate |
| `captions.srt` | SubRip Subtitle | Valid sequential indices (`1`, `2`, `3`), valid timestamp format (`00:00:00,000 --> 00:00:03,500`), clean line wraps. | Regex parser |
| `captions.vtt` | WebVTT Subtitle | Valid `WEBVTT` header, valid decimal timestamps (`00:00:00.000 --> 00:00:03.500`). | WebVTT spec parser |
| `timeline.json` | JSON | Documents each cut point, scene duration, narration, selected B-roll metadata, and aspect ratio. | JSON Schema |
| `manifest.json` | JSON | Contains SHA-256 digests for all generated files, video specs, and Attribution Ledger credit roll. | Hash verification |
