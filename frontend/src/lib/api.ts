/**
 * API client. Every request is relative ("/api/...") so the browser talks to
 * whatever host is serving the app - never to an external domain.
 */
import type {
  AuditPayload,
  DetectorInfo,
  EntityDetail,
  EvidencePage,
  Finding,
  NegativeSpace,
  Overview,
  QualityReport,
  ReviewSample,
  Run,
  Stats,
  UploadStage,
  ValidationResult,
} from './types'

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: init?.body instanceof FormData ? undefined : { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`
    try {
      const body = await res.json()
      if (body?.detail) detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch {
      /* keep the status text */
    }
    throw new ApiError(detail, res.status)
  }
  return (await res.json()) as T
}

export const api = {
  health: () => request<{ status: string; version: string; offline: boolean }>('/api/health'),
  stats: () => request<Stats>('/api/stats'),
  overview: () => request<Overview>('/api/overview'),
  detectors: () => request<DetectorInfo[]>('/api/detectors'),
  entity: (id: string) => request<EntityDetail>(`/api/entities/${id}`),
  negativeSpace: (id: string) => request<NegativeSpace>(`/api/entities/${id}/negative-space`),
  findings: (params: Record<string, string | number | undefined> = {}) => {
    const q = new URLSearchParams()
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== '') q.set(k, String(v))
    })
    const suffix = q.toString() ? `?${q}` : ''
    return request<Finding[]>(`/api/findings${suffix}`)
  },
  finding: (id: string) => request<Finding>(`/api/findings/${id}`),
  evidence: (id: string, limit = 100, offset = 0) =>
    request<EvidencePage>(`/api/findings/${id}/evidence?limit=${limit}&offset=${offset}`),
  patchFinding: (id: string, body: { status?: string; supervisor_note?: string }) =>
    request<Finding>(`/api/findings/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  runAnalysis: () =>
    request<{ run_id: string; finding_count: number; per_detector: unknown[] }>('/api/runs', {
      method: 'POST',
      body: JSON.stringify({ notes: 'triggered from the dashboard' }),
    }),
  runs: () => request<Run[]>('/api/runs'),
  latestRun: () => request<Run>('/api/runs/latest'),
  audit: () => request<AuditPayload>('/api/audit'),
  validation: () => request<ValidationResult>('/api/validation'),
  ingestSample: () => request<{ counts: Record<string, number>; data_hash: string }>(
    '/api/ingest/sample',
    { method: 'POST' },
  ),
  reviewSample: (id: string, size: number, seed = 42) =>
    request<ReviewSample>(`/api/entities/${id}/review-sample`, {
      method: 'POST',
      body: JSON.stringify({ size, seed }),
    }),
  quality: (id: string) => request<QualityReport>(`/api/entities/${id}/quality`),
  stageUpload: (entityId: string, tableType: string, file: File) => {
    const form = new FormData()
    form.append('entity_id', entityId)
    form.append('table_type', tableType)
    form.append('file', file)
    return request<UploadStage>('/api/upload/stage', { method: 'POST', body: form })
  },
  commitUpload: (
    uploadId: string,
    mapping: Record<string, string | null>,
    valueMap: Record<string, Record<string, string>>,
  ) =>
    request<{
      rows_loaded: number
      rows_replaced: number
      submission_id: string | null
      quality_report: QualityReport
    }>(`/api/upload/${uploadId}/commit`, {
      method: 'POST',
      body: JSON.stringify({ mapping, value_map: valueMap, remember_mapping: true }),
    }),
  sampleCsvUrl: (sampleId: string) => `/api/samples/${sampleId}/export.csv`,
  reportUrl: (entityId: string) => `/api/entities/${entityId}/report.pdf`,
}
