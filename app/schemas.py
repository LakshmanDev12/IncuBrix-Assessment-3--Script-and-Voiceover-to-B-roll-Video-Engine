from datetime import datetime, timezone
import re
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.config import settings
from app.security import validate_url_security, validate_url_syntax, SecurityValidationError

AspectRatio = Literal["16:9", "9:16", "1:1"]
Resolution = Literal["1080p", "720p"]
JobStatus = Literal["queued", "processing", "running", "completed", "failed", "cancelled"]
JobStage = Literal[
    "queued", "validating", "segmenting", "fetching_media", 
    "processing_media", "assembling_timeline",
    "rendering", "generating_artifacts", "completed", "failed", "cancelled"
]
AudioSourceType = Literal["none", "upload", "url"]


class MediaMetadata(BaseModel):
    model_config = ConfigDict(extra="ignore")

    source_url: Optional[str] = Field(default=None, description="Public URL of the media clip or image")
    license_name: str = Field(
        default="UNVERIFIED — replace with verified licence",
        max_length=200,
        description="License identifier (e.g., CC0, CC-BY-4.0, Pexels License)"
    )
    attribution: str = Field(
        default="UNVERIFIED — attribution required",
        max_length=500,
        description="Author or source attribution string"
    )
    media_type: Literal["video", "image"] = Field(default="video", description="Type of visual media")
    verified: bool = Field(default=False, description="Whether license & source have been verified")

    @field_validator("source_url")
    @classmethod
    def validate_source_url(cls, v: Optional[str]) -> Optional[str]:
        if v:
            validate_url_syntax(v)
        return v


class Scene(BaseModel):
    model_config = ConfigDict(extra="ignore")

    narration: str = Field(
        default="Scene narration",
        min_length=1, 
        max_length=settings.MAX_NARRATION_LENGTH, 
        description="Script narration text spoken in this scene"
    )
    duration_seconds: float = Field(
        default=3.0,
        ge=settings.MIN_SCENE_DURATION_SECONDS, 
        le=settings.MAX_SCENE_DURATION_SECONDS, 
        description="Duration of this scene in seconds (0.5 to 60.0s)"
    )
    visual_description: str = Field(
        default="cinematic b-roll footage",
        max_length=settings.MAX_VISUAL_DESCRIPTION_LENGTH, 
        description="Visual description describing the desired B-roll content"
    )
    # Direct fields preserved for backwards compatibility with starter payloads
    source_url: Optional[str] = None
    license_name: str = "UNVERIFIED — replace with verified licence"
    attribution: str = "UNVERIFIED — attribution required"
    media_metadata: Optional[MediaMetadata] = None

    @field_validator("narration", mode="before")
    @classmethod
    def sanitize_narration(cls, v: Any) -> str:
        s = str(v or "").strip()
        cleaned = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", s).strip()
        return cleaned if cleaned else "Scene narration"

    @field_validator("visual_description", mode="before")
    @classmethod
    def sanitize_visual(cls, v: Any) -> str:
        s = str(v or "").strip()
        cleaned = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", s).strip()
        if len(cleaned) < settings.MIN_VISUAL_DESCRIPTION_LENGTH:
            return "cinematic b-roll footage"
        return cleaned[:settings.MAX_VISUAL_DESCRIPTION_LENGTH]

    @field_validator("duration_seconds", mode="before")
    @classmethod
    def sanitize_duration(cls, v: Any) -> float:
        try:
            val = float(v)
            if val < settings.MIN_SCENE_DURATION_SECONDS:
                return settings.MIN_SCENE_DURATION_SECONDS
            if val > settings.MAX_SCENE_DURATION_SECONDS:
                return settings.MAX_SCENE_DURATION_SECONDS
            return val
        except (ValueError, TypeError):
            return 3.0

    @field_validator("source_url")
    @classmethod
    def check_url(cls, v: Optional[str]) -> Optional[str]:
        if v:
            validate_url_syntax(v)
        return v

    @model_validator(mode="after")
    def sync_media_metadata(self) -> "Scene":
        if self.media_metadata is None:
            self.media_metadata = MediaMetadata(
                source_url=self.source_url,
                license_name=self.license_name,
                attribution=self.attribution,
                verified=False
            )
        return self


