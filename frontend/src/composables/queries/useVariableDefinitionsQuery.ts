import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import type { Ref } from 'vue'
import { computed } from 'vue'
import { orgVariableDefinitionsApi } from '@/api'

export interface VariableDefinition {
  id?: string
  organization_id?: string
  project_ids?: string[]
  name: string
  type: 'string' | 'number' | 'boolean' | 'oauth' | 'secret' | 'source'
  description: string | null
  required: boolean
  default_value: string | null
  has_default_value?: boolean
  metadata: Record<string, unknown> | null
  editable: boolean
  display_order: number
  created_at?: string | null
  updated_at?: string | null
}

// --- Org-scoped definitions ---

export function useOrgVariableDefinitionsQuery(orgId: Ref<string | undefined>, filters?: { type?: string }) {
  const queryKey = computed(() => ['org-variable-definitions', orgId.value, filters?.type])

  return useQuery({
    queryKey,
    queryFn: async (): Promise<VariableDefinition[]> => {
      if (!orgId.value) throw new Error('No org ID provided')
      return await orgVariableDefinitionsApi.list(orgId.value, filters)
    },
    enabled: computed(() => !!orgId.value),
    staleTime: 1000 * 60 * 5,
  })
}

export function useUpsertOrgVariableDefinitionMutation(orgId: Ref<string | undefined>) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({
      name,
      data,
      projectIds,
    }: {
      name: string
      data: Record<string, unknown>
      projectIds?: string[]
    }) => {
      if (!orgId.value) throw new Error('No org ID provided')
      return await orgVariableDefinitionsApi.upsert(orgId.value, name, data, projectIds)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['org-variable-definitions', orgId.value] })
    },
  })
}

export function useDeleteOrgVariableDefinitionMutation(orgId: Ref<string | undefined>) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ name }: { name: string }) => {
      if (!orgId.value) throw new Error('No org ID provided')
      return await orgVariableDefinitionsApi.delete(orgId.value, name)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['org-variable-definitions', orgId.value] })
    },
  })
}
