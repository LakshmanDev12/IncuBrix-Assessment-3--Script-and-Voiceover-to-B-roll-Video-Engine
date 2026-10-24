import glob
import os
from pathlib import Path
import shutil
from typing import Set

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
# Load .env if not executing under pytest
if "PYTEST_CURRENT_TEST" not in os.environ and "PYTEST_VERSION" not in os.environ:
    load_dotenv(ROOT_DIR / ".env")
    load_dotenv()


def ensure_ffmpeg_on_path():
    """Dynamically locates FFmpeg and FFprobe binaries if not already in system PATH."""
    if shutil.which("ffmpeg") and shutil.which("ffprobe"):
        return

    home = Path.home()
    candidates = [
        home / "AppData/Local/Microsoft/WinGet/Links",
        Path("C:/ffmpeg/bin"),
        Path("C:/Program Files/ffmpeg/bin"),
        * [Path(p).parent for p in glob.glob(str(home / "AppData/Local/Microsoft/WinGet/Packages/**/bin/ffmpeg.exe"), recursive=True)]
    ]

    for cand in candidates:
        if cand.exists() and (cand / "ffmpeg.exe").exists():
            os.environ["PATH"] = str(cand) + os.pathsep + os.environ.get("PATH", "")
            if shutil.which("ffmpeg") and shutil.which("ffprobe"):
                break


ensure_ffmpeg_on_path()

