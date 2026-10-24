import io
from pathlib import Path
import struct
import wave

def make_valid_wav_bytes(duration_seconds: float = 4.0, sample_rate: int = 44100, channels: int = 1) -> bytes:
    """Generates a valid PCM 16-bit RIFF/WAVE audio byte buffer."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        num_samples = int(duration_seconds * sample_rate * channels)
        # 16-bit silent samples
        data = struct.pack(f"<{num_samples}h", *(0 for _ in range(num_samples)))
        w.writeframes(data)
    return buf.getvalue()


def make_valid_mp3_bytes(duration_seconds: float = 4.0, bitrate_kbps: int = 128, sample_rate: int = 44100) -> bytes:
    """
    Generates a valid MPEG-1 Layer III audio stream consisting of repeated valid frames.
    MPEG-1 Layer 3, 128kbps, 44100Hz: frame size = 144 * 128000 // 44100 = 417 bytes.
    Frame header = 0xFF 0xFB 0x90 0x00.
    """
    frame_size = int(144 * (bitrate_kbps * 1000) / sample_rate)
    header = bytes([0xFF, 0xFB, 0x90, 0x00])
    frame = header + b"\x00" * (frame_size - len(header))
    
    # Each frame in Layer III 44.1kHz is 1152 samples = 1152 / 44100 ~= 0.02612s
    frame_duration = 1152.0 / sample_rate
    num_frames = int(duration_seconds / frame_duration) + 1
    return frame * num_frames


def make_corrupted_audio_bytes() -> bytes:
    """Truncated WAV header without chunk data."""
    return b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00"


def make_executable_disguised_as_audio() -> bytes:
    """Executable DOS/PE header bytes."""
    return b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xFF\xFF\x00\x00"


def make_html_disguised_as_audio() -> bytes:
    """HTML document bytes."""
    return b"<!DOCTYPE html><html><body>Error 404</body></html>"


def create_real_h264_clip(
    output_path: Path,
    width: int = 1920,
    height: int = 1080,
    duration_seconds: float = 2.0,
    fps: int = 30,
    pattern: str = "testsrc",
    color: str = "navy"
) -> Path:
    """
    Generates a legally usable, real H.264 MP4 video fixture using FFmpeg lavfi filters.
    If FFmpeg is unavailable, falls back to native ISO-BMFF box synthesis.
    """
    import shutil
    import subprocess
    from app.config import settings

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if shutil.which("ffmpeg"):
        if pattern == "testsrc":
            src = f"testsrc=duration={duration_seconds:.3f}:size={width}x{height}:rate={fps}"
        elif pattern == "smptebars":
            src = f"smptebars=duration={duration_seconds:.3f}:size={width}x{height}:rate={fps}"
        else:
            src = f"color=c={color}:s={width}x{height}:r={fps}:d={duration_seconds:.3f}"

        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", src,
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-pix_fmt", "yuv420p",
            "-r", str(fps),
            "-an",
            str(output_path)
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return output_path
    else:
        from app.services.video_composer import VideoComposer
        return VideoComposer.generate_fallback_mp4(
            dest_path=output_path,
            width=width,
            height=height,
            duration_sec=duration_seconds,
            fps=float(fps)
        )
