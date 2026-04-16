import { useQuery } from '@tanstack/vue-query'
import { type Ref, computed } from 'vue'
import { scopeoApi } from '@/api'
import type { LLMModel } from '@/types/llmModels'
import { logQueryStart } from '@/utils/queryLogger'

export function useLLMModelsQuery(orgId: Ref<string | undefined>) {
  const queryKey = computed(() => ['llm-models', orgId.value] as const)

  return useQuery({
    queryKey,
    queryFn: async (): Promise<LLMModel[]> => {
      logQueryStart(['llm-models', orgId.value], 'useLLMModelsQuery')

      if (!orgId.value) {
        return []
      }

      return await scopeoApi.llmModels.list(orgId.value)
    },
    enabled: computed(() => !!orgId.value),
    staleTime: 1000 * 60 * 5, // 5 minutes
    refetchOnMount: false,
  })
}
