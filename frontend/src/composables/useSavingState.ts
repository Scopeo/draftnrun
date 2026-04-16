import { type Ref, computed } from 'vue'

/**
 * Shared helper to compute isSaving state from save version composable and local saving state
 * Ensures consistent pattern between Agent and Workflow modes
 */
export function useSavingState(saveVersionIsSaving: Ref<boolean> | undefined, localIsSaving: Ref<boolean>) {
  return computed(() => {
    // Prefer save version's isSaving (from shared composable), fallback to local isSaving (for regular saves)
    return saveVersionIsSaving?.value ?? localIsSaving.value
  })
}
