import { computed, ref } from 'vue'
import type { Ref } from 'vue'
import { logger } from '@/utils/logger'

/**
 * Composable for managing QA custom column visibility in localStorage
 *
 * Note: This is a temporary solution using localStorage.
 * TODO: Move to database persistence for proper state management
 */
export function useQAColumnVisibility(datasetId: Ref<string | undefined>) {
  // In-memory cache to avoid reading localStorage on every computed evaluation
  const columnVisibilityCache = ref<Record<string, Record<string, boolean>>>({})

  const getColumnVisibilityKey = (id: string) => `qa-columns-visibility-${id}`

  const loadColumnVisibility = (id: string | undefined): Record<string, boolean> => {
    if (!id) return {}

    // Check cache first
    if (columnVisibilityCache.value[id]) {
      return columnVisibilityCache.value[id]
    }

    // Load from localStorage
    try {
      const stored = localStorage.getItem(getColumnVisibilityKey(id))
      const visibility = stored ? JSON.parse(stored) : {}

      columnVisibilityCache.value[id] = visibility
      return visibility
    } catch (error: unknown) {
      return {}
    }
  }

  const setColumnVisibility = (id: string, columnId: string, visible: boolean, onError?: (message: string) => void) => {
    if (!columnVisibilityCache.value[id]) {
      columnVisibilityCache.value[id] = {}
    }
    columnVisibilityCache.value[id][columnId] = visible

    try {
      localStorage.setItem(getColumnVisibilityKey(id), JSON.stringify(columnVisibilityCache.value[id]))
    } catch (err) {
      const errorMessage = 'Failed to save column visibility settings. Please try again.'
      if (onError) {
        onError(errorMessage)
      } else {
        logger.error('Failed to save column visibility', { error: err })
      }
    }
  }

  const isColumnVisible = (columnId: string): boolean => {
    if (!datasetId.value) return true
    const visibility = loadColumnVisibility(datasetId.value)
    // Default to visible if not set (for new columns)
    return visibility[columnId] !== false
  }

  const clearCache = () => {
    columnVisibilityCache.value = {}
  }

  // Load visibility when dataset changes
  const visibility = computed(() => {
    if (!datasetId.value) return {}
    return loadColumnVisibility(datasetId.value)
  })

  return {
    visibility,
    isColumnVisible,
    setColumnVisibility,
    loadColumnVisibility,
    clearCache,
  }
}
