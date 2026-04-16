import { useQueryClient } from '@tanstack/vue-query'
import { useOrgStore } from '@/stores/org'

/**
 * Wraps org store's setSelectedOrg with TanStack query invalidation.
 * Use this composable in Vue setup() context; the router guard should call
 * orgStore.setSelectedOrg() directly (no query client available there).
 */
export function useOrgSwitch() {
  const orgStore = useOrgStore()
  const queryClient = useQueryClient()

  function switchOrg(orgId: string, role: string) {
    orgStore.setSelectedOrg(orgId, role)

    queryClient.invalidateQueries({ queryKey: ['projects', orgId] })
    queryClient.invalidateQueries({ queryKey: ['agents', orgId] })
    queryClient.invalidateQueries({ queryKey: ['sources', orgId] })
  }

  return { switchOrg }
}