class Settings:
    # Directories
    OUTPUT_DIR: Path = Path(os.getenv("OUTPUT_DIR", str(ROOT_DIR / "output")))
    UPLOAD_DIR: Path = OUTPUT_DIR / "uploads"

    # Job & Content Limits
    MIN_TITLE_LENGTH: int = int(os.getenv("MIN_TITLE_LENGTH", "1"))
    MAX_TITLE_LENGTH: int = int(os.getenv("MAX_TITLE_LENGTH", "120"))
    
    MIN_SCENES: int = int(os.getenv("MIN_SCENES", "1"))
    MAX_SCENES: int = int(os.getenv("MAX_SCENES", "150"))
    
    MIN_SCENE_DURATION_SECONDS: float = float(os.getenv("MIN_SCENE_DURATION_SECONDS", "0.5"))
    MAX_SCENE_DURATION_SECONDS: float = float(os.getenv("MAX_SCENE_DURATION_SECONDS", "60.0"))
    
    MIN_JOB_DURATION_SECONDS: float = float(os.getenv("MIN_JOB_DURATION_SECONDS", "1.0"))
    MAX_JOB_DURATION_SECONDS: float = float(os.getenv("MAX_JOB_DURATION_SECONDS", "1800.0"))
    
    MAX_SCRIPT_LENGTH: int = int(os.getenv("MAX_SCRIPT_LENGTH", "60000"))
    MAX_NARRATION_LENGTH: int = int(os.getenv("MAX_NARRATION_LENGTH", "10000"))
    MIN_VISUAL_DESCRIPTION_LENGTH: int = int(os.getenv("MIN_VISUAL_DESCRIPTION_LENGTH", "3"))
    MAX_VISUAL_DESCRIPTION_LENGTH: int = int(os.getenv("MAX_VISUAL_DESCRIPTION_LENGTH", "500"))

    # Segmentation & Speech Rate Defaults
    DEFAULT_WORDS_PER_MINUTE: int = int(os.getenv("DEFAULT_WORDS_PER_MINUTE", "150"))
    MIN_WORDS_PER_SCENE: int = int(os.getenv("MIN_WORDS_PER_SCENE", "3"))
    TARGET_WORDS_PER_SCENE: int = int(os.getenv("TARGET_WORDS_PER_SCENE", "18"))
    MAX_WORDS_PER_SCENE: int = int(os.getenv("MAX_WORDS_PER_SCENE", "45"))

    # Audio Constraints
    MAX_AUDIO_FILE_SIZE_BYTES: int = int(os.getenv("MAX_AUDIO_FILE_SIZE_BYTES", str(50 * 1024 * 1024)))  # 50MB
    MAX_AUDIO_DURATION_SECONDS: float = float(os.getenv("MAX_AUDIO_DURATION_SECONDS", "900.0"))
    ALLOWED_AUDIO_EXTENSIONS: Set[str] = {".wav", ".mp3", ".aac", ".m4a", ".ogg", ".flac"}
    ALLOWED_AUDIO_MIME_TYPES: Set[str] = {
        "audio/wav", "audio/x-wav", "audio/wave",
        "audio/mpeg", "audio/mp3",
        "audio/aac", "audio/mp4", "audio/x-m4a",
        "audio/ogg", "audio/flac", "audio/x-flac"
    }

    # Media & Video Constraints
    MAX_MEDIA_DOWNLOAD_SIZE_BYTES: int = int(os.getenv("MAX_MEDIA_DOWNLOAD_SIZE_BYTES", str(100 * 1024 * 1024)))  # 100MB
    MIN_MEDIA_DURATION_SECONDS: float = float(os.getenv("MIN_MEDIA_DURATION_SECONDS", "0.5"))
    MIN_MEDIA_WIDTH: int = int(os.getenv("MIN_MEDIA_WIDTH", "320"))
    MIN_MEDIA_HEIGHT: int = int(os.getenv("MIN_MEDIA_HEIGHT", "240"))
    ALLOWED_VIDEO_EXTENSIONS: Set[str] = {".mp4", ".mov", ".webm", ".mkv"}
    MEDIA_DOWNLOAD_TIMEOUT_SECONDS: float = float(os.getenv("MEDIA_DOWNLOAD_TIMEOUT_SECONDS", "15.0"))

    # Security & SSRF Rules
    ALLOWED_URL_SCHEMES: Set[str] = {"http", "https"}
    URL_FETCH_TIMEOUT_SECONDS: float = float(os.getenv("URL_FETCH_TIMEOUT_SECONDS", "5.0"))
    MAX_URL_REDIRECTS: int = int(os.getenv("MAX_URL_REDIRECTS", "3"))
    ALLOW_PRIVATE_NETWORKS: bool = os.getenv("ALLOW_PRIVATE_NETWORKS", "false").lower() in ("true", "1", "yes")

    # Media Providers & Licensing
    PEXELS_API_KEY: str = os.getenv("PEXELS_API_KEY", "")
    PIXABAY_API_KEY: str = os.getenv("PIXABAY_API_KEY", "58143162-0e7cd37c74b9ab500f3882602")
    ENABLE_REMOTE_PROVIDERS: bool = os.getenv("ENABLE_REMOTE_PROVIDERS", "false").lower() in ("true", "1", "yes")
    DEFAULT_MEDIA_PROVIDER: str = os.getenv("DEFAULT_MEDIA_PROVIDER", "local_cc0")
    ALLOWED_LICENSES: Set[str] = {
        "CC0", "CC0-1.0", "Public Domain", "CC-BY-4.0", "CC-BY-3.0", "Pexels License", "Pixabay License"
    }
    PROHIBITED_LICENSES: Set[str] = {
        "CC-BY-NC", "CC-BY-ND", "CC-BY-NC-ND", "CC-BY-NC-SA",
        "All Rights Reserved", "Unknown", "Editorial Use Only"
    }

    # Dimensions
    ASPECT_RATIOS = {
        "16:9": (1920, 1080),
        "9:16": (1080, 1920),
        "1:1": (1080, 1080)
    }

    # Process Governance & Timeouts
    FFMPEG_SCENE_TIMEOUT: float = float(os.getenv("FFMPEG_SCENE_TIMEOUT", "60.0"))
    FFMPEG_TOTAL_TIMEOUT: float = float(os.getenv("FFMPEG_TOTAL_TIMEOUT", "1800.0"))
    MIN_DISK_FREE_BYTES: int = int(os.getenv("MIN_DISK_FREE_BYTES", str(500 * 1024 * 1024)))  # 500MB minimum disk free

    # Internal Files Blacklist
    FORBIDDEN_FILENAMES: Set[str] = {
        "job_state.json", "jobs.db", "jobs.db-journal", "jobs.db-wal", "jobs.db-shm",
        ".env", "web.config", "app.py", "main.py"
    }

settings = Settings()
settings.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
