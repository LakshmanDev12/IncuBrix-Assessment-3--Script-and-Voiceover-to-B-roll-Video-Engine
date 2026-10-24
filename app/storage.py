from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.database import get_db, init_db
from app.db.models import JobRecord

VALID_TRANSITIONS: Dict[str, Set[str]] = {
    "queued": {"running", "failed", "cancelled"},
    "running": {"running", "completed", "failed", "cancelled"},
    "failed": {"queued"},  # Allows bounded retry re-queueing
    "completed": set(),    # Terminal state
    "cancelled": set()     # Terminal state
}


class InvalidStateTransitionError(ValueError):
    """Raised when an illegal lifecycle transition is attempted."""
    def __init__(self, current_status: str, target_status: str):
        super().__init__(f"Cannot transition job from '{current_status}' to '{target_status}'.")
        self.current_status = current_status
        self.target_status = target_status


class JobStore:
    def __init__(self):
        init_db()

    def create_job(
        self,
        job_id: str,
        initial_data: Dict[str, Any],
        idempotency_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """Atomically inserts a new job record with optional idempotency key."""
        now = datetime.now(timezone.utc)
        record = JobRecord(
            job_id=job_id,
            idempotency_key=idempotency_key,
            title=initial_data["title"],
            status="queued",
            current_stage="queued",
            progress=0.0,
            stage_message=initial_data.get("stage_message", "Job accepted and queued for processing."),
            aspect_ratio=initial_data["aspect_ratio"],
            resolution=initial_data["resolution"],
            duration_seconds=float(initial_data["duration_seconds"]),
            scenes_count=int(initial_data["scenes_count"]),
            audio_source=initial_data.get("audio_source", "none"),
            audio_url=initial_data.get("audio_url"),
            auto_rebalance_scenes=bool(initial_data.get("auto_rebalance_scenes", False)),
            request_payload={"scenes": initial_data.get("scenes", [])},
            audio_details=initial_data.get("audio_details"),
            created_at_utc=now,
            updated_at_utc=now
        )
        with get_db() as db:
            db.add(record)
            db.flush()
            return record.to_dict()

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a job by its unique UUID."""
        with get_db() as db:
            record = db.query(JobRecord).filter(JobRecord.job_id == job_id).first()
            return record.to_dict() if record else None

    def get_job_by_idempotency_key(self, idempotency_key: str) -> Optional[Dict[str, Any]]:
        """Finds existing job by its client-supplied or content-derived idempotency key."""
        if not idempotency_key:
            return None
        with get_db() as db:
            record = db.query(JobRecord).filter(JobRecord.idempotency_key == idempotency_key).first()
            return record.to_dict() if record else None

    def update_job(self, job_id: str, **kwargs) -> Optional[Dict[str, Any]]:
        """Updates arbitrary mutable fields on a job."""
        with get_db() as db:
            record = db.query(JobRecord).filter(JobRecord.job_id == job_id).first()
            if not record:
                return None
            for key, val in kwargs.items():
                if hasattr(record, key):
                    setattr(record, key, val)
            record.updated_at_utc = datetime.now(timezone.utc)
            db.flush()
            return record.to_dict()

    def transition_state(
        self,
        job_id: str,
        to_status: str,
        to_stage: Optional[str] = None,
        progress: Optional[float] = None,
        stage_message: Optional[str] = None,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
        error_details: Optional[Any] = None,
        manifest: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Enforces lifecycle state transitions, validates against illegal transitions,
        and manages timestamps and error payloads atomically.
        """
        with get_db() as db:
            record = db.query(JobRecord).filter(JobRecord.job_id == job_id).with_for_update().first()
            if not record:
                raise ValueError(f"Job '{job_id}' not found.")

            current = record.status
            # Allow progress updates within the same status
            if current != to_status and to_status not in VALID_TRANSITIONS.get(current, set()):
                raise InvalidStateTransitionError(current, to_status)

            now = datetime.now(timezone.utc)
            record.status = to_status
            record.updated_at_utc = now

            if to_stage is not None:
                record.current_stage = to_stage
            if progress is not None:
                record.progress = max(0.0, min(100.0, float(progress)))
            if stage_message is not None:
                record.stage_message = stage_message

            # Lifecycle timestamps
            if to_status == "running" and record.started_at_utc is None:
                record.started_at_utc = now
            elif to_status == "completed":
                record.completed_at_utc = now
                record.progress = 100.0
                if manifest is not None:
                    record.manifest = manifest
            elif to_status == "failed":
                record.error_code = error_code or "INTERNAL_ERROR"
                record.error_message = error_message or "An error occurred during execution."
                record.error_details = error_details
            elif to_status == "cancelled":
                record.cancelled_at_utc = now

            db.flush()
            return record.to_dict()

    def cancel_job(self, job_id: str) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Requests cancellation of an active or queued job.
        Returns (success: bool, message: str, job_dict: Optional[dict]).
        """
        with get_db() as db:
            record = db.query(JobRecord).filter(JobRecord.job_id == job_id).with_for_update().first()
            if not record:
                return False, "Job not found.", None

            current = record.status
            if current in ("completed", "failed"):
                return False, f"Cannot cancel job in terminal state '{current}'.", record.to_dict()
            if current == "cancelled":
                return True, "Job is already cancelled.", record.to_dict()

            now = datetime.now(timezone.utc)
            record.status = "cancelled"
            record.current_stage = "cancelled"
            record.stage_message = "Job cancelled by user request."
            record.cancelled_at_utc = now
            record.updated_at_utc = now

            db.flush()
            return True, "Job successfully cancelled.", record.to_dict()

    def recover_stuck_jobs(self) -> List[str]:
        """
        Recovers jobs left in 'running' state after an unexpected server restart/crash.
        Re-queues them with exponential retry count if retries remain; fails them otherwise.
        Purges any partially rendered video.mp4 or temp files from interrupted runs.
        """
        import shutil
        recovered_ids = []
        now = datetime.now(timezone.utc)
        with get_db() as db:
            stuck = db.query(JobRecord).filter(JobRecord.status == "running").all()
            for rec in stuck:
                rec.updated_at_utc = now
                if rec.retry_count < rec.max_retries:
                    rec.retry_count += 1
                    rec.status = "queued"
                    rec.current_stage = "queued"
                    rec.stage_message = f"Recovered after server restart (retry {rec.retry_count}/{rec.max_retries})."
                else:
                    rec.status = "failed"
                    rec.current_stage = "failed"
                    rec.error_code = "PROCESS_CRASH_TERMINATION"
                    rec.error_message = f"Job failed: process was terminated unexpectedly and exceeded maximum retries ({rec.max_retries})."

                # Purge incomplete outputs or temp artifacts left behind by the crashed process
                job_dir = settings.OUTPUT_DIR / rec.job_id
                if job_dir.exists():
                    partial_video = job_dir / "video.mp4"
                    if partial_video.exists():
                        try:
                            partial_video.unlink()
                        except OSError:
                            pass
                    temp_dir = job_dir / "temp"
                    if temp_dir.exists():
                        shutil.rmtree(temp_dir, ignore_errors=True)

                recovered_ids.append(rec.job_id)
            db.flush()
        return recovered_ids

    def list_jobs(self, status: Optional[str] = None, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """Lists jobs with optional status filter, sorted newest first."""
        with get_db() as db:
            query = db.query(JobRecord)
            if status:
                query = query.filter(JobRecord.status == status)
            records = query.order_by(JobRecord.created_at_utc.desc()).offset(offset).limit(limit).all()
            return [r.to_dict() for r in records]

    def count_jobs(self, status: Optional[str] = None) -> int:
        """Counts total jobs matching an optional status filter."""
        with get_db() as db:
            query = db.query(JobRecord)
            if status:
                query = query.filter(JobRecord.status == status)
            return query.count()


job_store = JobStore()
