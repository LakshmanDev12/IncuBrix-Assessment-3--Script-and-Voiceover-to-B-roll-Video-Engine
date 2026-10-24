from datetime import datetime, timezone
import hashlib
import json
import mimetypes
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def calculate_sha256(file_path: Path) -> str:
    """Computes the SHA-256 hexadecimal digest of a file."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def build_timeline(
    job_id: str,
    title: str,
    scenes: List[Dict[str, Any]],
    selected_clips: Optional[List[Dict[str, Any]]] = None,
    aspect_ratio: str = "16:9",
    resolution: str = "1080p",
    fps: int = 30,
    audio_source: str = "none"
) -> Dict[str, Any]:
    """
    Constructs a frame-accurate, auditable video timeline structure.
    """
    clip_map = {}
    if selected_clips:
        for idx, clip in enumerate(selected_clips):
            scene_idx = clip.get("scene_index", idx + 1)
            clip_map[scene_idx] = clip

    total_duration = 0.0
    current_time = 0.0
    timeline_scenes = []

    for idx, sc in enumerate(scenes):
        s_idx = idx + 1
        dur = round(float(sc.get("duration_seconds", 3.0)), 3)
        start_t = round(float(sc.get("start_seconds", current_time)), 3)
        end_t = round(float(sc.get("end_seconds", start_t + dur)), 3)
        dur = round(end_t - start_t, 3)

        clip_data = clip_map.get(s_idx)
        selected_media_info = None
        if clip_data:
            cand = clip_data.get("candidate", {})
            prov = clip_data.get("provenance", {})
            selected_media_info = {
                "candidate_id": cand.get("id", clip_data.get("candidate_id")),
                "provider": cand.get("provider", "local_cc0"),
                "title": cand.get("title", ""),
                "creator": cand.get("creator", "Unknown"),
                "source_page_url": prov.get("source_page_url", cand.get("source_page_url")),
                "license_name": prov.get("license_name", cand.get("license_name", "CC0-1.0")),
                "relevance_score": round(float(clip_data.get("relevance_score", 1.0)), 4),
                "selection_rank": clip_data.get("selection_rank", 1),
                "selection_reason": clip_data.get("selection_reason", "Selected matching candidate."),
                "verification_status": prov.get("verification_status", "verified")
            }

        timeline_scenes.append({
            "scene_index": s_idx,
            "start_time_seconds": start_t,
            "end_time_seconds": end_t,
            "duration_seconds": dur,
            "narration": sc.get("narration", ""),
            "visual_description": sc.get("visual_description", ""),
            "selected_clip": selected_media_info,
            "cut_points": {
                "in_point_seconds": 0.0,
                "out_point_seconds": dur
            }
        })

        current_time = end_t
        total_duration = end_t

    return {
        "job_id": job_id,
        "title": title,
        "aspect_ratio": aspect_ratio,
        "resolution": resolution,
        "fps": fps,
        "total_duration_seconds": round(total_duration, 3),
        "scenes_count": len(timeline_scenes),
        "audio_source": audio_source,
        "scenes": timeline_scenes
    }


def build_manifest(
    job_id: str,
    title: str,
    status: str,
    aspect_ratio: str,
    resolution: str,
    width: int,
    height: int,
    duration_seconds: float,
    fps: int,
    audio_source: str,
    audio_details: Optional[Dict[str, Any]],
    artifacts_dir: Path,
    scenes_count: int,
    attribution_summary: Optional[Dict[str, Any]] = None,
    rendering_engine: str = "ffmpeg",
    quality_verification: Optional[Dict[str, Any]] = None,
    created_at_utc: Optional[str] = None
) -> Dict[str, Any]:
    """
    Assembles a comprehensive manifest.json document with SHA-256 hashes,
    sizes, video specs, and licensing/provenance credit rolls.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    
    # Scan artifacts in directory
    artifact_items = []
    if artifacts_dir.exists():
        for f in sorted(artifacts_dir.iterdir()):
            if f.is_file() and f.name not in ("job_state.json", "jobs.db", "manifest.json"):
                mime, _ = mimetypes.guess_type(f.name)
                artifact_items.append({
                    "name": f.name,
                    "content_type": mime or "application/octet-stream",
                    "size_bytes": f.stat().st_size,
                    "sha256": calculate_sha256(f),
                    "download_url": f"/v1/jobs/{job_id}/artifacts/{f.name}"
                })

    video_spec = {
        "aspect_ratio": aspect_ratio,
        "resolution": resolution,
        "width": width,
        "height": height,
        "fps": fps,
        "duration_seconds": round(duration_seconds, 3),
        "video_codec": "h264",
        "audio_codec": "aac" if audio_source != "none" else "silent_aac",
        "audio_source": audio_source,
        "rendering_engine": rendering_engine
    }

    if audio_details:
        video_spec["audio_details"] = audio_details

    attr_info = attribution_summary or {
        "all_verified": True,
        "license_summary": ["CC0-1.0"],
        "credits": [],
        "credit_roll_text": "All footage used is in the Public Domain / CC0-1.0."
    }

    manifest = {
        "manifest_version": "1.0",
        "job_id": job_id,
        "title": title,
        "status": status,
        "created_at_utc": created_at_utc or now_iso,
        "completed_at_utc": now_iso,
        "video_specification": video_spec,
        "scene_summary": {
            "total_scenes": scenes_count,
            "total_duration_seconds": round(duration_seconds, 3)
        },
        "artifacts": artifact_items,
        "attribution_and_licensing": attr_info
    }

    if quality_verification:
        manifest["quality_verification"] = quality_verification

    return manifest


def write_timeline_and_manifest(
    output_dir: Path,
    timeline_data: Dict[str, Any],
    manifest_data: Dict[str, Any]
) -> Tuple[Path, Path]:
    """Writes timeline.json and manifest.json to the output directory."""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    timeline_path = output_dir / "timeline.json"
    timeline_path.write_text(json.dumps(timeline_data, indent=2), encoding="utf-8")

    # Ensure timeline.json is registered in manifest artifacts
    if not any(a.get("name") == "timeline.json" for a in manifest_data.get("artifacts", [])):
        manifest_data["artifacts"].append({
            "name": "timeline.json",
            "content_type": "application/json",
            "size_bytes": timeline_path.stat().st_size,
            "sha256": calculate_sha256(timeline_path),
            "download_url": f"/v1/jobs/{manifest_data.get('job_id')}/artifacts/timeline.json"
        })

    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")

    # Recalculate artifact entry for manifest itself
    manifest_artifact = {
        "name": "manifest.json",
        "content_type": "application/json",
        "size_bytes": manifest_path.stat().st_size,
        "sha256": calculate_sha256(manifest_path),
        "download_url": f"/v1/jobs/{manifest_data.get('job_id')}/artifacts/manifest.json"
    }
    if not any(a.get("name") == "manifest.json" for a in manifest_data.get("artifacts", [])):
        manifest_data["artifacts"].append(manifest_artifact)
        manifest_path.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")

    return timeline_path, manifest_path
