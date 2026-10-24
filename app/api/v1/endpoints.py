from datetime import datetime, timezone
import hashlib
import json
import mimetypes
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid

from fastapi import APIRouter, File, Form, Header, HTTPException, Request, Response, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import ValidationError

from app.config import settings
from app.schemas import (
    ArtifactItem,
    ArtifactsResponse,
    AudioInputMetadata,
    CancelJobResponse,
    CandidateMediaItem,
    JobLinks,
    JobResponse,
    JobListResponse,
    LimitsResponse,
    MediaRankingRequest,
    MediaRankingResponse,
    MediaSearchResponse,
    ProviderItemResponse,
    RenderJobCreate,
    Scene,
    SegmentationRequest,
    SegmentationResponse,
)
from app.security import (
    SecurityValidationError,
    probe_and_validate_audio_url,
    validate_safe_filename,
    validate_url_security,
)
from app.services.audio_inspector import AudioInspectionError
from app.services.ingestion import IngestionError, ingestion_service
from app.services.providers import provider_registry
from app.services.relevance import get_relevance_ranker
from app.services.segmentation import SegmentationConfig, SegmentationError, scene_segmenter
from app.services.worker import background_worker
from app.storage import job_store

router = APIRouter(prefix="/v1", tags=["Video Engine v1"])


def calculate_sha256(file_path: Path) -> str:
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def format_job_response(job: Dict[str, Any]) -> JobResponse:
    job_id = job["job_id"]
    audio_details = job.get("audio_details")
    audio_meta = AudioInputMetadata(**audio_details) if audio_details else None

    return JobResponse(
        job_id=job_id,
        title=job.get("title", "Untitled Video"),
        status="processing" if job.get("status") == "running" else job.get("status", "queued"),
        progress=float(job.get("progress", 0.0)),
        current_stage=job.get("current_stage", "queued"),
        stage_message=job.get("stage_message", "Job is in queue."),
        aspect_ratio=job.get("aspect_ratio", "16:9"),
        resolution=job.get("resolution", "1080p"),
        duration_seconds=float(job.get("duration_seconds", 0.0)),
        scenes_count=int(job.get("scenes_count", 0)),
        audio_source=job.get("audio_source", "none"),
        audio_details=audio_meta,
        auto_rebalance_scenes=job.get("auto_rebalance_scenes", False),
        created_at_utc=job.get("created_at_utc", datetime.now(timezone.utc).isoformat()),
        started_at_utc=job.get("started_at_utc"),
        completed_at_utc=job.get("completed_at_utc"),
        error=job.get("error"),
        manifest=job.get("manifest"),
        links=JobLinks(
            self=f"/v1/jobs/{job_id}",
            status=f"/v1/jobs/{job_id}",
            artifacts=f"/v1/jobs/{job_id}/artifacts",
            cancel=f"/v1/jobs/{job_id}/cancel" if job.get("status") not in ("completed", "failed", "cancelled") else None
        )
    )


@router.get("/limits", response_model=LimitsResponse, summary="Get active engine validation limits")
def get_limits():
    """Returns active runtime constraints and validation boundaries."""
    return LimitsResponse(
        min_title_length=settings.MIN_TITLE_LENGTH,
        max_title_length=settings.MAX_TITLE_LENGTH,
        min_scenes=settings.MIN_SCENES,
        max_scenes=settings.MAX_SCENES,
        min_scene_duration_seconds=settings.MIN_SCENE_DURATION_SECONDS,
        max_scene_duration_seconds=settings.MAX_SCENE_DURATION_SECONDS,
        min_job_duration_seconds=settings.MIN_JOB_DURATION_SECONDS,
        max_job_duration_seconds=settings.MAX_JOB_DURATION_SECONDS,
        max_audio_file_size_bytes=settings.MAX_AUDIO_FILE_SIZE_BYTES,
        max_audio_duration_seconds=settings.MAX_AUDIO_DURATION_SECONDS,
        allowed_aspect_ratios=list(settings.ASPECT_RATIOS.keys()),
        allowed_resolutions=["1080p", "720p"],
        allowed_audio_extensions=list(settings.ALLOWED_AUDIO_EXTENSIONS)
    )


