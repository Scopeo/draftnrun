import type { QueryClient } from '@tanstack/vue-query'
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import type { Ref } from 'vue'
import { computed } from 'vue'
import type { OAuthConnectionListItem } from '@/api'
import { oauthConnectionsApi } from '@/api/oauth'
import { logNetworkCall, logQueryStart } from '@/utils/queryLogger'

/**
 * Query hook for fetching OAuth connections for an organization.
 *
 * @param orgId - Organization ID (reactive)
 * @param provider - Optional provider filter (reactive)
 */
export function useOAuthConnectionsQuery(orgId: Ref<string | undefined>, provider?: Ref<string | undefined>) {
  const queryKey = computed(() => ['oauth-connections', orgId.value, provider?.value] as const)

  return useQuery({
    queryKey,
    queryFn: async (): Promise<OAuthConnectionListItem[]> => {
      logQueryStart([...queryKey.value], 'useOAuthConnectionsQuery')
      logNetworkCall([...queryKey.value], 'GET /organizations/{orgId}/oauth-connections')

      if (!orgId.value) {
        return []
      }

      const connections = await oauthConnectionsApi.list(orgId.value, provider?.value)
      return connections || []
    },
    enabled: computed(() => !!orgId.value),
    staleTime: 30000, // 30s - connections don't change frequently
  })
}

export function useDeleteOAuthConnectionMutation(orgId: Ref<string | undefined>) {
  const queryClient = useQueryClient()

  return useMutation<void, Error, { connectionId: string; providerConfigKey: string }>({
    mutationFn: async ({ connectionId, providerConfigKey }) => {
      if (!orgId.value) throw new Error('No org ID provided')
      logNetworkCall(['delete-oauth-connection', connectionId], `DELETE /organizations/${orgId.value}/oauth-connections/${connectionId}`)
      await oauthConnectionsApi.delete(orgId.value, connectionId, providerConfigKey)
    },
    onSuccess: () => {
      if (orgId.value) {
        queryClient.invalidateQueries({ queryKey: ['oauth-connections', orgId.value] })
        queryClient.invalidateQueries({ queryKey: ['org-variable-definitions', orgId.value] })
      }
    },
  })
}

/**
 * Invalidate OAuth connections query for an organization.
 * Call this after creating, updating, or deleting a connection.
 */
export function invalidateOAuthConnectionsQuery(queryClient: QueryClient, orgId: string) {
  queryClient.invalidateQueries({ queryKey: ['oauth-connections', orgId] })
}
