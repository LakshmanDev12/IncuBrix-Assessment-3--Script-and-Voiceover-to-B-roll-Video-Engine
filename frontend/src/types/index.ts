export type StudioMode = 'creative' | 'professional';
export type AspectRatio = '16:9' | '9:16' | '1:1';
export type Resolution = '1080p' | '720p';
export type JobStatus = 'queued' | 'processing' | 'completed' | 'failed' | 'cancelled';
export type JobStage =
  | 'queued'
  | 'validating'
  | 'segmenting'
  | 'fetching_media'
  | 'processing_media'
  | 'assembling_timeline'
  | 'rendering'
  | 'generating_artifacts'
  | 'completed'
  | 'failed'
  | 'cancelled';

export type AudioSourceType = 'none' | 'upload' | 'url';

export interface BrandingConfig {
  brand_name?: string;
  logo_url?: string;
  primary_color?: string;
  secondary_color?: string;
  font_family?: string;
}

export interface MediaMetadata {
  source_url?: string;
  license_name: string;
  attribution: string;
  media_type: 'video' | 'image';
  verified: boolean;
}

export interface Scene {
  narration: string;
  duration_seconds: number;
  visual_description: string;
  source_url?: string;
  license_name?: string;
  attribution?: string;
  media_metadata?: MediaMetadata;
  keywords?: string[];
  transition?: string;
  visual_style?: string;
}

export interface AudioInputMetadata {
  source_type: AudioSourceType;
  duration_seconds: number;
  codec: string;
  format_name: string;
  sample_rate: number;
  channels: number;
  bit_rate?: number;
  size_bytes?: number;
  filename?: string;
  url?: string;
}

export interface JobLinks {
  self: string;
  status: string;
  artifacts?: string;
  cancel?: string;
}

export interface JobResponse {
  job_id: string;
  title: string;
  status: JobStatus;
  progress: number;
  current_stage: JobStage;
  stage_message: string;
  aspect_ratio: AspectRatio;
  resolution: Resolution;
  duration_seconds: number;
  scenes_count: number;
  audio_source: AudioSourceType;
  audio_details?: AudioInputMetadata | null;
  auto_rebalance_scenes: boolean;
  studio_mode?: StudioMode;
  style_preset?: string | null;
  pacing?: string;
  caption_preset?: string | null;
  branding?: BrandingConfig | null;
  created_at_utc: string;
  started_at_utc?: string | null;
  completed_at_utc?: string | null;
  error?: {
    error_code: string;
    message: string;
    details?: unknown;
  } | null;
  manifest?: ManifestData | null;
  links: JobLinks;
}

export interface ManifestSceneClip {
  scene_index: number;
  narration: string;
  duration_seconds: number;
  start_seconds: number;
  end_seconds: number;
  clip_id?: string;
  clip_source?: string;
  license_name?: string;
  attribution?: string;
  verified?: boolean;
  relevance_score?: number;
}

export interface ManifestData {
  job_id: string;
  title: string;
  aspect_ratio: string;
  resolution: string;
  total_duration_seconds: number;
  scenes: ManifestSceneClip[];
  render_stats?: {
    frame_rate: number;
    video_codec: string;
    audio_codec: string;
    render_duration_seconds?: number;
  };
  provenance_summary?: {
    total_clips: number;
    verified_cc0_count: number;
    unverified_count: number;
  };
  created_at_utc: string;
}

export interface JobListResponse {
  jobs: JobResponse[];
  total: number;
  limit: number;
  offset: number;
}

export interface CancelJobResponse {
  job_id: string;
  status: 'cancelled';
  message: string;
  cancelled_at_utc: string;
}

export interface ArtifactItem {
  name: string;
  content_type: string;
  size_bytes: number;
  sha256?: string;
  download_url: string;
}

export interface ArtifactsResponse {
  job_id: string;
  status: JobStatus;
  artifacts: ArtifactItem[];
  created_at_utc: string;
}

export interface LimitsResponse {
  min_title_length: number;
  max_title_length: number;
  min_scenes: number;
  max_scenes: number;
  min_scene_duration_seconds: number;
  max_scene_duration_seconds: number;
  min_job_duration_seconds: number;
  max_job_duration_seconds: number;
  max_audio_file_size_bytes: number;
  max_audio_duration_seconds: number;
  allowed_aspect_ratios: string[];
  allowed_resolutions: string[];
  allowed_audio_extensions: string[];
}

export interface SegmentationRequest {
  script?: string;
  scenes?: Partial<Scene>[];
  total_duration_seconds?: number;
  min_scene_duration?: number;
  max_scene_duration?: number;
  words_per_minute?: number;
}

export interface SegmentationResponse {
  scenes: Scene[];
  total_duration_seconds: number;
  scene_count: number;
  original_text_preserved: boolean;
}

export interface CandidateMediaItem {
  id: string;
  provider: string;
  title: string;
  description: string;
  tags: string[];
  duration_seconds: number;
  aspect_ratio: AspectRatio;
  source_url?: string;
  source_page_url?: string;
  download_url?: string;
  preview_url?: string;
  creator?: string;
  license_name: string;
  attribution: string;
  verified: boolean;
  media_type: 'video' | 'image';
}

export interface MediaSearchResponse {
  query: string;
  provider: string;
  count: number;
  candidates: CandidateMediaItem[];
}

export interface ProviderItemResponse {
  name: string;
  display_name: string;
  is_healthy: boolean;
  is_remote: boolean;
}
