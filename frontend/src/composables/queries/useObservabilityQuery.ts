import { keepPreviousData, useQuery } from '@tanstack/vue-query'
import { type Ref, computed } from 'vue'
import { scopeoApi } from '@/api'
import type { Span } from '@/types/observability'
import { logQueryStart } from '@/utils/queryLogger'

export interface TraceListParams {
  duration?: number
  start_time?: string
  end_time?: string
  call_type?: string
  page?: number
  size?: number
  search?: string
}

export interface PaginatedTraceResponse {
  traces: Span[]
  pagination: {
    page: number
    size: number
    total_pages: number
  }
}

/**
 * Fetches the list of traces for a project with pagination support
 * Automatically refetches every 10 seconds for real-time updates
 */
export function useTracesQuery(
  projectId: Ref<string | undefined>,
  params: Ref<TraceListParams>,
  enabled?: Ref<boolean>
) {
  const queryKey = computed(() => ['traces', projectId.value, params.value] as const)

  return useQuery({
    queryKey,
    queryFn: async (): Promise<PaginatedTraceResponse> => {
      logQueryStart(['traces', projectId.value, params.value], 'useTracesQuery')

      if (!projectId.value) {
        return {
          traces: [],
          pagination: {
            page: params.value.page || 1,
            size: params.value.size || 20,
            total_pages: 1,
          },
        }
      }

      const data = await scopeoApi.observability.getTracesList(projectId.value, params.value)

      if (data && typeof data === 'object' && 'traces' in data && 'pagination' in data) {
        return {
          traces: data.traces || [],
          pagination: data.pagination || {
            page: params.value.page || 1,
            size: params.value.size || 20,
            total_pages: 1,
          },
        }
      }

      const traces = Array.isArray(data) ? data : []
      return {
        traces,
        pagination: {
          page: params.value.page || 1,
          size: params.value.size || 20,
          total_pages: 1,
        },
      }
    },
    placeholderData: keepPreviousData,
    enabled: computed(() => (enabled?.value ?? true) && !!projectId.value),
    staleTime: 1000 * 5,
    gcTime: 1000 * 60 * 30,
    refetchInterval: 1000 * 10,
    refetchIntervalInBackground: false,
    refetchOnMount: false, // Trust staleTime - data is fresh for 5 seconds, refetchInterval handles polling
  })
}

/**
 * Fetches detailed information for a specific trace including the full tree structure
 */
export function useTraceDetailsQuery(traceId: Ref<string | undefined>, enabled?: Ref<boolean>) {
  const queryKey = computed(() => ['trace-details', traceId.value] as const)

  return useQuery<Span>({
    queryKey,
    queryFn: async () => {
      logQueryStart(['trace-details', traceId.value], 'useTraceDetailsQuery')

      if (!traceId.value) {
        throw new Error('Trace ID is required')
      }
      return await scopeoApi.observability.getTraceDetails(traceId.value)
    },
    enabled: computed(() => (enabled?.value ?? true) && !!traceId.value),
    staleTime: 1000 * 60 * 5,
    gcTime: 1000 * 60 * 30,
    refetchOnMount: false, // Trust staleTime - only refetch if data is stale (> 5 minutes)
  })
}

/**
 * Fetches monitoring charts for a project
 */
export function useMonitoringChartsQuery(
  projectId: Ref<string | undefined>,
  duration: Ref<number>,
  callType?: Ref<string | undefined>
) {
  const queryKey = computed(() => ['monitoring-charts', projectId.value, duration.value, callType?.value] as const)

  return useQuery({
    queryKey,
    queryFn: async () => {
      logQueryStart(['monitoring-charts', projectId.value, duration.value, callType?.value], 'useMonitoringChartsQuery')

      if (!projectId.value) {
        return { charts: [] }
      }

      const params: { duration: number; call_type?: string } = { duration: duration.value }
      if (callType?.value && callType.value !== 'all') {
        params.call_type = callType.value
      }

      return await scopeoApi.observability.getCharts(projectId.value, params)
    },
    enabled: computed(() => !!projectId.value),
    staleTime: 1000 * 60 * 2,
    gcTime: 1000 * 60 * 30,
    refetchOnMount: false, // Trust staleTime - only refetch if data is stale (> 2 minutes)
  })
}

