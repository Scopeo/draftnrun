import { $api } from '@/utils/api'

export interface TracesListParams {
  duration?: number
  start_time?: string
  end_time?: string
  call_type?: string
  page?: number
  size?: number
  search?: string
}

export interface ObservabilityApi {
  getTraces: (projectId: string, params: { duration: number; call_type?: string }) => Promise<any>
  getTracesList: (projectId: string, params: TracesListParams) => Promise<any>
  getTraceDetails: (traceId: string) => Promise<any>
  getCharts: (projectId: string, params: { duration: number; call_type?: string }) => Promise<any>
  getKpis: (projectId: string, duration: number, call_type?: string) => Promise<any>
  getOrgCharts: (
    organizationId: string,
    params: { duration: number; call_type?: string; project_ids: string[] }
  ) => Promise<any>
  getOrgKpis: (
    organizationId: string,
    params: { duration: number; call_type?: string; project_ids: string[] }
  ) => Promise<any>
}

export const observabilityApi: ObservabilityApi = {
  getTraces: (projectId: string, params: { duration: number; call_type?: string }) =>
    $api(`/projects/${projectId}/v2/trace`, { query: params }),

  getTracesList: (projectId: string, params: TracesListParams) =>
    $api(`/projects/${projectId}/traces`, { query: params }),

  getTraceDetails: (traceId: string) => $api(`/traces/${traceId}/tree`),

  getCharts: (projectId: string, params: { duration: number; call_type?: string }) =>
    $api(`/projects/${projectId}/charts`, { query: params }),

  getKpis: (projectId: string, duration: number, call_type?: string) =>
    $api(`/projects/${projectId}/kpis`, { query: { duration, ...(call_type && { call_type }) } }),

  getOrgCharts: (organizationId: string, params: { duration: number; call_type?: string; project_ids: string[] }) =>
    $api(`/monitor/org/${organizationId}/charts`, { query: params }),

  getOrgKpis: (organizationId: string, params: { duration: number; call_type?: string; project_ids: string[] }) =>
    $api(`/monitor/org/${organizationId}/kpis`, { query: params }),
}
