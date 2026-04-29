import { useQuery } from '@tanstack/vue-query'
import { type Ref, computed } from 'vue'
import { studioApi } from '@/api/studio'
import type { GraphV2Response } from '@/components/studio/types/graph.types'
import { logNetworkCall, logQueryStart } from '@/utils/queryLogger'

export function useGraphQuery(projectId: Ref<string | undefined>, graphRunnerId: Ref<string | undefined>) {
  const queryKey = computed(() => ['graph', projectId.value, graphRunnerId.value] as const)

  return useQuery({
    queryKey,
    queryFn: async () => {
      logQueryStart(['graph', projectId.value, graphRunnerId.value], 'useGraphQuery')

      logNetworkCall(
        ['graph', projectId.value, graphRunnerId.value],
        `/projects/${projectId.value}/graph/${graphRunnerId.value}`
      )

      return await studioApi.getGraph(projectId.value!, graphRunnerId.value!)
    },
    enabled: computed(() => !!projectId.value && !!graphRunnerId.value),
    staleTime: 1000 * 60 * 5,
    gcTime: 1000 * 60 * 30,
  })
}

export function useGraphQueryV2(projectId: Ref<string | undefined>, graphRunnerId: Ref<string | undefined>) {
  const queryKey = computed(() => ['graph-v2', projectId.value, graphRunnerId.value] as const)

  return useQuery<GraphV2Response>({
    queryKey,
    queryFn: async () => {
      logQueryStart(['graph-v2', projectId.value, graphRunnerId.value], 'useGraphQueryV2')

      logNetworkCall(
        ['graph-v2', projectId.value, graphRunnerId.value],
        `/v2/projects/${projectId.value}/graph/${graphRunnerId.value}`
      )

      return await studioApi.getGraphV2(projectId.value!, graphRunnerId.value!)
    },
    enabled: computed(() => !!projectId.value && !!graphRunnerId.value),
    staleTime: 1000 * 60 * 5,
    gcTime: 1000 * 60 * 30,
  })
}
