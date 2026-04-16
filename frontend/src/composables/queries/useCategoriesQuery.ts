import { useQuery } from '@tanstack/vue-query'
import { type Ref, computed } from 'vue'
import { scopeoApi } from '@/api'
import { logNetworkCall, logQueryStart } from '@/utils/queryLogger'
import { logger } from '@/utils/logger'

export interface Category {
  id: string
  name: string
  description: string | null
  icon: string | null
  display_order: number
}

/**
 * Fetch all categories
 */
async function fetchCategories(): Promise<Category[]> {
  logNetworkCall(['categories'], '/categories')

  const response = await scopeoApi.categories.getAll()

  logger.info('[useCategoriesQuery] API Response', { data: response })

  if (Array.isArray(response)) {
    return response
  }

  // Return empty array as fallback to prevent UI crashes
  logger.error('[useCategoriesQuery] Invalid response format, returning empty array', { error: response })
  return []
}

/**
 * Query: Fetch all categories
 *
 * CACHING BEHAVIOR:
 * - Cache key: ['categories']
 * - staleTime: 10 minutes - categories rarely change
 * - refetchOnMount: false - don't refetch when components remount
 * - TanStack Query automatically deduplicates: multiple calls = 1 network request
 */
export function useCategoriesQuery(enabled?: Ref<boolean> | boolean) {
  const queryKey = ['categories']

  const queryEnabled = computed(() => {
    if (enabled === undefined) return true
    return typeof enabled === 'boolean' ? enabled : enabled.value
  })

  logQueryStart(queryKey, 'useCategoriesQuery')

  return useQuery({
    queryKey,
    queryFn: fetchCategories,
    enabled: queryEnabled,
    staleTime: 1000 * 60 * 10, // 10 minutes - categories rarely change
    refetchOnMount: false, // Don't refetch when components remount
  })
}
