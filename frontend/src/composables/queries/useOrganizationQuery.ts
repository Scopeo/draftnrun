import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { type Ref, computed } from 'vue'
import { scopeoApi } from '@/api'
import type { OrgApiKeyCreatedResponse, OrgApiKeysResponse } from '@/types/organization'

/**
 * Query: Fetch all org API keys for an organization
 */
export function useOrgApiKeysQuery(orgId: Ref<string | undefined>) {
  const queryKey = computed(() => ['org-api-keys', orgId.value] as const)

  return useQuery<OrgApiKeysResponse>({
    queryKey,
    queryFn: async () => {
      if (!orgId.value) throw new Error('No organization ID provided')
      return await scopeoApi.orgApiKeys.getAll(orgId.value)
    },
    enabled: computed(() => !!orgId.value),
    staleTime: 1000 * 60 * 5,
    gcTime: 1000 * 60 * 30,
    refetchOnMount: true,
  })
}

/**
 * Query: Fetch credit usage for an organization
 */
export function useOrgCreditUsageQuery(orgId: Ref<string | undefined>) {
  const queryKey = computed(() => ['org-credit-usage', orgId.value] as const)

  return useQuery({
    queryKey,
    queryFn: async () => {
      if (!orgId.value) throw new Error('No organization ID provided')
      const data = await scopeoApi.organizationCreditUsage.getCreditUsage(orgId.value)

      if (data.charts && Array.isArray(data.charts) && data.charts.length > 0) {
        const tableChart = data.charts.find((chart: any) => chart.type === 'table')
        return tableChart || data.charts[0]
      }

      return null
    },
    enabled: computed(() => !!orgId.value),
    staleTime: 0,
    gcTime: 0,
    refetchOnMount: 'always',
  })
}

/**
 * Mutation: Create a new org API key
 */
export function useCreateOrgApiKeyMutation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (data: { key_name: string; org_id: string }): Promise<OrgApiKeyCreatedResponse> => {
      return await scopeoApi.orgApiKeys.create(data)
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['org-api-keys', variables.org_id] })
    },
  })
}

/**
 * Mutation: Revoke an org API key
 */
export function useRevokeOrgApiKeyMutation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ organizationId, keyId }: { organizationId: string; keyId: string }) => {
      return await scopeoApi.orgApiKeys.revoke(organizationId, { key_id: keyId })
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['org-api-keys', variables.organizationId] })
    },
  })
}