@router.post("/jobs", status_code=status.HTTP_202_ACCEPTED, response_model=JobResponse, summary="Create a new render job")
async def create_job(
    request: RenderJobCreate,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key")
):
    """
    Submits a validated script-to-video render job.
    Accepts scene definitions, aspect ratio, resolution, and optional public audio URL.
    Supports Idempotency-Key header or deterministic body fingerprint to avoid duplicate processing.
    """
    # 1. Check idempotency if client provided Idempotency-Key header
    if idempotency_key:
        existing = job_store.get_job_by_idempotency_key(idempotency_key)
        if existing:
            return format_job_response(existing)

    job_id = str(uuid.uuid4())
    audio_details = None
    audio_source = "none"
    processed_scenes = request.scenes

    # Handle external audio URL if provided
    if request.audio_url:
        try:
            audio_path, inspection = ingestion_service.ingest_audio_url(job_id, str(request.audio_url))
            audio_source = "url"
            audio_details = {
                "source_type": "url",
                "url": str(request.audio_url),
                "duration_seconds": inspection.duration_seconds,
                "codec": inspection.codec,
                "format_name": inspection.format_name,
                "sample_rate": inspection.sample_rate,
                "channels": inspection.channels,
                "bit_rate": inspection.bit_rate,
                "size_bytes": inspection.file_size_bytes
            }
            processed_scenes = ingestion_service.validate_and_align_scenes(
                scenes=request.scenes,
                audio_duration=inspection.duration_seconds,
                tolerance_seconds=2.0,
                auto_rebalance=request.auto_rebalance_scenes,
                strict_match=getattr(request, "strict_duration_match", True)
            )
        except IngestionError as ing_err:
            status_code = status.HTTP_422_UNPROCESSABLE_ENTITY if ing_err.code == "DURATION_MISMATCH" else status.HTTP_400_BAD_REQUEST
            raise HTTPException(
                status_code=status_code,
                detail={"error_code": ing_err.code, "message": ing_err.message}
            )
        except AudioInspectionError as aud_err:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error_code": aud_err.code, "message": aud_err.message}
            )
        except SecurityValidationError as sec_err:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error_code": sec_err.code, "message": sec_err.message}
            )

    total_duration = sum(s.duration_seconds for s in processed_scenes)
    now_iso = datetime.now(timezone.utc).isoformat()

    job_data = {
        "job_id": job_id,
        "title": request.title,
        "status": "queued",
        "progress": 0.0,
        "current_stage": "queued",
        "stage_message": "Job accepted and queued for processing.",
        "aspect_ratio": request.aspect_ratio,
        "resolution": request.resolution,
        "duration_seconds": round(total_duration, 3),
        "scenes_count": len(processed_scenes),
        "audio_source": audio_source,
        "audio_url": str(request.audio_url) if request.audio_url else None,
        "audio_details": audio_details,
        "auto_rebalance_scenes": request.auto_rebalance_scenes,
        "scenes": [s.model_dump(mode="json") for s in processed_scenes],
        "created_at_utc": now_iso,
        "output_dir": str(settings.OUTPUT_DIR / job_id)
    }

    created_job = job_store.create_job(job_id, job_data, idempotency_key=idempotency_key)
    await background_worker.enqueue(job_id)
    return format_job_response(created_job)


