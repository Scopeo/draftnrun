import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { type Ref, computed } from 'vue'
import { organizationSecretsApi } from '@/api/organization'
import { logNetworkCall, logQueryStart } from '@/utils/queryLogger'

export function useOrganizationSecretsQuery(orgId: Ref<string | undefined>) {
  const queryKey = computed(() => ['organization-secrets', orgId.value] as const)

  return useQuery({
    queryKey,
    queryFn: async () => {
      logQueryStart(['organization-secrets', orgId.value], 'useOrganizationSecretsQuery')

      if (!orgId.value) return []

      logNetworkCall(['organization-secrets', orgId.value], `/org/${orgId.value}/secrets`)

      const data = await organizationSecretsApi.getAll(orgId.value)
      return data || []
    },
    enabled: computed(() => !!orgId.value),
    staleTime: 1000 * 60 * 5,
    gcTime: 1000 * 60 * 30,
  })
}

export function useAddOrUpdateSecretMutation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ orgId, secretKey, value }: { orgId: string; secretKey: string; value: string }) => {
      logNetworkCall(['add-update-secret', orgId, secretKey], `/org/${orgId}/secrets/${secretKey}`)
      return await organizationSecretsApi.addOrUpdate(orgId, secretKey, { value })
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['organization-secrets', variables.orgId] })
    },
  })
}

export function useDeleteSecretMutation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ orgId, secretKey }: { orgId: string; secretKey: string }) => {
      logNetworkCall(['delete-secret', orgId, secretKey], `/org/${orgId}/secrets/${secretKey}`)
      return await organizationSecretsApi.delete(orgId, secretKey)
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['organization-secrets', variables.orgId] })
    },
  })
}
