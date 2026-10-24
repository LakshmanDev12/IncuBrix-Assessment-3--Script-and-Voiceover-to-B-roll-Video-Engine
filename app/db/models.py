from datetime import datetime, timezone
from typing import Any, Dict, Optional
from sqlalchemy import Boolean, Column, DateTime, Float, Integer, JSON, String, Text

from app.db.database import Base


class JobRecord(Base):
    __tablename__ = "render_jobs"

    job_id = Column(String(36), primary_key=True, index=True)
    idempotency_key = Column(String(64), unique=True, index=True, nullable=True)
    title = Column(String(120), nullable=False)
    status = Column(String(20), nullable=False, default="queued", index=True)
    current_stage = Column(String(40), nullable=False, default="queued")
    progress = Column(Float, nullable=False, default=0.0)
    stage_message = Column(String(255), nullable=False, default="Job submitted and queued.")
    
    aspect_ratio = Column(String(10), nullable=False)
    resolution = Column(String(10), nullable=False)
    duration_seconds = Column(Float, nullable=False)
    scenes_count = Column(Integer, nullable=False)
    audio_source = Column(String(20), nullable=False, default="none")
    audio_url = Column(Text, nullable=True)
    auto_rebalance_scenes = Column(Boolean, nullable=False, default=False)
    
    # Serialized structures
    request_payload = Column(JSON, nullable=False)
    audio_details = Column(JSON, nullable=True)
    
    # Errors & Retries
    error_code = Column(String(50), nullable=True)
    error_message = Column(Text, nullable=True)
    error_details = Column(JSON, nullable=True)
    retry_count = Column(Integer, nullable=False, default=0)
    max_retries = Column(Integer, nullable=False, default=3)

    # Timestamps
    created_at_utc = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at_utc = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    started_at_utc = Column(DateTime, nullable=True)
    completed_at_utc = Column(DateTime, nullable=True)
    cancelled_at_utc = Column(DateTime, nullable=True)

    # Artifact metadata
    manifest = Column(JSON, nullable=True)

    def to_dict(self) -> Dict[str, Any]:
        """Serializes JobRecord into a clean, sanitized dictionary without leaking host paths."""
        err = None
        if self.error_code or self.error_message:
            err = {
                "error_code": self.error_code,
                "message": self.error_message,
                "details": self.error_details
            }

        return {
            "job_id": self.job_id,
            "idempotency_key": self.idempotency_key,
            "title": self.title,
            "status": self.status,
            "progress": round(self.progress, 1),
            "current_stage": self.current_stage,
            "stage_message": self.stage_message,
            "aspect_ratio": self.aspect_ratio,
            "resolution": self.resolution,
            "duration_seconds": round(self.duration_seconds, 3),
            "scenes_count": self.scenes_count,
            "audio_source": self.audio_source,
            "audio_url": self.audio_url,
            "audio_details": self.audio_details,
            "auto_rebalance_scenes": self.auto_rebalance_scenes,
            "scenes": self.request_payload.get("scenes", []),
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "created_at_utc": self.created_at_utc.isoformat() if self.created_at_utc else None,
            "updated_at_utc": self.updated_at_utc.isoformat() if self.updated_at_utc else None,
            "started_at_utc": self.started_at_utc.isoformat() if self.started_at_utc else None,
            "completed_at_utc": self.completed_at_utc.isoformat() if self.completed_at_utc else None,
            "cancelled_at_utc": self.cancelled_at_utc.isoformat() if self.cancelled_at_utc else None,
            "error": err,
            "manifest": self.manifest,
            # Virtual output_dir reference maintained for internal filesystem lookup
            "output_dir": f"jobs/{self.job_id}"
        }
