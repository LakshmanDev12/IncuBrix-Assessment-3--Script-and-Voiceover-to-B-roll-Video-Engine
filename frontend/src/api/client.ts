
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

const API_BASE = (
  import.meta.env.VITE_API_BASE_URL ||
  'https://incubrix-video-broll-engine.onrender.com'
).replace(/\/+$/, '');

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

async function handleResponse<T>(res: Response): Promise<T> {
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
    const body = data as {
      detail?: string | {
        error_code?: string;
        message?: string;
        details?: unknown;
      };
      message?: string;
      error_code?: string;
      details?: unknown;
    } | undefined;

    let message = `Request failed with status ${res.status}`;
    let code = 'HTTP_ERROR';
    let details: unknown;

    if (typeof body?.detail === 'string') {
      message = body.detail;
    } else if (body?.detail && typeof body.detail === 'object') {
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

    throw new ApiError(message, code, res.status, details);
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

export const api = {
  async getHealth(): Promise<{
    status: string;
    version: string;
    uptime_seconds?: number;
  }> {
    return handleResponse(
      await fetch(`${API_BASE}/health`),
    );
  },

  async getLimits(): Promise<LimitsResponse> {
    return handleResponse(
      await fetch(`${API_BASE}/v1/limits`),
    );
  },

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

    return handleResponse(
      await fetch(`${API_BASE}/v1/jobs?${params.toString()}`),
    );
  },

  async getJob(jobId: string): Promise<JobResponse> {
    return handleResponse(
      await fetch(
        `${API_BASE}/v1/jobs/${encodeURIComponent(jobId)}`,
      ),
    );
  },

  async cancelJob(jobId: string): Promise<CancelJobResponse> {
    return handleResponse(
      await fetch(
        `${API_BASE}/v1/jobs/${encodeURIComponent(jobId)}/cancel`,
        { method: 'POST' },
      ),
    );
  },

  async getArtifacts(jobId: string): Promise<ArtifactsResponse> {
    return handleResponse(
      await fetch(
        `${API_BASE}/v1/jobs/${encodeURIComponent(jobId)}/artifacts`,
      ),
    );
  },

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

    return handleResponse(
      await fetch(`${API_BASE}/v1/jobs`, {
        method: 'POST',
        headers,
        body: JSON.stringify(payload),
      }),
    );
  },

  async createJobMultipart(
    formData: FormData,
    idempotencyKey?: string,
  ): Promise<JobResponse> {
    const headers: Record<string, string> = {};

    if (idempotencyKey) {
      headers['Idempotency-Key'] = idempotencyKey;
    }

    return handleResponse(
      await fetch(`${API_BASE}/v1/jobs/multipart`, {
        method: 'POST',
        headers,
        body: formData,
      }),
    );
  },

  async probeAudioUrl(
    url: string,
  ): Promise<{
    valid: boolean;
    duration_seconds?: number;
    codec?: string;
  }> {
    return handleResponse(
      await fetch(`${API_BASE}/v1/audio/validate-url`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url }),
      }),
    );
  },

  async segmentScript(
    req: SegmentationRequest,
  ): Promise<SegmentationResponse> {
    return handleResponse(
      await fetch(`${API_BASE}/v1/scenes/segment`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(req),
      }),
    );
  },

  async searchMedia(
    query: string,
    provider = 'local_cc0',
    count = 10,
  ): Promise<MediaSearchResponse> {
    const params = new URLSearchParams({
      query,
      provider,
      count: String(count),
    });

    return handleResponse(
      await fetch(
        `${API_BASE}/v1/media/search?${params.toString()}`,
      ),
    );
  },

  async listProviders(): Promise<ProviderItemResponse[]> {
    return handleResponse(
      await fetch(`${API_BASE}/v1/providers`),
    );
  },

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