@router.post("/jobs/multipart", status_code=status.HTTP_202_ACCEPTED, response_model=JobResponse, summary="Create job with optional audio upload")
async def create_job_multipart(
    title: str = Form(default="Demo video"),
    aspect_ratio: str = Form(default="16:9"),
    resolution: str = Form(default="1080p"),
    scenes: str = Form(..., description="JSON string array of scenes"),
    audio_url: Optional[str] = Form(default=None),
    script: Optional[str] = Form(default=None),
    auto_rebalance_scenes: bool = Form(default=False),
    strict_match: bool = Form(default=True),
    strict_duration_match: Optional[bool] = Form(default=None),
    audio_file: Optional[UploadFile] = File(default=None),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key")
):
    """
    Submits a render job with either an uploaded audio file or a validated audio URL.
    Explicit rejection rule: Providing BOTH an uploaded audio file and an audio URL will result in HTTP 400.
    Supports Idempotency-Key header to prevent duplicate submissions.
    """
    if idempotency_key:
        existing = job_store.get_job_by_idempotency_key(idempotency_key)
        if existing and existing.get("status") in ("queued", "running", "completed"):
            return format_job_response(existing)

    # Check for ambiguous audio input
    if audio_file is not None and audio_url is not None and audio_url.strip() != "":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error_code": "AMBIGUOUS_AUDIO_INPUT",
                "message": "Ambiguous audio input: both 'audio_file' and 'audio_url' were provided. Please supply only one audio source."
            }
        )

    # Parse scenes JSON
    try:
        scenes_data = json.loads(scenes)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error_code": "INVALID_SCENES_JSON",
                "message": f"Malformed scenes JSON: {exc}"
            }
        )

    # Validate using Pydantic
    try:
        validated_request = RenderJobCreate(
            title=title,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            scenes=scenes_data,
            audio_url=audio_url.strip() if audio_url and audio_url.strip() else None,
            script=script,
            auto_rebalance_scenes=auto_rebalance_scenes
        )
    except ValidationError as err:
        errors = err.errors()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error_code": "VALIDATION_ERROR",
                "message": "Request payload failed schema validation.",
                "details": errors
            }
        )
    except SecurityValidationError as sec_err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error_code": sec_err.code,
                "message": sec_err.message
            }
        )

    job_id = str(uuid.uuid4())
    audio_source = "none"
    audio_details = None
    processed_scenes = validated_request.scenes

    # Handle uploaded audio file if provided
    if audio_file is not None:
        filename = audio_file.filename or "narration.wav"
        ext = Path(filename).suffix.lower()
        if ext not in settings.ALLOWED_AUDIO_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail={
                    "error_code": "UNSUPPORTED_AUDIO_FORMAT",
                    "message": f"Unsupported audio extension '{ext}'. Allowed extensions: {list(settings.ALLOWED_AUDIO_EXTENSIONS)}"
                }
            )

        try:
            audio_path, inspection = await ingestion_service.ingest_audio_upload(job_id, audio_file)
            audio_source = "upload"
            audio_details = {
                "source_type": "upload",
                "filename": filename,
                "duration_seconds": inspection.duration_seconds,
                "codec": inspection.codec,
                "format_name": inspection.format_name,
                "sample_rate": inspection.sample_rate,
                "channels": inspection.channels,
                "bit_rate": inspection.bit_rate,
                "size_bytes": inspection.file_size_bytes
            }
            use_strict = strict_duration_match if strict_duration_match is not None else strict_match
            processed_scenes = ingestion_service.validate_and_align_scenes(
                scenes=validated_request.scenes,
                audio_duration=inspection.duration_seconds,
                tolerance_seconds=2.0,
                auto_rebalance=auto_rebalance_scenes,
                strict_match=use_strict
            )
        except IngestionError as ing_err:
            status_code = status.HTTP_422_UNPROCESSABLE_ENTITY if ing_err.code == "DURATION_MISMATCH" else status.HTTP_400_BAD_REQUEST
            raise HTTPException(
                status_code=status_code,
                detail={"error_code": ing_err.code, "message": ing_err.message}
            )
        except AudioInspectionError as aud_err:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error_code": aud_err.code, "message": aud_err.message}
            )

    elif validated_request.audio_url:
        try:
            audio_path, inspection = ingestion_service.ingest_audio_url(job_id, str(validated_request.audio_url))
            audio_source = "url"
            audio_details = {
                "source_type": "url",
                "url": str(validated_request.audio_url),
                "duration_seconds": inspection.duration_seconds,
                "codec": inspection.codec,
                "format_name": inspection.format_name,
                "sample_rate": inspection.sample_rate,
                "channels": inspection.channels,
                "bit_rate": inspection.bit_rate,
                "size_bytes": inspection.file_size_bytes
            }
            processed_scenes = ingestion_service.validate_and_align_scenes(
                scenes=validated_request.scenes,
                audio_duration=inspection.duration_seconds,
                tolerance_seconds=2.0,
                auto_rebalance=auto_rebalance_scenes
            )
        except IngestionError as ing_err:
            status_code = status.HTTP_422_UNPROCESSABLE_ENTITY if ing_err.code == "DURATION_MISMATCH" else status.HTTP_400_BAD_REQUEST
            raise HTTPException(
                status_code=status_code,
                detail={"error_code": ing_err.code, "message": ing_err.message}
            )
        except AudioInspectionError as aud_err:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error_code": aud_err.code, "message": aud_err.message}
            )

    now_iso = datetime.now(timezone.utc).isoformat()
    total_duration = sum(s.duration_seconds for s in processed_scenes)

    job_data = {
        "job_id": job_id,
        "title": validated_request.title,
        "status": "queued",
        "progress": 0.0,
        "current_stage": "queued",
        "stage_message": "Job accepted and queued for processing.",
        "aspect_ratio": validated_request.aspect_ratio,
        "resolution": validated_request.resolution,
        "duration_seconds": round(total_duration, 3),
        "scenes_count": len(processed_scenes),
        "audio_source": audio_source,
        "audio_url": str(validated_request.audio_url) if validated_request.audio_url else None,
        "audio_details": audio_details,
        "auto_rebalance_scenes": auto_rebalance_scenes,
        "scenes": [s.model_dump(mode="json") for s in processed_scenes],
        "created_at_utc": now_iso,
        "output_dir": str(settings.OUTPUT_DIR / job_id)
    }

    created_job = job_store.create_job(job_id, job_data, idempotency_key=idempotency_key)
    await background_worker.enqueue(job_id)
    return format_job_response(created_job)


