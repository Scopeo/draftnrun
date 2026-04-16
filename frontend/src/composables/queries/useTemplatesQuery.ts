import { useQuery } from '@tanstack/vue-query'
import { type Ref, computed } from 'vue'
import { scopeoApi } from '@/api'
import { logQueryStart } from '@/utils/queryLogger'

export interface Template {
  template_graph_runner_id: string
  template_project_id: string
  name: string
  description: string
}

/**
 * Fetches templates for the given organization
 */
export function useTemplatesQuery(orgId: Ref<string | undefined>) {
  const queryKey = computed(() => ['templates', orgId.value] as const)

  return useQuery({
    queryKey,
    queryFn: async () => {
      logQueryStart(['templates', orgId.value], 'useTemplatesQuery')

      if (!orgId.value) {
        return []
      }
      const data = await scopeoApi.templates.getAll(orgId.value)
      return data || []
    },
    enabled: computed(() => !!orgId.value),
    staleTime: 1000 * 60 * 5, // 5 minutes - templates don't change frequently
    refetchOnMount: false,
  })
}
