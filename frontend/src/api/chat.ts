import { $api, getApiBaseUrl, getAuthHeaders } from '@/utils/api'

export interface ChatAsyncAccepted {
  accepted: true
  run_id: string
}
export interface ChatAsyncResult {
  accepted: false
  result: Record<string, any>
}

export const chatApi = {
  chat: (projectId: string, graphRunnerId: string, data: any) =>
    $api(`/projects/${projectId}/graphs/${graphRunnerId}/chat`, { method: 'POST', body: data }),

  chatByEnv: (projectId: string, env: string, data: any) =>
    $api(`/projects/${projectId}/${env}/chat`, { method: 'POST', body: data }),

  // Uses raw fetch because $api doesn't handle 202 + run_id response pattern
  chatAsync: async (
    projectId: string,
    graphRunnerId: string,
    data: any
  ): Promise<ChatAsyncAccepted | ChatAsyncResult> => {
    const authHeaders = await getAuthHeaders()
    const url = `${getApiBaseUrl()}/projects/${projectId}/graphs/${graphRunnerId}/chat/async`

    const response = await fetch(url, {
      method: 'POST',
      headers: {
        ...authHeaders,
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      body: JSON.stringify(data),
    })

    const body = await response.json().catch(() => ({}))
    if (response.status === 202 && body?.run_id) {
      return { accepted: true, run_id: body.run_id }
    }
    if (response.ok) {
      return { accepted: false, result: body }
    }
    const detail = body?.detail ?? response.statusText ?? 'Request failed'
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  },
}

export const runsApi = {
  getResult: (projectId: string, runId: string) =>
    $api<Record<string, any>>(`/projects/${projectId}/runs/${encodeURIComponent(runId)}/result`),
}
