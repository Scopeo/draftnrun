import { keepPreviousData, useQuery } from '@tanstack/vue-query'
import { type Ref, computed } from 'vue'
import { scopeoApi } from '@/api'
import type { OrgRunsParams } from '@/api/observability'
import { logQueryStart } from '@/utils/queryLogger'

export interface OrgRun {
  id: string
  project_id: string
  project_name: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  trigger: string
  trace_id: string | null
  error: Record<string, any> | null
  retry_group_id: string | null
  attempt_number: number
  attempt_count: number
  input_available: boolean
  started_at: string | null
  finished_at: string | null
  created_at: string
}

export interface OrgRunsResponse {
  runs: OrgRun[]
  pagination: {
    page: number
    page_size: number
    total_items: number
    total_pages: number
  }
}

export function useOrgRunsQuery(
  organizationId: Ref<string | undefined>,
  params: Ref<OrgRunsParams>,
  enabled?: Ref<boolean>
) {
  const queryKey = computed(() => ['org-runs', organizationId.value, params.value] as const)

  return useQuery<OrgRunsResponse>({
    queryKey,
    queryFn: async () => {
      logQueryStart(['org-runs', organizationId.value, params.value], 'useOrgRunsQuery')

      if (!organizationId.value) {
        return {
          runs: [],
          pagination: { page: 1, page_size: 50, total_items: 0, total_pages: 0 },
        }
      }

      return await scopeoApi.observability.getOrgRuns(organizationId.value, params.value)
    },
    placeholderData: keepPreviousData,
    enabled: computed(() => (enabled?.value ?? true) && !!organizationId.value),
    staleTime: 0,
    gcTime: 1000 * 60 * 10,
  })
}
