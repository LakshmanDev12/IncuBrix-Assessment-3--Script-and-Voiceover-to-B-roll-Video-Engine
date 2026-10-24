from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
from typing import Optional
import wave

from app.config import settings


@dataclass
class AudioInspectionResult:
    codec: str
    format_name: str
    duration_seconds: float
    sample_rate: int
    channels: int
    bit_rate: Optional[int]
    file_size_bytes: int


class AudioInspectionError(ValueError):
    """Raised when an audio file is invalid, corrupted, unsupported, or insecure."""
    def __init__(self, message: str, code: str = "INVALID_AUDIO"):
        super().__init__(message)
        self.code = code
        self.message = message


def _check_dangerous_magic_bytes(header: bytes):
    """Rejects executable binaries, archives, and text payloads pretending to be audio."""
    if header.startswith(b"MZ"):
        raise AudioInspectionError("Executable binary (DOS/PE) detected. Execution prohibited.", code="SECURITY_VIOLATION")
    if header.startswith(b"\x7fELF"):
        raise AudioInspectionError("Executable binary (ELF) detected. Execution prohibited.", code="SECURITY_VIOLATION")
    if header.startswith(b"PK\x03\x04") or header.startswith(b"PK\x05\x06"):
        raise AudioInspectionError("Archive file (ZIP/JAR) detected.", code="UNSUPPORTED_MEDIA_TYPE")
    if header.startswith(b"<!DOC") or header.startswith(b"<html") or header.startswith(b"<?xml"):
        raise AudioInspectionError("HTML/XML document detected instead of audio.", code="UNSUPPORTED_MEDIA_TYPE")
    if header.strip().startswith(b"{") or header.strip().startswith(b"["):
        raise AudioInspectionError("JSON payload detected instead of audio.", code="UNSUPPORTED_MEDIA_TYPE")


def _inspect_with_ffprobe(file_path: Path, ffprobe_bin: str) -> Optional[AudioInspectionResult]:
    """Inspects media file using FFprobe CLI tool."""
    command = [
        ffprobe_bin,
        "-v", "error",
        "-select_streams", "a:0",
        "-show_entries", "stream=codec_name,channels,sample_rate,duration,bit_rate",
        "-show_entries", "format=duration,size,format_name,bit_rate",
        "-of", "json",
        str(file_path)
    ]
    try:
        proc = subprocess.run(command, capture_output=True, text=True, timeout=10)
        if proc.returncode != 0:
            err_msg = proc.stderr.strip() or "FFprobe failed to decode audio file."
            raise AudioInspectionError(f"Corrupted or invalid audio: {err_msg}", code="CORRUPTED_AUDIO_FILE")

        data = json.loads(proc.stdout)
        streams = data.get("streams", [])
        if not streams:
            raise AudioInspectionError("File does not contain an audio stream or codec.", code="MISSING_AUDIO_CODEC")

        astream = streams[0]
        aformat = data.get("format", {})

        codec = astream.get("codec_name", "unknown")
        format_name = aformat.get("format_name", "unknown").split(",")[0]
        channels = int(astream.get("channels", 1))
        sample_rate = int(astream.get("sample_rate", 44100))

        # Duration can be on stream or on format
        duration_raw = astream.get("duration") or aformat.get("duration")
        if not duration_raw:
            raise AudioInspectionError("Unable to determine audio stream duration.", code="INVALID_AUDIO_DURATION")
        
        duration = float(duration_raw)
        if duration <= 0:
            raise AudioInspectionError("Audio duration must be greater than zero.", code="INVALID_AUDIO_DURATION")

        bit_rate_raw = astream.get("bit_rate") or aformat.get("bit_rate")
        bit_rate = int(bit_rate_raw) if bit_rate_raw and str(bit_rate_raw).isdigit() else None
        size_bytes = int(aformat.get("size", file_path.stat().st_size))

        return AudioInspectionResult(
            codec=codec,
            format_name=format_name,
            duration_seconds=round(duration, 3),
            sample_rate=sample_rate,
            channels=channels,
            bit_rate=bit_rate,
            file_size_bytes=size_bytes
        )
    except subprocess.TimeoutExpired:
        raise AudioInspectionError("Audio inspection timed out.", code="INSPECTION_TIMEOUT")
    except json.JSONDecodeError:
        raise AudioInspectionError("Failed to parse FFprobe inspection output.", code="CORRUPTED_AUDIO_FILE")


