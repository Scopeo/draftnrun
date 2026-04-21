import { $api } from '@/utils/api'

export interface RetryRunRequest {
  env?: string
  graph_runner_id?: string
}

export const runsApi = {
  getResult: (projectId: string, runId: string) =>
    $api<Record<string, any>>(`/projects/${projectId}/runs/${encodeURIComponent(runId)}/result`),

  retry: (projectId: string, runId: string, data: RetryRunRequest) =>
    $api(`/projects/${projectId}/runs/${encodeURIComponent(runId)}/retry`, { method: 'POST', body: data }),
}
