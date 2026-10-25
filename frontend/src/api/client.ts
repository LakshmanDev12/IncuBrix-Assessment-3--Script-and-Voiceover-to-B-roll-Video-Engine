
import type {
  ArtifactsResponse,
  CancelJobResponse,
  JobListResponse,
  JobResponse,
  LimitsResponse,
  MediaSearchResponse,
  ProviderItemResponse,
  SegmentationRequest,
  SegmentationResponse,
} from '../types';

// ==================================================
// API CONFIGURATION
// ==================================================

const API_BASE = (
  import.meta.env.VITE_API_BASE_URL ||
  'https://incubrix-video-broll-engine.onrender.com'
).replace(/\/+$/, '');

// ==================================================
// API ERROR CLASS
// ==================================================

export class ApiError extends Error {
  code: string;
  status: number;
  details?: unknown;

  constructor(
    message: string,
    code = 'API_ERROR',
    status = 500,
    details?: unknown,
  ) {
    super(message);

    this.name = 'ApiError';
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

// ==================================================
// COMMON RESPONSE HANDLER
// ==================================================

async function handleResponse<T>(
  res: Response,
): Promise<T> {
  const responseText = await res.text();

  let data: unknown;

  if (responseText.trim()) {
    try {
      data = JSON.parse(responseText);
    } catch {
      data = undefined;
    }
  }

  if (!res.ok) {
    const body = data as
      | {
          detail?:
            | string
            | {
                error_code?: string;
                message?: string;
                details?: unknown;
              };
          message?: string;
          error_code?: string;
          details?: unknown;
        }
      | undefined;

    let message = `Request failed with status ${res.status}`;
    let code = 'HTTP_ERROR';
    let details: unknown;

    if (typeof body?.detail === 'string') {
      message = body.detail;
    } else if (
      body?.detail &&
      typeof body.detail === 'object'
    ) {
      message = body.detail.message || message;
      code = body.detail.error_code || code;
      details = body.detail.details;
    } else if (body?.message) {
      message = body.message;
      code = body.error_code || code;
      details = body.details;
    } else if (responseText.trim()) {
      message = responseText.slice(0, 300);
    }

    throw new ApiError(
      message,
      code,
      res.status,
      details,
    );
  }

  if (!responseText.trim()) {
    throw new ApiError(
      'The API returned an empty response.',
      'EMPTY_RESPONSE',
      res.status,
    );
  }

  if (data === undefined) {
    throw new ApiError(
      'The API returned invalid JSON.',
      'INVALID_RESPONSE',
      res.status,
      responseText.slice(0, 300),
    );
  }

  return data as T;
}

// ==================================================
// API METHODS
// ==================================================

export const api = {
  // ----------------------------------------------
  // Backend health
  // ----------------------------------------------

  async getHealth(): Promise<{
    status: string;
    version: string;
    uptime_seconds?: number;
  }> {
    const res = await fetch(`${API_BASE}/health`);

    return handleResponse(res);
  },

  // ----------------------------------------------
  // Application limits
  // ----------------------------------------------

  async getLimits(): Promise<LimitsResponse> {
    const res = await fetch(`${API_BASE}/v1/limits`);

    return handleResponse(res);
  },

  // ----------------------------------------------
  // List jobs
  // ----------------------------------------------

  async listJobs(
    status?: string,
    limit = 50,
    offset = 0,
  ): Promise<JobListResponse> {
    const params = new URLSearchParams();

    if (status && status !== 'all') {
      params.set('status', status);
    }

    params.set('limit', String(limit));
    params.set('offset', String(offset));

    const res = await fetch(
      `${API_BASE}/v1/jobs?${params.toString()}`,
    );

    return handleResponse(res);
  },

  // ----------------------------------------------
  // Get one job
  // ----------------------------------------------

  async getJob(
    jobId: string,
  ): Promise<JobResponse> {
    const res = await fetch(
      `${API_BASE}/v1/jobs/${encodeURIComponent(jobId)}`,
    );

    return handleResponse(res);
  },

  // ----------------------------------------------
  // Cancel job
  // ----------------------------------------------

  async cancelJob(
    jobId: string,
  ): Promise<CancelJobResponse> {
    const res = await fetch(
      `${API_BASE}/v1/jobs/${encodeURIComponent(jobId)}/cancel`,
      {
        method: 'POST',
      },
    );

    return handleResponse(res);
  },

  // ----------------------------------------------
  // Get job artifacts
  // ----------------------------------------------

  async getArtifacts(
    jobId: string,
  ): Promise<ArtifactsResponse> {
    const res = await fetch(
      `${API_BASE}/v1/jobs/${encodeURIComponent(jobId)}/artifacts`,
    );

    return handleResponse(res);
  },

  // ----------------------------------------------
  // Create job using JSON
  // ----------------------------------------------

  async createJobJson(
    payload: Record<string, unknown>,
    idempotencyKey?: string,
  ): Promise<JobResponse> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };

    if (idempotencyKey) {
      headers['Idempotency-Key'] = idempotencyKey;
    }

    const res = await fetch(`${API_BASE}/v1/jobs`, {
      method: 'POST',
      headers,
      body: JSON.stringify(payload),
    });

    return handleResponse(res);
  },