def _inspect_wav_native(file_path: Path, file_size: int) -> AudioInspectionResult:
    """Native parser for RIFF/WAVE PCM audio files."""
    try:
        with wave.open(str(file_path), "rb") as w:
            channels = w.getnchannels()
            framerate = w.getframerate()
            nframes = w.getnframes()
            sampwidth = w.getsampwidth()

            if channels <= 0 or framerate <= 0:
                raise AudioInspectionError("WAV header contains invalid channel count or sample rate.", code="CORRUPTED_AUDIO_FILE")
            if nframes <= 0:
                raise AudioInspectionError("WAV file contains 0 audio frames.", code="EMPTY_AUDIO_STREAM")

            duration = nframes / float(framerate)
            bit_rate = framerate * channels * sampwidth * 8

            return AudioInspectionResult(
                codec=f"pcm_s{sampwidth * 8}le",
                format_name="wav",
                duration_seconds=round(duration, 3),
                sample_rate=framerate,
                channels=channels,
                bit_rate=bit_rate,
                file_size_bytes=file_size
            )
    except wave.Error as exc:
        raise AudioInspectionError(f"Corrupted or invalid WAV file: {exc}", code="CORRUPTED_AUDIO_FILE")
    except EOFError:
        raise AudioInspectionError("Unexpected end of WAV file (truncated).", code="TRUNCATED_AUDIO_FILE")


def _inspect_mp3_native(file_path: Path, file_size: int, header: bytes) -> AudioInspectionResult:
    """Native parser for MPEG-1/2 Audio Layer III (MP3) files."""
    with open(file_path, "rb") as f:
        data = f.read(min(file_size, 65536))

    offset = 0
    # Check for ID3v2 header
    if data.startswith(b"ID3"):
        if len(data) < 10:
            raise AudioInspectionError("Truncated ID3v2 header.", code="TRUNCATED_AUDIO_FILE")
        # ID3 size is 4 bytes at offset 6, syncsafe integer (7 bits per byte)
        id3_size = ((data[6] & 0x7F) << 21) | ((data[7] & 0x7F) << 14) | ((data[8] & 0x7F) << 7) | (data[9] & 0x7F)
        offset = 10 + id3_size

    # Look for MPEG sync frame (11 set bits: 0xFF followed by 0xE0..0xFF)
    with open(file_path, "rb") as f:
        f.seek(offset)
        search_buf = f.read(8192)

    sync_pos = -1
    for i in range(len(search_buf) - 3):
        if search_buf[i] == 0xFF and (search_buf[i+1] & 0xE0) == 0xE0:
            # Check layer is Layer III (bits 17-18: 01 for Layer III)
            layer = (search_buf[i+1] >> 1) & 0x03
            if layer == 0x01:  # Layer III
                sync_pos = i
                break

    if sync_pos == -1:
        raise AudioInspectionError("No valid MPEG Layer III audio frame sync found.", code="CORRUPTED_AUDIO_FILE")

    frame = search_buf[sync_pos : sync_pos + 4]
    version_id = (frame[1] >> 3) & 0x03  # 3=MPEG 1, 2=MPEG 2
    bitrate_idx = (frame[2] >> 4) & 0x0F
    sampling_idx = (frame[2] >> 2) & 0x03
    channel_mode = (frame[3] >> 6) & 0x03
    channels = 1 if channel_mode == 3 else 2

    sample_rates_v1 = [44100, 48000, 32000]
    sample_rates_v2 = [22050, 24000, 16000]
    sample_rates = sample_rates_v1 if version_id == 3 else sample_rates_v2
    if sampling_idx >= len(sample_rates):
        raise AudioInspectionError("Invalid MP3 sampling rate index.", code="CORRUPTED_AUDIO_FILE")
    sample_rate = sample_rates[sampling_idx]

    # Standard V1 Layer 3 bitrates in kbps
    bitrates_v1_l3 = [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320]
    bitrate_kbps = bitrates_v1_l3[bitrate_idx] if bitrate_idx < len(bitrates_v1_l3) else 128
    if bitrate_kbps == 0:
        bitrate_kbps = 128
    bit_rate = bitrate_kbps * 1000

    # Approximate duration from audio payload size
    audio_bytes = max(0, file_size - offset)
    duration = (audio_bytes * 8) / float(bit_rate)

    return AudioInspectionResult(
        codec="mp3",
        format_name="mp3",
        duration_seconds=round(max(0.1, duration), 3),
        sample_rate=sample_rate,
        channels=channels,
        bit_rate=bit_rate,
        file_size_bytes=file_size
    )


