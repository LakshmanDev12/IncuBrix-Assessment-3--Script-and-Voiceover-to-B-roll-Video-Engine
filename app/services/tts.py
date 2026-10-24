import asyncio
import logging
from pathlib import Path
import shutil
import subprocess
from typing import Any, Dict, List, Optional

logger = logging.getLogger("video_engine.tts")

DEFAULT_VOICE = "en-US-ChristopherNeural"


async def synthesize_scene_narration(text: str, output_path: Path, voice: str = DEFAULT_VOICE) -> bool:
    """Synthesizes text into an audio file using edge-tts or system fallback."""
    if not text or not text.strip():
        return False

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # 1. Try edge-tts first (high-quality neural voice)
    try:
        import edge_tts
        communicate = edge_tts.Communicate(text.strip(), voice)
        await communicate.save(str(output_path))
        if output_path.exists() and output_path.stat().st_size > 100:
            return True
    except Exception as e:
        logger.warning(f"edge-tts failed: {e}. Attempting fallback TTS...")

    # 2. Windows System.Speech SAPI Fallback (works 100% offline on Windows)
    try:
        clean_text = text.replace("'", "").replace('"', "")
        ps_cmd = (
            f"Add-Type -AssemblyName System.Speech; "
            f"$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            f"$s.SetOutputToWaveFile('{output_path.as_posix()}'); "
            f"$s.Speak('{clean_text}'); $s.Dispose();"
        )
        res = subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], capture_output=True, timeout=15)
        if output_path.exists() and output_path.stat().st_size > 100:
            return True
    except Exception as e:
        logger.warning(f"PowerShell System.Speech fallback failed: {e}")

    return False


async def generate_voiceover_for_scenes(
    scenes: List[Dict[str, Any]],
    output_audio_path: Path,
    total_duration: float,
    voice: str = DEFAULT_VOICE
) -> Optional[Path]:
    """
    Synthesizes speech for all scenes and aligns them to their scene durations.
    Pads each scene's audio to its exact scene duration and concatenates them seamlessly.
    Produces a single continuous broadcast-ready stereo audio file.
    """
    if not scenes:
        return None

    temp_dir = output_audio_path.parent / "temp_tts"
    temp_dir.mkdir(parents=True, exist_ok=True)
    ffmpeg_bin = shutil.which("ffmpeg") or "ffmpeg"

    padded_files: List[Path] = []

    try:
        tts_sem = asyncio.Semaphore(6)

        async def _synth_one_scene(idx: int, sc: Dict[str, Any]) -> Optional[Path]:
            narration = str(sc.get("narration", "")).strip()
            dur = float(sc.get("duration_seconds", 3.0))

            raw_speech = temp_dir / f"raw_{idx:03d}.mp3"
            padded_wav = temp_dir / f"pad_{idx:03d}.wav"

            ok = False
            if narration:
                async with tts_sem:
                    ok = await synthesize_scene_narration(narration, raw_speech, voice=voice)

            if ok and raw_speech.exists():
                cmd = [
                    ffmpeg_bin, "-y",
                    "-i", str(raw_speech),
                    "-af", f"apad,atrim=0:{dur:.3f}",
                    "-c:a", "pcm_s16le",
                    "-ar", "44100",
                    "-ac", "2",
                    str(padded_wav)
                ]
            else:
                cmd = [
                    ffmpeg_bin, "-y",
                    "-f", "lavfi",
                    "-i", f"anullsrc=channel_layout=stereo:sample_rate=44100",
                    "-t", f"{dur:.3f}",
                    "-c:a", "pcm_s16le",
                    str(padded_wav)
                ]

            proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
            await proc.wait()
            if padded_wav.exists() and padded_wav.stat().st_size > 100:
                return padded_wav
            return None

        synth_tasks = [_synth_one_scene(i, s) for i, s in enumerate(scenes)]
        results = await asyncio.gather(*synth_tasks)
        padded_files = [r for r in results if r is not None]

        if not padded_files:
            return None

        # Build concat list
        concat_txt = temp_dir / "concat_audio.txt"
        with open(concat_txt, "w", encoding="utf-8") as f:
            for pf in padded_files:
                f.write(f"file '{pf.resolve().as_posix()}'\n")

        # Concat all padded scene audios into final voiceover file
        output_audio_path.parent.mkdir(parents=True, exist_ok=True)
        final_cmd = [
            ffmpeg_bin, "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_txt),
            "-c:a", "pcm_s16le",
            str(output_audio_path)
        ]

        res = subprocess.run(final_cmd, capture_output=True)
        if res.returncode == 0 and output_audio_path.exists() and output_audio_path.stat().st_size > 500:
            logger.info(f"Synthesized voiceover audio for {len(scenes)} scenes: {output_audio_path}")
            return output_audio_path

    except Exception as e:
        logger.error(f"Error in generate_voiceover_for_scenes: {e}")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    return None
