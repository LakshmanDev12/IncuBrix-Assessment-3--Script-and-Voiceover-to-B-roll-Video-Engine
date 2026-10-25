import asyncio
import re
import shutil
from datetime import datetime, timezone
import logging
from pathlib import Path
import traceback
from typing import Optional

from app.config import settings
from app.schemas import Scene
from app.services.ingestion import ingestion_service
from app.services.media_selector import media_selector
from app.services.subtitles import write_subtitle_files
from app.services.timeline_manifest import build_manifest, build_timeline, write_timeline_and_manifest
from app.services.video_composer import RenderingCancelledError, video_composer
from app.storage import job_store

logger = logging.getLogger("video_engine.worker")


class BackgroundWorker:
    """
    Robust in-process asynchronous queue worker for video generation jobs.
    
    Architectural characteristics & constraints:
    - Simplicity & Local Demonstrability: Runs directly within the FastAPI event loop without
      requiring external message brokers (Redis/RabbitMQ/Celery) for evaluation.
    - Persistent Crash Recovery: SQLite-backed jobs table guarantees queued/interrupted jobs
      survive process termination.
    - Limits of In-Process Background Execution:
      1. Horizontal Pod Scalability: In-process workers do not distribute jobs across multiple
         container replicas. Multi-node clusters require an external message queue.
      2. Event Loop Responsiveness: Heavy CPU operations (FFmpeg encoding) must be delegated to
         subprocesses or worker threads to prevent blocking HTTP endpoints.
      3. Process Fate Sharing: If the FastAPI container terminates forcefully (OOM / SIGKILL),
         currently running jobs will be halted and must be recovered on restart.
    """
    def __init__(self, concurrency: int = 1):
        self.concurrency = concurrency
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._tasks: list[asyncio.Task] = []
        self._running = False

    async def start(self):
        """Starts worker consumer tasks and initiates crash recovery."""
        if self._running:
            return
        self._running = True

        # 1. Recover any abandoned jobs from previous crashes
        recovered = job_store.recover_stuck_jobs()
        if recovered:
            logger.warning(f"Recovered {len(recovered)} stuck jobs on worker startup: {recovered}")
            for jid in recovered:
                await self._queue.put(jid)

        # 2. Launch concurrent consumer workers
        for i in range(self.concurrency):
            task = asyncio.create_task(self._worker_loop(worker_index=i))
            self._tasks.append(task)
        logger.info(f"BackgroundWorker initialized with {self.concurrency} concurrent runners.")

    async def stop(self):
        """Signals workers to stop and waits for in-flight tasks to wind down."""
        self._running = False
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        logger.info("BackgroundWorker successfully stopped.")

    async def enqueue(self, job_id: str):
        """Enqueues a job ID for background processing."""
        await self._queue.put(job_id)

    async def _worker_loop(self, worker_index: int):
        while self._running:
            try:
                job_id = await self._queue.get()
            except asyncio.CancelledError:
                break

            try:
                await self._process_job(job_id)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(f"[Worker {worker_index}] Unexpected top-level failure for job '{job_id}': {exc}")
            finally:
                self._queue.task_done()

    async def _process_job(self, job_id: str):
        job = job_store.get_job(job_id)
        if not job or job.get("status") == "cancelled":
            return

        workspace = ingestion_service.get_workspace(job_id)

        try:
            # 1. Transition to running: validating
            job = job_store.transition_state(
                job_id=job_id,
                to_status="running",
                to_stage="validating",
                progress=15.0,
                stage_message="Validating input script, scenes, and media assets."
            )

            if self._check_cancelled(job_id):
                return

            scenes_raw = job.get("scenes", [])
            scene_objs = [Scene(**s) if isinstance(s, dict) else s for s in scenes_raw]

            # Stage 2: Processing Media & Audio
            job_store.transition_state(
                job_id=job_id,
                to_status="running",
                to_stage="processing_media",
                progress=35.0,
                stage_message="Selecting candidate B-roll clips and checking licensing."
            )
            if self._check_cancelled(job_id):
                return

            selection_result = media_selector.select_media_for_scenes(
                job_id=job_id,
                scenes=scene_objs,
                allow_repeated_clips=False,
                target_aspect_ratio=job.get("aspect_ratio", "16:9")
            )
            selected_clips_data = [sc.to_dict() for sc in selection_result.selected_clips]

            # Stage 3: Timeline Assembly
            job_store.transition_state(
                job_id=job_id,
                to_status="running",
                to_stage="assembling_timeline",
                progress=55.0,
                stage_message="Assembling scene cuts, visual descriptions, and timing metadata."
            )
            if self._check_cancelled(job_id):
                return

            timeline_data = build_timeline(
                job_id=job_id,
                title=job.get("title", "Untitled Video"),
                scenes=scenes_raw,
                selected_clips=selected_clips_data,
                aspect_ratio=job.get("aspect_ratio", "16:9"),
                resolution=job.get("resolution", "1080p"),
                fps=30,
                audio_source=job.get("audio_source", "none")
            )

            # Stage 4: Composition & Rendering
            job_store.transition_state(
                job_id=job_id,
                to_status="running",
                to_stage="rendering",
                progress=75.0,
                stage_message="Rendering 1080p video composition and multiplexing audio."
            )
            if self._check_cancelled(job_id):
                return

            # Check for voiceover audio file
            audio_path = None
            if workspace.audio_dir.exists():
                for f in workspace.audio_dir.iterdir():
                    if f.is_file() and f.name.startswith("voiceover"):
                        audio_path = f
                        break

            # If no audio was provided, synthesize narration speech from scenes text (TTS)
            if not audio_path:
                try:
                    from app.services.tts import generate_voiceover_for_scenes
                    tts_dest = workspace.audio_dir / "voiceover.wav"
                    tot_dur = sum(float(s.get("duration_seconds", 3.0)) for s in scenes_raw)
                    synth_path = await generate_voiceover_for_scenes(scenes_raw, tts_dest, tot_dur)
                    if synth_path and synth_path.exists():
                        audio_path = synth_path
                        logger.info(f"Generated TTS voiceover for job '{job_id}': {audio_path}")
                except Exception as tts_err:
                    logger.warning(f"TTS synthesis skipped or failed for job '{job_id}': {tts_err}")

            # Generate captions (.srt and .vtt) BEFORE composition so they can be burned into frames
            srt_path, vtt_path = write_subtitle_files(
                output_dir=workspace.job_dir,
                scenes=scenes_raw,
                base_name="captions"
            )

            video_path = workspace.job_dir / "video.mp4"
            composition_meta = await video_composer.compose_video(
                job_id=job_id,
                scenes=scenes_raw,
                selected_clips=selected_clips_data,
                output_path=video_path,
                aspect_ratio=job.get("aspect_ratio", "16:9"),
                resolution=job.get("resolution", "1080p"),
                audio_path=audio_path,
                subtitle_path=srt_path,
                cancel_check=lambda: self._check_cancelled(job_id)
            )

            # Ensure video is also available under the project title
            clean_title = re.sub(r'[\\/*?:"<>|]', "", job.get("title", "video")).strip() or "video"
            named_video_path = workspace.job_dir / f"{clean_title}.mp4"
            if named_video_path != video_path and video_path.exists():
                try:
                    shutil.copy2(video_path, named_video_path)
                    logger.info(f"Created project-named video artifact: {named_video_path.name}")
                except Exception as exc:
                    logger.warning(f"Could not copy named video file: {exc}")

            # Stage 5: Artifact Generation
            job_store.transition_state(
                job_id=job_id,
                to_status="running",
                to_stage="generating_artifacts",
                progress=90.0,
                stage_message="Compiling final manifest, timeline, and subtitle tracks."
            )
            if self._check_cancelled(job_id):
                return

            # Build and write timeline & manifest
            width, height = video_composer.get_dimensions(
                aspect_ratio=job.get("aspect_ratio", "16:9"),
                resolution=job.get("resolution", "1080p")
            )
            attr_summary = selection_result.attribution_ledger.to_dict()

            manifest_data = build_manifest(
                job_id=job_id,
                title=job.get("title", "Untitled Video"),
                status="completed",
                aspect_ratio=job.get("aspect_ratio", "16:9"),
                resolution=job.get("resolution", "1080p"),
                width=width,
                height=height,
                duration_seconds=float(job.get("duration_seconds", 0.0)),
                fps=30,
                audio_source=job.get("audio_source", "none"),
                audio_details=job.get("audio_details"),
                artifacts_dir=workspace.job_dir,
                scenes_count=len(scenes_raw),
                attribution_summary=attr_summary,
                rendering_engine=composition_meta.get("rendering_engine", "ffmpeg"),
                quality_verification=composition_meta.get("quality_verification"),
                created_at_utc=job.get("created_at_utc")
            )

            write_timeline_and_manifest(
                output_dir=workspace.job_dir,
                timeline_data=timeline_data,
                manifest_data=manifest_data
            )

            # Stage 6: Completion
            job_store.transition_state(
                job_id=job_id,
                to_status="completed",
                to_stage="completed",
                progress=100.0,
                stage_message="Video processing completed successfully.",
                manifest=manifest_data
            )
            workspace.cleanup_temp()

        except RenderingCancelledError:
            logger.info(f"Job '{job_id}' rendering was cancelled.")
            workspace.cleanup_temp()
            return
        except Exception as exc:
            # Handle failure with bounded retry backoff
            await self._handle_job_failure(job_id, exc)

    def _check_cancelled(self, job_id: str) -> bool:
        current_job = job_store.get_job(job_id)
        if current_job and current_job.get("status") == "cancelled":
            ingestion_service.get_workspace(job_id).cleanup_temp()
            return True
        return False

    async def _handle_job_failure(self, job_id: str, exc: Exception):
        job = job_store.get_job(job_id)
        if not job:
            return

        workspace = ingestion_service.get_workspace(job_id)
        workspace.cleanup_temp()

        retry_count = int(job.get("retry_count", 0))
        max_retries = int(job.get("max_retries", 3))

        # Sanitize error message to prevent leaking host paths
        raw_msg = str(exc)
        sanitized_msg = self._sanitize_error_text(raw_msg)

        if retry_count < max_retries:
            next_retry = retry_count + 1
            # Bounded exponential backoff: 0.2s * 2^(retry-1)
            backoff_delay = min(5.0, 0.2 * (2 ** (next_retry - 1)))
            logger.warning(f"Job '{job_id}' encountered transient failure. Scheduling retry {next_retry}/{max_retries} in {backoff_delay}s: {sanitized_msg}")

            job_store.update_job(
                job_id=job_id,
                retry_count=next_retry,
                status="queued",
                current_stage="queued",
                stage_message=f"Transient failure occurred. Queued for retry {next_retry}/{max_retries}."
            )
            await asyncio.sleep(backoff_delay)
            await self._queue.put(job_id)
        else:
            logger.error(f"Job '{job_id}' permanently failed after {max_retries} retries: {sanitized_msg}")
            job_store.transition_state(
                job_id=job_id,
                to_status="failed",
                to_stage="failed",
                progress=0.0,
                stage_message=f"Job failed after {max_retries} attempts: {sanitized_msg}",
                error_code="PROCESSING_ERROR",
                error_message=sanitized_msg
            )

    @staticmethod
    def _sanitize_error_text(text: str) -> str:
        """Strips internal system directory paths from error messages."""
        output_dir_str = str(settings.OUTPUT_DIR)
        sanitized = text.replace(output_dir_str, "[DATA_DIR]")
        root_dir_str = str(settings.OUTPUT_DIR.parent)
        sanitized = sanitized.replace(root_dir_str, "[APP_ROOT]")
        # Strip Windows drive letters like E:\ or C:\
        import re
        sanitized = re.sub(r"[A-Za-z]:\\[\w\-\\]+", "[INTERNAL_PATH]", sanitized)
        return sanitized


background_worker = BackgroundWorker(concurrency=1)
