import math
from pathlib import Path
import textwrap
from typing import Any, Dict, List, Optional, Tuple


def format_srt_timestamp(seconds: float) -> str:
    """Formats float seconds into SRT timestamp: HH:MM:SS,mmm"""
    if seconds < 0:
        seconds = 0.0
    total_ms = int(round(seconds * 1000))
    hrs = total_ms // 3600000
    total_ms %= 3600000
    mins = total_ms // 60000
    total_ms %= 60000
    secs = total_ms // 1000
    ms = total_ms % 1000
    return f"{hrs:02d}:{mins:02d}:{secs:02d},{ms:03d}"


def format_vtt_timestamp(seconds: float) -> str:
    """Formats float seconds into WebVTT timestamp: HH:MM:SS.mmm"""
    if seconds < 0:
        seconds = 0.0
    total_ms = int(round(seconds * 1000))
    hrs = total_ms // 3600000
    total_ms %= 3600000
    mins = total_ms // 60000
    total_ms %= 60000
    secs = total_ms // 1000
    ms = total_ms % 1000
    return f"{hrs:02d}:{mins:02d}:{secs:02d}.{ms:03d}"


def generate_subtitles(
    scenes: List[Dict[str, Any]],
    max_line_chars: int = 42
) -> Tuple[str, str]:
    """
    Generates synchronized SubRip (.srt) and WebVTT (.vtt) subtitle tracks.
    
    Args:
        scenes: List of scene dictionaries containing 'narration', 'duration_seconds',
                and optional 'start_seconds' / 'end_seconds'.
        max_line_chars: Maximum characters per line before soft word-wrapping.
        
    Returns:
        Tuple of (srt_content, vtt_content).
    """
    srt_cues = []
    vtt_cues = ["WEBVTT\n"]

    current_time = 0.0
    cue_number = 1

    for scene in scenes:
        duration = float(scene.get("duration_seconds", 3.0))
        if "start_seconds" in scene and scene["start_seconds"] is not None:
            start_time = float(scene["start_seconds"])
        else:
            start_time = current_time

        if "end_seconds" in scene and scene["end_seconds"] is not None:
            end_time = float(scene["end_seconds"])
        else:
            end_time = start_time + duration

        narration = str(scene.get("narration", "")).strip()

        if narration:
            # Wrap lines for readability (standard broadcast guideline: max 2 lines per cue)
            wrapped = textwrap.wrap(narration, width=max_line_chars)
            formatted_text = "\n".join(wrapped) if wrapped else narration

            # SRT cue block
            srt_start = format_srt_timestamp(start_time)
            srt_end = format_srt_timestamp(end_time)
            srt_cues.append(f"{cue_number}\n{srt_start} --> {srt_end}\n{formatted_text}\n")

            # VTT cue block
            vtt_start = format_vtt_timestamp(start_time)
            vtt_end = format_vtt_timestamp(end_time)
            vtt_cues.append(f"{cue_number}\n{vtt_start} --> {vtt_end}\n{formatted_text}\n")

            cue_number += 1

        current_time = end_time

    srt_text = "\n".join(srt_cues).strip() + "\n" if srt_cues else ""
    vtt_text = "\n".join(vtt_cues).strip() + "\n"

    return srt_text, vtt_text


def write_subtitle_files(
    output_dir: Path,
    scenes: List[Dict[str, Any]],
    base_name: str = "captions"
) -> Tuple[Path, Path]:
    """
    Generates and saves both .srt and .vtt subtitle files into output_dir.
    Returns (srt_path, vtt_path).
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    srt_content, vtt_content = generate_subtitles(scenes)

    srt_path = output_dir / f"{base_name}.srt"
    vtt_path = output_dir / f"{base_name}.vtt"

    srt_path.write_text(srt_content, encoding="utf-8")
    vtt_path.write_text(vtt_content, encoding="utf-8")

    return srt_path, vtt_path