  // ----------------------------------------------
  // Create job using multipart form data
  // ----------------------------------------------

  async createJobMultipart(
    formData: FormData,
    idempotencyKey?: string,
  ): Promise<JobResponse> {
    const headers: Record<string, string> = {};

    if (idempotencyKey) {
      headers['Idempotency-Key'] = idempotencyKey;
    }

    const res = await fetch(
      `${API_BASE}/v1/jobs/multipart`,
      {
        method: 'POST',
        headers,
        body: formData,
      },
    );

    return handleResponse(res);
  },

  // ----------------------------------------------
  // Validate audio URL
  // ----------------------------------------------

  async probeAudioUrl(
    url: string,
  ): Promise<{
    valid: boolean;
    duration_seconds?: number;
    codec?: string;
  }> {
    const res = await fetch(
      `${API_BASE}/v1/audio/validate-url`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ url }),
      },
    );

    return handleResponse(res);
  },

  // ----------------------------------------------
  // Segment script into scenes
  // ----------------------------------------------

  async segmentScript(
    req: SegmentationRequest,
  ): Promise<SegmentationResponse> {
    const res = await fetch(
      `${API_BASE}/v1/scenes/segment`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(req),
      },
    );

    return handleResponse(res);
  },

  // ----------------------------------------------
  // Search B-roll media
  // Default provider: Pixabay
  // ----------------------------------------------

  async searchMedia(
    query: string,
    provider = 'pixabay',
    count = 10,
  ): Promise<MediaSearchResponse> {
    const normalizedQuery = query.trim();

    if (!normalizedQuery) {
      throw new ApiError(
        'Enter a search query for B-roll footage.',
        'EMPTY_QUERY',
        400,
      );
    }

    const params = new URLSearchParams({
      query: normalizedQuery,
      provider,
      count: String(count),
    });

    const res = await fetch(
      `${API_BASE}/v1/media/search?${params.toString()}`,
    );

    return handleResponse(res);
  },

  // ----------------------------------------------
  // List media providers
  // Confirmed path: /v1/providers
  // ----------------------------------------------

  async listProviders(): Promise<ProviderItemResponse[]> {
    const res = await fetch(
      `${API_BASE}/v1/providers`,
    );

    return handleResponse(res);
  },

  // ----------------------------------------------
  // Artifact download URL
  // ----------------------------------------------

  getArtifactDownloadUrl(
    jobId: string,
    filename: string,
  ): string {
    return (
      `${API_BASE}/v1/jobs/${encodeURIComponent(jobId)}` +
      `/artifacts/${encodeURIComponent(filename)}`
    );
  },
};