def _inspect_flac_native(file_path: Path, file_size: int) -> AudioInspectionResult:
    """Native parser for FLAC audio files."""
    with open(file_path, "rb") as f:
        header = f.read(42)

    if len(header) < 42 or not header.startswith(b"fLaC"):
        raise AudioInspectionError("Corrupted or incomplete FLAC header.", code="CORRUPTED_AUDIO_FILE")

    # STREAMINFO starts at offset 8 (after 4 byte magic + 4 byte metadata block header)
    stream_info = header[8:42]
    # Sample rate (20 bits), channels (3 bits), bits_per_sample (5 bits), total_samples (36 bits)
    # Byte 10..12: sample rate
    b10, b11, b12 = stream_info[10], stream_info[11], stream_info[12]
    sample_rate = (b10 << 12) | (b11 << 4) | (b12 >> 4)
    channels = ((b12 >> 1) & 0x07) + 1
    
    # Bytes 13..17: total samples (36 bits)
    b13, b14, b15, b16, b17 = stream_info[13], stream_info[14], stream_info[15], stream_info[16], stream_info[17]
    total_samples = ((b13 & 0x0F) << 32) | (b14 << 24) | (b15 << 16) | (b16 << 8) | b17

    if sample_rate <= 0 or total_samples <= 0:
        raise AudioInspectionError("FLAC stream contains 0 samples or invalid sample rate.", code="CORRUPTED_AUDIO_FILE")

    duration = total_samples / float(sample_rate)
    return AudioInspectionResult(
        codec="flac",
        format_name="flac",
        duration_seconds=round(duration, 3),
        sample_rate=sample_rate,
        channels=channels,
        bit_rate=None,
        file_size_bytes=file_size
    )


def inspect_audio_file(file_path: Path) -> AudioInspectionResult:
    """
    Inspects and validates an audio file.
    Uses FFprobe when available; falls back to native container parsers.
    Rejects dangerous files, zero-byte files, and corrupted streams.
    """
    if not file_path.exists():
        raise AudioInspectionError(f"Audio file '{file_path}' does not exist.", code="FILE_NOT_FOUND")

    file_size = file_path.stat().st_size
    if file_size == 0:
        raise AudioInspectionError("Audio file is empty (0 bytes).", code="EMPTY_FILE")

    # Read leading bytes for magic byte security checks
    with open(file_path, "rb") as f:
        header = f.read(512)

    _check_dangerous_magic_bytes(header)

    # 1. Try FFprobe if configured or on PATH
    ffprobe_bin = os.getenv("FFPROBE_PATH") or shutil.which("ffprobe")
    if ffprobe_bin:
        try:
            return _inspect_with_ffprobe(file_path, ffprobe_bin)
        except AudioInspectionError:
            # Re-raise explicit inspection error
            raise
        except Exception:
            pass  # Fallback to native parsers

    # 2. Native container parsing fallback
    if header.startswith(b"RIFF") and header[8:12] == b"WAVE":
        return _inspect_wav_native(file_path, file_size)

    if header.startswith(b"ID3") or header.startswith(b"\xff\xfb") or header.startswith(b"\xff\xf3"):
        return _inspect_mp3_native(file_path, file_size, header)

    if header.startswith(b"fLaC"):
        return _inspect_flac_native(file_path, file_size)

    raise AudioInspectionError(
        "Unsupported audio container or missing codec. Supported formats: WAV, MP3, FLAC, AAC.",
        code="UNSUPPORTED_MEDIA_TYPE"
    )