@router.post("/audio/validate-url", summary="Probe and validate an external audio URL")
def validate_audio_url_endpoint(payload: Dict[str, str]):
    """Checks whether an audio URL is reachable, valid, bounded in size, and safe from SSRF."""
    url = payload.get("url")
    if not url:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error_code": "MISSING_URL", "message": "Field 'url' is required."}
        )
    try:
        result = probe_and_validate_audio_url(url)
        return {"valid": True, **result}
    except SecurityValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error_code": exc.code, "message": exc.message}
        )


@router.get("/jobs", response_model=JobListResponse, summary="List render jobs")
def list_jobs(
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
):
    """Lists jobs with optional status filter and pagination."""
    jobs_data = job_store.list_jobs(status=status, limit=limit, offset=offset)
    total = job_store.count_jobs(status=status)
    formatted = [format_job_response(j) for j in jobs_data]
    return JobListResponse(
        jobs=formatted,
        total=total,
        limit=limit,
        offset=offset
    )


@router.get("/jobs/{job_id}", response_model=JobResponse, summary="Get job status and progress")
def get_job(job_id: str):
    """Fetches real-time status, progress, stage, and manifest for a given job ID."""
    job = job_store.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "JOB_NOT_FOUND", "message": f"Job '{job_id}' not found."}
        )
    return format_job_response(job)


@router.post("/jobs/{job_id}/cancel", response_model=CancelJobResponse, summary="Cancel an in-progress job")
def cancel_job(job_id: str):
    """Requests cancellation of a queued or active job."""
    success, message, job = job_store.cancel_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "JOB_NOT_FOUND", "message": f"Job '{job_id}' not found."}
        )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error_code": "CANNOT_CANCEL_JOB", "message": message}
        )
    return CancelJobResponse(
        job_id=job_id,
        status="cancelled",
        message=message,
        cancelled_at_utc=job.get("cancelled_at_utc", datetime.now(timezone.utc).isoformat())
    )


