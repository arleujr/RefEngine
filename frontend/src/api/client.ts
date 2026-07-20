import type {
  ApiErrorPayload,
  CatalogField,
  Health,
  InputInventory,
  PublishResponse,
  Run,
  SchemaDefinition,
  WorkAction,
  WorkDetail,
  WorkPatch,
  WorkSummary,
} from './types';

export class ApiError extends Error {
  readonly code: string;
  readonly details: Record<string, unknown>;

  constructor(status: number, payload: ApiErrorPayload | null) {
    super(payload?.message ?? `A solicitação falhou com status ${status}.`);
    this.name = 'ApiError';
    this.code = payload?.error ?? 'request_failed';
    this.details = (payload?.details ?? {}) as Record<string, unknown>;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...init?.headers,
    },
  });

  if (!response.ok) {
    let payload: ApiErrorPayload | null = null;
    try {
      payload = (await response.json()) as ApiErrorPayload;
    } catch {
      payload = null;
    }
    throw new ApiError(response.status, payload);
  }

  return (await response.json()) as T;
}

export const api = {
  health: () => request<Health>('/api/v1/health'),
  inventory: () => request<InputInventory>('/api/v1/input'),
  listRuns: () => request<Run[]>('/api/v1/runs?limit=20'),
  createRun: () =>
    request<Run>('/api/v1/runs', {
      method: 'POST',
      body: JSON.stringify({}),
    }),
  getRun: (runId: string) => request<Run>(`/api/v1/runs/${runId}`),
  listWorks: (runId: string) =>
    request<WorkSummary[]>(`/api/v1/runs/${runId}/works`),
  getWork: (runId: string, workId: string) =>
    request<WorkDetail>(`/api/v1/runs/${runId}/works/${workId}`),
  saveWork: (runId: string, workId: string, patch: WorkPatch) =>
    request<WorkAction>(`/api/v1/runs/${runId}/works/${workId}`, {
      method: 'PATCH',
      body: JSON.stringify(patch),
    }),
  approveWork: (runId: string, workId: string) =>
    request<WorkAction>(`/api/v1/runs/${runId}/works/${workId}/approve`, {
      method: 'POST',
      body: JSON.stringify({}),
    }),
  publish: (runId: string) =>
    request<PublishResponse>(`/api/v1/runs/${runId}/publish`, {
      method: 'POST',
      body: JSON.stringify({}),
    }),
  schemas: () => request<SchemaDefinition[]>('/api/v1/catalog/schemas'),
  fields: () => request<CatalogField[]>('/api/v1/catalog/fields'),
};
