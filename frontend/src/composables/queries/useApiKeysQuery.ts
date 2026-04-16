import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { type Ref, computed } from 'vue'
import { orgApiKeysApi } from '@/api/auth-keys'
import { logNetworkCall, logQueryStart } from '@/utils/queryLogger'

export function useApiKeysQuery(orgId: Ref<string | undefined>) {
  const queryKey = computed(() => ['api-keys', orgId.value] as const)

  return useQuery({
    queryKey,
    queryFn: async () => {
      logQueryStart(['api-keys', orgId.value], 'useApiKeysQuery')

      if (!orgId.value) return []

      logNetworkCall(['api-keys', orgId.value], `/auth/org-api-key?organization_id=${orgId.value}`)

      const data = await orgApiKeysApi.getAll(orgId.value)
      return data || []
    },
    enabled: computed(() => !!orgId.value),
    staleTime: 1000 * 60 * 5,
    gcTime: 1000 * 60 * 30,
  })
}

export function useCreateApiKeyMutation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ orgId, keyName }: { orgId: string; keyName: string }) => {
      logNetworkCall(['create-api-key', orgId], '/auth/org-api-key')
      return await orgApiKeysApi.create({ key_name: keyName, org_id: orgId })
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['api-keys', variables.orgId] })
    },
  })
}

export function useRevokeApiKeyMutation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ orgId, keyId }: { orgId: string; keyId: string }) => {
      logNetworkCall(['revoke-api-key', orgId, keyId], '/auth/org-api-key')
      return await orgApiKeysApi.revoke(orgId, { key_id: keyId })
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['api-keys', variables.orgId] })
    },
  })
}