@router.get("/jobs/{job_id}/artifacts", response_model=ArtifactsResponse, summary="List job artifacts with metadata")
def get_job_artifacts(job_id: str):
    """Lists generated artifacts (video, timeline, captions, manifest) with sizes, hashes, and download links."""
    job = job_store.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "JOB_NOT_FOUND", "message": f"Job '{job_id}' not found."}
        )
    if job.get("status") != "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error_code": "JOB_NOT_COMPLETED",
                "message": f"Job '{job_id}' is currently in state '{job.get('status')}'. Artifacts are only available once completed."
            }
        )

    folder = settings.OUTPUT_DIR / job_id
    artifacts = []
    if folder.exists():
        forbidden = {f.lower() for f in settings.FORBIDDEN_FILENAMES}
        for item in sorted(folder.iterdir()):
            if item.is_file() and not item.name.startswith(".") and item.name.lower() not in forbidden:
                mime, _ = mimetypes.guess_type(item.name)
                artifacts.append(ArtifactItem(
                    name=item.name,
                    content_type=mime or "application/octet-stream",
                    size_bytes=item.stat().st_size,
                    sha256=calculate_sha256(item),
                    download_url=f"/v1/jobs/{job_id}/artifacts/{item.name}"
                ))

    return ArtifactsResponse(
        job_id=job_id,
        status=job["status"],
        artifacts=artifacts,
        created_at_utc=job.get("created_at_utc", datetime.now(timezone.utc).isoformat())
    )


@router.get("/jobs/{job_id}/artifacts/{artifact_name}", summary="Download specific artifact file")
def download_artifact(job_id: str, artifact_name: str):
    """Securely downloads a generated artifact file, enforcing path-traversal and file-access protection."""
    job = job_store.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "JOB_NOT_FOUND", "message": f"Job '{job_id}' not found."}
        )
    if job.get("status") != "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error_code": "JOB_NOT_COMPLETED",
                "message": f"Job '{job_id}' is currently '{job.get('status')}'. Artifacts can only be downloaded when completed."
            }
        )

    folder = settings.OUTPUT_DIR / job_id
    try:
        safe_path = validate_safe_filename(folder, artifact_name)
    except SecurityValidationError as exc:
        err_status = status.HTTP_403_FORBIDDEN if exc.code == "FORBIDDEN_FILE_ACCESS" else status.HTTP_400_BAD_REQUEST
        raise HTTPException(
            status_code=err_status,
            detail={"error_code": exc.code, "message": exc.message}
        )

    if not safe_path.exists() or not safe_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "ARTIFACT_NOT_FOUND", "message": f"Artifact '{artifact_name}' does not exist."}
        )

    mime, _ = mimetypes.guess_type(safe_path.name)
    download_filename = safe_path.name
    if safe_path.suffix.lower() == ".mp4":
        job_title = (job.get("title") or "").strip()
        if job_title:
            clean_title = re.sub(r'[\\/*?:"<>|]', "", job_title).strip()
            if clean_title:
                download_filename = f"{clean_title}.mp4"

    return FileResponse(
        path=safe_path,
        media_type=mime or "application/octet-stream",
        filename=download_filename
    )




@router.get("/jobs/{job_id}/download", summary="Download job final video with project title filename")
def download_job_video(job_id: str):
    """Convenience endpoint to download the rendered MP4 named according to the project title."""
    return download_artifact(job_id, "video.mp4")
@router.post("/scenes/segment", response_model=SegmentationResponse, summary="Segment script into coherent scenes")
def segment_script_endpoint(req: SegmentationRequest):
    """
    Splits continuous script text into coherent scenes using punctuation boundaries and length constraints,
    preserves original narration text verbatim, and calculates positive durations according to audio or cadence.
    """
    cfg = SegmentationConfig(
        min_duration_seconds=req.min_scene_duration or settings.MIN_SCENE_DURATION_SECONDS,
        max_duration_seconds=req.max_scene_duration or settings.MAX_SCENE_DURATION_SECONDS,
        words_per_minute=req.words_per_minute or settings.DEFAULT_WORDS_PER_MINUTE
    )

    try:
        scenes = scene_segmenter.segment_input(
            script=req.script,
            scenes=req.scenes,
            aligned_segments=req.aligned_segments,
            total_duration=req.total_duration_seconds,
            config=cfg
        )
    except SegmentationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error_code": exc.code, "message": exc.message}
        )

    if req.script:
        raw_text = req.script
    elif req.aligned_segments:
        raw_text = " ".join(seg.text for seg in req.aligned_segments)
    elif req.scenes:
        raw_text = " ".join(str(s.get("narration", "")) for s in req.scenes)
    else:
        raw_text = ""

    preserved = scene_segmenter.verify_text_preservation(raw_text, scenes) if raw_text else True
    total_dur = sum(s.duration_seconds for s in scenes)

    return SegmentationResponse(
        scenes=scenes,
        total_duration_seconds=round(total_dur, 3),
        scene_count=len(scenes),
        original_text_preserved=preserved
    )


