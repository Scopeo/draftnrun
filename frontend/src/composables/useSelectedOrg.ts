import { storeToRefs } from 'pinia'
import { ref, watch } from 'vue'
import { useOrgStore } from '@/stores/org'
import { logger } from '@/utils/logger'

// Re-export types for backward compatibility
export type { AppAbilityRawRule } from '@/utils/abilityRules'

export function useSelectedOrg() {
  const orgStore = useOrgStore()

  // Map store state to composable API
  const {
    selectedOrgId,
    selectedOrgRole,
    isLoading: isOrgDataLoading,
    isLoaded: isOrgDataLoaded,
    isOrgAdmin,
  } = storeToRefs(orgStore)

  // Forward setSelectedOrg to store
  const setSelectedOrg = (orgId: string, role?: string) => {
    if (role) {
      orgStore.setSelectedOrg(orgId, role)
    } else {
      logger.warn('[useSelectedOrg] No role provided when changing organization')
    }
  }

  // Emulate orgChangeCounter for backward compatibility
  const orgChangeCounter = ref(0)

  watch([selectedOrgId, selectedOrgRole], () => {
    orgChangeCounter.value++
  })

  return {
    selectedOrgId,
    selectedOrgRole,
    setSelectedOrg,
    isOrgAdmin,
    orgChangeCounter,
    isOrgDataLoading,
    isOrgDataLoaded,
  }
}