class AudioInputMetadata(BaseModel):
    source_type: AudioSourceType = "none"
    url: Optional[str] = None
    filename: Optional[str] = None
    size_bytes: Optional[int] = None
    duration_seconds: Optional[float] = None
    mime_type: Optional[str] = None
    codec: Optional[str] = None
    format_name: Optional[str] = None
    sample_rate: Optional[int] = None
    channels: Optional[int] = None
    bit_rate: Optional[int] = None


class RenderJobCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str = Field(
        default="Demo video", 
        min_length=settings.MIN_TITLE_LENGTH, 
        max_length=settings.MAX_TITLE_LENGTH,
        description="Human-readable title for the video"
    )
    aspect_ratio: AspectRatio = Field(
        default="16:9", 
        description="Target aspect ratio: 16:9 (horizontal), 9:16 (vertical), or 1:1 (square)"
    )
    resolution: Resolution = Field(
        default="1080p", 
        description="Render resolution: 1080p (high quality) or 720p"
    )
    scenes: List[Scene] = Field(
        min_length=settings.MIN_SCENES, 
        max_length=settings.MAX_SCENES, 
        description="List of scenes defining narration, durations, and B-roll visuals"
    )
    audio_url: Optional[str] = Field(
        default=None, 
        description="Optional public URL to pre-recorded narration/audio track"
    )
    script: Optional[str] = Field(
        default=None,
        description="Optional full script text"
    )
    auto_rebalance_scenes: bool = Field(
        default=False,
        description="If True, rescales scene durations proportionally to fit voiceover audio length"
    )
    strict_duration_match: bool = Field(
        default=True,
        description="If True, strictly enforces that scene duration total matches audio duration"
    )

    @field_validator("title")
    @classmethod
    def sanitize_title(cls, v: str) -> str:
        cleaned = re.sub(r"[\x00-\x1F\x7F]", "", v).strip()
        if not cleaned:
            raise ValueError("Title must contain non-whitespace characters.")
        return cleaned

    @field_validator("script")
    @classmethod
    def validate_script(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            cleaned = v.strip()
            if not cleaned:
                raise ValueError("Script text cannot be empty or solely whitespace.")
            if len(v) > settings.MAX_SCRIPT_LENGTH:
                raise ValueError(f"Script length exceeds maximum permitted ({settings.MAX_SCRIPT_LENGTH} characters).")
        return v

    @field_validator("audio_url")
    @classmethod
    def validate_audio_url(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            # Full SSRF check
            validate_url_security(v)
        return v

    @model_validator(mode="after")
    def validate_job_bounds(self) -> "RenderJobCreate":
        total_duration = sum(s.duration_seconds for s in self.scenes)
        if total_duration < settings.MIN_JOB_DURATION_SECONDS:
            raise ValueError(
                f"Total scene duration ({total_duration:.2f}s) is shorter than minimum allowed ({settings.MIN_JOB_DURATION_SECONDS}s)."
            )
        if total_duration > settings.MAX_JOB_DURATION_SECONDS:
            raise ValueError(
                f"Total scene duration ({total_duration:.2f}s) exceeds maximum allowed ({settings.MAX_JOB_DURATION_SECONDS}s)."
            )
        return self


class JobLinks(BaseModel):
    self: str
    status: str
    artifacts: Optional[str] = None
    cancel: Optional[str] = None


class JobResponse(BaseModel):
    job_id: str
    title: str
    status: JobStatus
    progress: float = Field(ge=0.0, le=100.0, description="Job progress percentage from 0.0 to 100.0")
    current_stage: JobStage
    stage_message: str
    aspect_ratio: AspectRatio
    resolution: Resolution
    duration_seconds: float
    scenes_count: int
    audio_source: AudioSourceType
    audio_details: Optional[AudioInputMetadata] = None
    auto_rebalance_scenes: bool = False
    created_at_utc: str
    started_at_utc: Optional[str] = None
    completed_at_utc: Optional[str] = None
    error: Optional[Dict[str, Any]] = None
    manifest: Optional[Dict[str, Any]] = None
    links: JobLinks


class JobListResponse(BaseModel):
    jobs: List[JobResponse]
    total: int
    limit: int
    offset: int


class CancelJobResponse(BaseModel):
    job_id: str
    status: Literal["cancelled"]
    message: str
    cancelled_at_utc: str


class ArtifactItem(BaseModel):
    name: str
    content_type: str
    size_bytes: int
    sha256: Optional[str] = None
    download_url: str


class ArtifactsResponse(BaseModel):
    job_id: str
    status: JobStatus
    artifacts: List[ArtifactItem]
    created_at_utc: str


class ErrorDetail(BaseModel):
    code: str
    message: str
    field: Optional[str] = None


class ErrorResponse(BaseModel):
    error_code: str
    message: str
    details: List[ErrorDetail] = Field(default_factory=list)
    timestamp_utc: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class LimitsResponse(BaseModel):
    min_title_length: int
    max_title_length: int
    min_scenes: int
    max_scenes: int
    min_scene_duration_seconds: float
    max_scene_duration_seconds: float
    min_job_duration_seconds: float
    max_job_duration_seconds: float
    max_audio_file_size_bytes: int
    max_audio_duration_seconds: float
    allowed_aspect_ratios: List[str]
    allowed_resolutions: List[str]
    allowed_audio_extensions: List[str]


# --- Segmentation & Relevance Ranking Schemas ---

class AlignedNarrationSegment(BaseModel):
    model_config = ConfigDict(extra="ignore")

    text: str = Field(min_length=1, description="Spoken narration text for this segment")
    start_seconds: float = Field(ge=0.0, description="Start timestamp in seconds")
    end_seconds: float = Field(gt=0.0, description="End timestamp in seconds")
    speaker: Optional[str] = Field(default=None, description="Optional speaker label")
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Alignment confidence")

    @model_validator(mode="after")
    def validate_timestamps(self) -> "AlignedNarrationSegment":
        if self.end_seconds <= self.start_seconds:
            raise ValueError(
                f"End timestamp ({self.end_seconds}s) must be strictly greater than start timestamp ({self.start_seconds}s)."
            )
        return self


class SegmentationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    script: Optional[str] = Field(
        default=None,
        max_length=settings.MAX_SCRIPT_LENGTH, 
        description="Raw script text to segment into coherent scenes"
    )
    scenes: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Optional pre-existing scene list to validate and normalize"
    )
    aligned_segments: Optional[List[AlignedNarrationSegment]] = Field(
        default=None,
        description="Optional time-aligned narration segments"
    )
    total_duration_seconds: Optional[float] = Field(
        default=None, 
        ge=settings.MIN_JOB_DURATION_SECONDS, 
        le=settings.MAX_JOB_DURATION_SECONDS,
        description="Optional total duration (e.g. from voiceover audio) to allocate across scenes"
    )
    min_scene_duration: Optional[float] = Field(
        default=None, 
        ge=0.5, 
        le=30.0,
        description="Minimum duration in seconds per scene (default 0.5s)"
    )
    max_scene_duration: Optional[float] = Field(
        default=None, 
        ge=1.0, 
        le=settings.MAX_SCENE_DURATION_SECONDS,
        description="Maximum duration in seconds per scene (default 60.0s)"
    )
    words_per_minute: Optional[int] = Field(
        default=None, 
        ge=60, 
        le=300,
        description="Estimated speech pace in words per minute (default 150 WPM)"
    )

    @model_validator(mode="after")
    def validate_has_input(self) -> "SegmentationRequest":
        has_script = bool(self.script and self.script.strip())
        has_scenes = bool(self.scenes and len(self.scenes) > 0)
        has_aligned = bool(self.aligned_segments and len(self.aligned_segments) > 0)

        if not (has_script or has_scenes or has_aligned):
            raise ValueError("At least one input must be supplied: 'script', 'scenes', or 'aligned_segments'.")
        return self


class SegmentationResponse(BaseModel):
    scenes: List[Scene]
    total_duration_seconds: float
    scene_count: int
    original_text_preserved: bool


class CandidateMediaItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(description="Unique candidate identifier")
    provider: str = Field(default="local_cc0", description="Originating provider (e.g. 'local_cc0', 'pexels')")
    title: str = Field(min_length=1, description="Candidate title or clip name")
    description: str = Field(default="", description="Descriptive visual text or scene context")
    tags: List[str] = Field(default_factory=list, description="Keywords or thematic tags")
    duration_seconds: float = Field(gt=0.0, description="Duration of candidate clip in seconds")
    aspect_ratio: AspectRatio = Field(default="16:9", description="Aspect ratio of candidate")
    source_url: Optional[str] = None
    source_page_url: Optional[str] = None
    download_url: Optional[str] = None
    preview_url: Optional[str] = None
    creator: Optional[str] = "Open Media Contributor"
    creator_url: Optional[str] = None
    license_name: str = "CC0"
    license_url: Optional[str] = None
    attribution: str = "Public Domain / CC0"
    attribution_required: bool = False
    usage_restrictions: List[str] = Field(default_factory=list)
    verification_status: Literal["verified", "unverified", "incompatible_license", "revoked"] = "verified"
    verified: bool = True
    media_type: Literal["video", "image"] = "video"


class ProviderItemResponse(BaseModel):
    name: str
    display_name: str
    is_healthy: bool
    is_remote: bool


class MediaSearchResponse(BaseModel):
    query: str
    provider: str
    count: int
    candidates: List[CandidateMediaItem]



class RankedScoreBreakdown(BaseModel):
    text_similarity: float = Field(ge=0.0, le=1.0, description="Lexical / TF-IDF token overlap score")
    phrase_match: float = Field(ge=0.0, le=1.0, description="N-gram phrase overlap score")
    tag_overlap: float = Field(ge=0.0, le=1.0, description="Thematic tag match score")
    duration_fit: float = Field(ge=0.0, le=1.0, description="Temporal suitability score")
    aspect_ratio_fit: float = Field(ge=0.0, le=1.0, description="Aspect ratio match factor")
    penalties: float = Field(ge=0.0, le=1.0, description="Negative concept / conflict penalty subtracted")


class RankedCandidateItem(BaseModel):
    candidate: CandidateMediaItem
    score: float = Field(ge=0.0, le=1.0, description="Final composite relevance score from 0.0 to 1.0")
    reasons: List[str] = Field(description="Auditable human-readable breakdown of match rationale")
    breakdown: RankedScoreBreakdown


class MediaRankingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query_description: str = Field(
        min_length=1, 
        max_length=settings.MAX_VISUAL_DESCRIPTION_LENGTH,
        description="Scene visual description or target cue"
    )
    target_duration: Optional[float] = Field(
        default=None, 
        gt=0.0,
        description="Target scene duration in seconds for temporal fit scoring"
    )
    target_aspect_ratio: Optional[AspectRatio] = Field(
        default="16:9", 
        description="Target aspect ratio"
    )
    candidates: List[CandidateMediaItem] = Field(
        min_length=1,
        description="List of candidate media items to rank"
    )
    ranker_type: Literal["deterministic", "embedding"] = Field(
        default="deterministic",
        description="Ranking engine to use: 'deterministic' baseline or 'embedding' adapter"
    )


class MediaRankingResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    query_description: str
    ranked_candidates: List[RankedCandidateItem]
    active_ranker: str
    model_info: str