@router.post("/media/rank", response_model=MediaRankingResponse, summary="Rank candidate visual media by relevance")
def rank_media_endpoint(req: MediaRankingRequest):
    """
    Ranks candidate visual media against a visual description using multi-feature relevance scoring
    (TF-IDF lexical cosine, n-gram phrase match, tag alignment, duration fit, aspect ratio compatibility).
    Exposes full auditable reasons and component breakdown.
    """
    ranker = get_relevance_ranker(req.ranker_type)
    ranked = ranker.rank(
        query_description=req.query_description,
        candidates=req.candidates,
        target_duration=req.target_duration,
        target_aspect_ratio=req.target_aspect_ratio
    )

    return MediaRankingResponse(
        query_description=req.query_description,
        ranked_candidates=ranked,
        active_ranker=ranker.ranker_name,
        model_info=ranker.model_info
    )


@router.get("/providers", response_model=List[ProviderItemResponse], summary="List registered media providers")
def list_media_providers():
    """Returns active media providers, health status, and remote capability flags."""
    return [
        ProviderItemResponse(
            name=p["name"],
            display_name=p["display_name"],
            is_healthy=p["is_healthy"],
            is_remote=p["is_remote"]
        )
        for p in provider_registry.list_providers()
    ]


@router.get("/media/search", response_model=MediaSearchResponse, summary="Search B-roll candidates from lawful providers")
def search_media_candidates(
    query: Optional[str] = None,
    q: Optional[str] = None,
    provider: Optional[str] = None,
    target_duration: Optional[float] = None,
    aspect_ratio: Optional[str] = "16:9",
    limit: Optional[int] = 10,
    count: Optional[int] = None
):
    """
    Searches lawful media providers for B-roll clips matching query keywords,
    validates license compliance, and records provenance metadata.
    Supports both `query` and `q`, as well as `limit` and `count`.
    """
    raw_query = query if query is not None else (q if q is not None else "")
    clean_q = raw_query.strip()
    if not clean_q:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error_code": "EMPTY_QUERY", "message": "Search query cannot be empty."}
        )

    effective_limit = limit if limit is not None else (count if count is not None else 10)

    candidates = provider_registry.search(
        query=clean_q,
        provider_name=provider,
        target_duration=target_duration,
        aspect_ratio=aspect_ratio,
        limit=min(effective_limit, 50)
    )

    items = [
        CandidateMediaItem(
            id=c.id,
            provider=c.provider,
            title=c.title,
            description=c.description,
            tags=c.tags,
            duration_seconds=c.duration_seconds,
            aspect_ratio=c.aspect_ratio if c.aspect_ratio in ("16:9", "9:16", "1:1") else "16:9",
            source_url=c.download_url,
            source_page_url=c.source_page_url,
            download_url=c.download_url,
            preview_url=c.preview_url,
            creator=c.creator,
            creator_url=c.creator_url,
            license_name=c.license_info.name,
            license_url=c.license_info.url,
            attribution=f"'{c.title}' by {c.creator} ({c.license_info.name})",
            attribution_required=c.license_info.attribution_required,
            usage_restrictions=c.usage_restrictions,
            verification_status=c.verification_status,
            verified=c.verified,
            media_type="video"
        )
        for c in candidates
    ]

    return MediaSearchResponse(
        query=clean_q,
        provider=provider or settings.DEFAULT_MEDIA_PROVIDER,
        count=len(items),
        candidates=items
    )


# Compatibility endpoint with starter pack
@router.get("/jobs/{job_id}/files", summary="Legacy file map endpoint")
def legacy_job_files(job_id: str):
    """Preserves backwards compatibility with initial starter pack test contracts."""
    job = job_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    if job["status"] != "completed":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Job is {job['status']}")
    folder = settings.OUTPUT_DIR / job_id
    return {name: str(folder / name) for name in ["video.mp4", "timeline.json", "captions.srt", "manifest.json"]}

