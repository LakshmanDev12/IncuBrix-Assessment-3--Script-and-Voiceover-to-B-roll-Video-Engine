
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
  import.meta.env.VITE_API_BASE_URL || ''
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

/**
 * Parse API responses safely.
 * Supports JSON responses and provides useful errors for empty
 * or non-JSON responses.
 */
async function handleResponse<T>(res: Response): Promise<T> {
  const contentType = res.headers.get('content-type') || '';
  const responseText = await res.text();

  let data: any = undefined;

  if (responseText.trim()) {
    try {
      data = JSON.parse(responseText);
    } catch {
      if (res.ok) {
        throw new ApiError(
          `The server returned a non-JSON response (HTTP ${res.status}).`,
          'INVALID_RESPONSE',
          res.status,
          responseText.slice(0, 500),
        );
      }
    }
  }

  if (!res.ok) {
    let errorCode = 'HTTP_ERROR';
    let errorMessage = `Request failed with status ${res.status}`;
    let details: unknown = undefined;

    if (data && typeof data === 'object') {
      if (typeof data.detail === 'string') {
        errorMessage = data.detail;
      } else if (
        data.detail &&
        typeof data.detail === 'object'
      ) {
        errorCode = data.detail.error_code || errorCode;
        errorMessage = data.detail.message || errorMessage;
        details = data.detail.details;
      } else if (data.message) {
        errorMessage = data.message;
        errorCode = data.error_code || errorCode;
        details = data.details;
      }
    } else if (responseText.trim()) {
      errorMessage = responseText.slice(0, 500);
    }

    throw new ApiError(
      errorMessage,
      errorCode,
      res.status,
      details,
    );
  }

  if (!responseText.trim()) {
    throw new ApiError(
      'The server returned an empty response.',
      'EMPTY_RESPONSE',
      res.status,
    );
  }

  if (!contentType.includes('application/json') && data === undefined) {
    throw new ApiError(
      'The server response was not valid JSON.',
      'INVALID_RESPONSE',
      res.status,
      responseText.slice(0, 500),
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
    const res = await fetch(`${API_BASE}/health`);
    return handleResponse(res);
  },

  async getLimits(): Promise<LimitsResponse> {
    const res = await fetch(`${API_BASE}/v1/limits`);
    return handleResponse<LimitsResponse>(res);
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

    const res = await fetch(
      `${API_BASE}/v1/jobs?${params.toString()}`,
    );

    return handleResponse<JobListResponse>(res);
  },

  async getJob(jobId: string): Promise<JobResponse> {
    const res = await fetch(
      `${API_BASE}/v1/jobs/${encodeURIComponent(jobId)}`,
    );

    return handleResponse<JobResponse>(res);
  },

  async cancelJob(jobId: string): Promise<CancelJobResponse> {
    const res = await fetch(
      `${API_BASE}/v1/jobs/${encodeURIComponent(jobId)}/cancel`,
      { method: 'POST' },
    );

    return handleResponse<CancelJobResponse>(res);
  },

  async getArtifacts(jobId: string): Promise<ArtifactsResponse> {
    const res = await fetch(
      `${API_BASE}/v1/jobs/${encodeURIComponent(jobId)}/artifacts`,
    );

    return handleResponse<ArtifactsResponse>(res);
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

    const res = await fetch(`${API_BASE}/v1/jobs`, {
      method: 'POST',
      headers,
      body: JSON.stringify(payload),
    });

    return handleResponse<JobResponse>(res);
  },

  async createJobMultipart(
    formData: FormData,
    idempotencyKey?: string,
  ): Promise<JobResponse> {
    const headers: Record<string, string> = {};

    if (idempotencyKey) {
      headers['Idempotency-Key'] = idempotencyKey;
    }

    // Do not set Content-Type manually for FormData.
    // The browser adds the multipart boundary automatically.
    const res = await fetch(`${API_BASE}/v1/jobs/multipart`, {
      method: 'POST',
      headers,
      body: formData,
    });

    return handleResponse<JobResponse>(res);
  },

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

  async segmentScript(
    req: SegmentationRequest,
  ): Promise<SegmentationResponse> {
    const res = await fetch(`${API_BASE}/v1/scenes/segment`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(req),
    });

    return handleResponse<SegmentationResponse>(res);
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

    const res = await fetch(
      `${API_BASE}/v1/media/search?${params.toString()}`,
    );

    return handleResponse<MediaSearchResponse>(res);
  },

  async listProviders(): Promise<ProviderItemResponse[]> {
    // Correct backend route: GET /v1/providers
    const res = await fetch(`${API_BASE}/v1/providers`);

    return handleResponse<ProviderItemResponse[]>(res);
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
