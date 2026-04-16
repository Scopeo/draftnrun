import type { QueryClient } from '@tanstack/vue-query'
import { useQuery } from '@tanstack/vue-query'
import type { Ref } from 'vue'
import { computed } from 'vue'
import type { OAuthConnectionListItem } from '@/api'
import { scopeoApi } from '@/api'
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

      const connections = await scopeoApi.oauthConnections.list(orgId.value, provider?.value)
      return connections || []
    },
    enabled: computed(() => !!orgId.value),
    staleTime: 30000, // 30s - connections don't change frequently
  })
}

/**
 * Invalidate OAuth connections query for an organization.
 * Call this after creating, updating, or deleting a connection.
 */
export function invalidateOAuthConnectionsQuery(queryClient: QueryClient, orgId: string) {
  queryClient.invalidateQueries({ queryKey: ['oauth-connections', orgId] })
}