/**
 * Fetches monitoring KPIs for a project
 */
export function useMonitoringKPIsQuery(
  projectId: Ref<string | undefined>,
  duration: Ref<number>,
  callType?: Ref<string | undefined>
) {
  const queryKey = computed(() => ['monitoring-kpis', projectId.value, duration.value, callType?.value] as const)

  return useQuery({
    queryKey,
    queryFn: async () => {
      logQueryStart(['monitoring-kpis', projectId.value, duration.value, callType?.value], 'useMonitoringKPIsQuery')

      if (!projectId.value) {
        return { kpis: [] }
      }

      const call_type = callType?.value && callType.value !== 'all' ? callType.value : undefined

      return await scopeoApi.observability.getKpis(projectId.value, duration.value, call_type)
    },
    enabled: computed(() => !!projectId.value),
    staleTime: 1000 * 60 * 2,
    gcTime: 1000 * 60 * 30,
    refetchOnMount: false, // Trust staleTime - only refetch if data is stale (> 2 minutes)
  })
}

const MONITORING_QUERY_CONFIG = {
  staleTime: 1000 * 60 * 2,
  gcTime: 1000 * 60 * 30,
  refetchOnMount: true, // Refetch on mount to ensure fresh data when navigating to the page
  refetchOnWindowFocus: true, // Refetch when user returns to tab for up-to-date monitoring data
  refetchOnReconnect: false,
}

function buildOrgMonitoringParams(duration: Ref<number>, callType: Ref<string | undefined>, projectIds: Ref<string[]>) {
  const params: { duration: number; call_type?: string; project_ids: string[] } = {
    duration: duration.value,
    project_ids: projectIds.value,
  }

  if (callType.value && callType.value !== 'all') {
    params.call_type = callType.value
  }
  return params
}

/**
 * Fetches monitoring charts for an organization with multiple projects
 */
export function useMonitoringOrgChartsQuery(
  organizationId: Ref<string | undefined>,
  projectIds: Ref<string[]>,
  duration: Ref<number>,
  callType?: Ref<string | undefined>
) {
  const queryKey = computed(() => {
    // Sort and create new array to ensure stable reference for query key
    const sortedProjectIds = [...projectIds.value].sort()
    return ['monitoring-org-charts', organizationId.value, sortedProjectIds, duration.value, callType?.value] as const
  })

  return useQuery({
    queryKey,
    queryFn: async () => {
      logQueryStart(
        ['monitoring-org-charts', organizationId.value, projectIds.value, duration.value, callType?.value],
        'useMonitoringOrgChartsQuery'
      )

      if (!organizationId.value || projectIds.value.length === 0) {
        return { charts: [] }
      }

      const params = buildOrgMonitoringParams(duration, callType as Ref<string | undefined>, projectIds)
      return await scopeoApi.observability.getOrgCharts(organizationId.value, params)
    },
    enabled: computed(() => !!organizationId.value && projectIds.value.length > 0),
    ...MONITORING_QUERY_CONFIG,
  })
}

/**
 * Fetches monitoring KPIs for an organization with multiple projects
 */
export function useMonitoringOrgKPIsQuery(
  organizationId: Ref<string | undefined>,
  projectIds: Ref<string[]>,
  duration: Ref<number>,
  callType?: Ref<string | undefined>
) {
  const queryKey = computed(() => {
    // Sort and create new array to ensure stable reference for query key
    const sortedProjectIds = [...projectIds.value].sort()
    return ['monitoring-org-kpis', organizationId.value, sortedProjectIds, duration.value, callType?.value] as const
  })

  return useQuery({
    queryKey,
    queryFn: async () => {
      logQueryStart(
        ['monitoring-org-kpis', organizationId.value, projectIds.value, duration.value, callType?.value],
        'useMonitoringOrgKPIsQuery'
      )

      if (!organizationId.value || projectIds.value.length === 0) {
        return { kpis: [] }
      }

      const params = buildOrgMonitoringParams(duration, callType as Ref<string | undefined>, projectIds)
      return await scopeoApi.observability.getOrgKpis(organizationId.value, params)
    },
    enabled: computed(() => !!organizationId.value && projectIds.value.length > 0),
    ...MONITORING_QUERY_CONFIG,
  })
}
