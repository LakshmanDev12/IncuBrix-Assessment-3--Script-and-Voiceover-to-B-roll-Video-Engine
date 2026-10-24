import logging
from pathlib import Path
import shutil
from typing import List, Optional, Tuple
import uuid

from fastapi import UploadFile

from app.config import settings
from app.schemas import Scene
from app.services.audio_downloader import download_audio_from_url
from app.services.audio_inspector import (
    AudioInspectionError,
    AudioInspectionResult,
    inspect_audio_file,
)


logger = logging.getLogger("video_engine.ingestion")


class IngestionError(ValueError):
    """Raised when ingestion validation fails."""
    def __init__(self, message: str, code: str = "INGESTION_ERROR"):
        super().__init__(message)
        self.code = code
        self.message = message


class JobWorkspace:
    """Manages isolated job directories and enforces strict separation between temporary and final assets."""
    def __init__(self, job_id: str, base_dir: Path = settings.OUTPUT_DIR):
        self.job_id = job_id
        self.root = base_dir / job_id
        self.temp_dir = self.root / "temp"
        self.audio_dir = self.root / "audio"
        self.artifacts_dir = self.root / "artifacts"

        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)

    @property
    def job_dir(self) -> Path:
        return self.root

    def cleanup_temp(self):
        """Removes temporary working directory and intermediate files."""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)
            self.temp_dir.mkdir(parents=True, exist_ok=True)

    def cleanup_all(self):
        """Removes the entire job folder on catastrophic failure."""
        if self.root.exists():
            shutil.rmtree(self.root, ignore_errors=True)


class IngestionService:
    def __init__(self, base_dir: Path = settings.OUTPUT_DIR):
        self.base_dir = base_dir

    def get_workspace(self, job_id: str) -> JobWorkspace:
        return JobWorkspace(job_id, self.base_dir)

    async def ingest_audio_upload(self, job_id: str, upload_file: UploadFile) -> Tuple[Path, AudioInspectionResult]:
        """
        Receives an uploaded audio file, verifies size boundaries, inspects container & codecs,
        and moves the validated audio file into the job's dedicated audio storage.
        """
        workspace = self.get_workspace(job_id)
        temp_dest = workspace.temp_dir / f"upload_{uuid.uuid4().hex[:8]}.tmp"

        total_bytes = 0
        try:
            with open(temp_dest, "wb") as f:
                while chunk := await upload_file.read(65536):
                    total_bytes += len(chunk)
                    if total_bytes > settings.MAX_AUDIO_FILE_SIZE_BYTES:
                        raise IngestionError(
                            f"Uploaded audio file exceeds maximum size limit of {settings.MAX_AUDIO_FILE_SIZE_BYTES} bytes.",
                            code="FILE_TOO_LARGE"
                        )
                    f.write(chunk)

            if total_bytes == 0:
                raise IngestionError("Uploaded audio file is empty (0 bytes).", code="EMPTY_FILE")

            inspection = inspect_audio_file(temp_dest)
            self._validate_audio_duration(inspection.duration_seconds)

            final_dest = workspace.audio_dir / f"voiceover.{inspection.format_name}"
            shutil.move(str(temp_dest), str(final_dest))
            return final_dest, inspection

        finally:
            workspace.cleanup_temp()

    def ingest_audio_url(self, job_id: str, audio_url: str) -> Tuple[Path, AudioInspectionResult]:
        """
        Downloads external audio from a validated URL, inspects codecs and duration,
        and saves it to the job's isolated audio folder.
        """
        workspace = self.get_workspace(job_id)
        temp_dest = workspace.temp_dir / f"download_{uuid.uuid4().hex[:8]}.tmp"

        try:
            download_audio_from_url(
                url_str=audio_url,
                dest_path=temp_dest,
                max_bytes=settings.MAX_AUDIO_FILE_SIZE_BYTES,
                timeout_seconds=settings.URL_FETCH_TIMEOUT_SECONDS
            )

            inspection = inspect_audio_file(temp_dest)
            self._validate_audio_duration(inspection.duration_seconds)

            final_dest = workspace.audio_dir / f"voiceover.{inspection.format_name}"
            shutil.move(str(temp_dest), str(final_dest))
            return final_dest, inspection

        finally:
            workspace.cleanup_temp()

    def _validate_audio_duration(self, duration: float):
        if duration < settings.MIN_JOB_DURATION_SECONDS:
            raise IngestionError(
                f"Audio duration ({duration:.2f}s) is shorter than minimum allowed ({settings.MIN_JOB_DURATION_SECONDS}s).",
                code="DURATION_TOO_SHORT"
            )
        if duration > settings.MAX_AUDIO_DURATION_SECONDS:
            raise IngestionError(
                f"Audio duration ({duration:.2f}s) exceeds maximum allowed ({settings.MAX_AUDIO_DURATION_SECONDS}s).",
                code="DURATION_TOO_LONG"
            )

    @staticmethod
    def validate_and_align_scenes(
        scenes: List[Scene],
        audio_duration: Optional[float] = None,
        tolerance_seconds: float = 2.0,
        auto_rebalance: bool = False,
        strict_match: bool = True,
        **kwargs
    ) -> List[Scene]:
        """
        Validates scene count and pacing. If an audio voiceover duration is present,
        verifies that scene durations match the audio or rescales them proportionally if requested.
        """
        if not scenes:
            raise IngestionError("At least one scene is required.", code="EMPTY_SCENES")

        total_scene_duration = sum(s.duration_seconds for s in scenes)

        if audio_duration is None:
            return scenes

        diff = abs(total_scene_duration - audio_duration)
        if diff <= tolerance_seconds:
            return scenes

        if not auto_rebalance:
            if strict_match:
                raise IngestionError(
                    f"Scene duration total ({total_scene_duration:.2f}s) does not match voiceover audio duration ({audio_duration:.2f}s). "
                    f"Difference of {diff:.2f}s exceeds tolerance of {tolerance_seconds:.2f}s. "
                    "Enable 'auto_rebalance_scenes' to synchronize scene durations to the voiceover audio track automatically.",
                    code="DURATION_MISMATCH"
                )
            logger.info(
                f"Scene duration total ({total_scene_duration:.2f}s) differs from audio duration ({audio_duration:.2f}s). "
                f"strict_match is False; proceeding without fixed audio constraint."
            )
            return scenes

        # Rescale scene durations proportionally to fit voiceover
        scale_factor = audio_duration / total_scene_duration
        rebalanced: List[Scene] = []
        running_total = 0.0

        for i, sc in enumerate(scenes):
            if i == len(scenes) - 1:
                # Last scene absorbs any rounding discrepancy
                new_dur = round(audio_duration - running_total, 3)
            else:
                new_dur = round(sc.duration_seconds * scale_factor, 3)
                running_total += new_dur

            # Boundary check on rebalanced scene
            if new_dur < settings.MIN_SCENE_DURATION_SECONDS:
                new_dur = settings.MIN_SCENE_DURATION_SECONDS

            rebalanced.append(Scene(
                narration=sc.narration,
                duration_seconds=new_dur,
                visual_description=sc.visual_description,
                source_url=sc.source_url,
                license_name=sc.license_name,
                attribution=sc.attribution,
                media_metadata=sc.media_metadata
            ))

        return rebalanced


ingestion_service = IngestionService()
