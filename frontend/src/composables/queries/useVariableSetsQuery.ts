import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import type { Ref } from 'vue'
import { computed } from 'vue'
import { variableSetsApi } from '@/api'

export interface SetIdsResponse {
  set_ids: string[]
}

export interface VariableSet {
  id: string
  organization_id: string
  project_id: string | null
  set_id: string
  values: Record<string, string | { has_value: boolean }>
  created_at: string
  updated_at: string
}

export interface VariableSetListResponse {
  variable_sets: VariableSet[]
}

export function useSetIdsQuery(orgId: Ref<string | undefined>, projectId: Ref<string | undefined>) {
  return useQuery({
    queryKey: computed(() => ['set-ids', orgId.value, projectId.value]),
    queryFn: async (): Promise<SetIdsResponse> => {
      if (!orgId.value || !projectId.value) throw new Error('Missing org or project ID')
      return await variableSetsApi.listSetIds(orgId.value, projectId.value)
    },
    enabled: computed(() => !!orgId.value && !!projectId.value),
    staleTime: 1000 * 60 * 5,
  })
}

export function useVariableSetsQuery(orgId: Ref<string | undefined>) {
  const queryKey = computed(() => ['variable-sets', orgId.value])

  return useQuery({
    queryKey,
    queryFn: async (): Promise<VariableSetListResponse> => {
      if (!orgId.value) throw new Error('No org ID provided')
      return await variableSetsApi.list(orgId.value)
    },
    enabled: computed(() => !!orgId.value),
    staleTime: 1000 * 60 * 5,
  })
}

export function useUpsertVariableSetMutation(orgId: Ref<string | undefined>) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ setId, values }: { setId: string; values: Record<string, string | null> }) => {
      if (!orgId.value) throw new Error('No org ID provided')
      return await variableSetsApi.upsert(orgId.value, setId, values)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['variable-sets', orgId.value] })
      queryClient.invalidateQueries({ queryKey: ['set-ids', orgId.value] })
    },
  })
}

export function useDeleteVariableSetMutation(orgId: Ref<string | undefined>) {
  const queryClient = useQueryClient()
  const queryKey = computed(() => ['variable-sets', orgId.value])

  return useMutation({
    mutationFn: async ({ setId }: { setId: string }) => {
      if (!orgId.value) throw new Error('No org ID provided')
      return await variableSetsApi.delete(orgId.value, setId)
    },
    onMutate: async ({ setId }) => {
      await queryClient.cancelQueries({ queryKey: queryKey.value })

      const previous = queryClient.getQueryData<VariableSetListResponse>(queryKey.value)

      if (previous) {
        queryClient.setQueryData<VariableSetListResponse>(queryKey.value, {
          ...previous,
          variable_sets: previous.variable_sets.filter(s => s.set_id !== setId),
        })
      }

      return { previous }
    },
    onError: (_err, _vars, context) => {
      if (context?.previous) {
        queryClient.setQueryData(queryKey.value, context.previous)
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: queryKey.value })
      queryClient.invalidateQueries({ queryKey: ['set-ids', orgId.value] })
    },
  })
}
