import { $api } from '@/utils/api'

// TODO: remove RetryRunRequest.env once all legacy runs (before graph_runner_id migration) have expired
export interface RetryRunRequest {
  env?: string
}

export const runsApi = {
  getResult: (projectId: string, runId: string) =>
    $api<Record<string, any>>(`/projects/${projectId}/runs/${encodeURIComponent(runId)}/result`),

  retry: (projectId: string, runId: string, data: RetryRunRequest = {}) =>
    $api(`/projects/${projectId}/runs/${encodeURIComponent(runId)}/retry`, { method: 'POST', body: data }),
}
