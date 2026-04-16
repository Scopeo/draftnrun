import { type Ref, computed } from 'vue'
import type { Category } from './queries/useCategoriesQuery'

/**
 * Centralized composable for category data and lookup maps.
 * Provides optimized lookup maps by ID and name from a provided categories array.
 *
 * @param categories - Computed ref or ref to categories array (typically from useComponentDefinitionsQuery)
 */
export function useCategoryMaps(categories: Ref<Category[] | undefined>) {
  // Helper to create a map with any key selector - DRY principle
  const createCategoryMap = <K extends string>(keySelector: (cat: Category) => K) => {
    return computed<Map<K, Category>>(() => {
      const map = new Map<K, Category>()
      if (categories.value) {
        categories.value.forEach(cat => {
          map.set(keySelector(cat), cat)
        })
      }
      return map
    })
  }

  // Create lookup maps using the shared helper
  const categoriesMapById = createCategoryMap(cat => cat.id)
  const categoriesMapByName = createCategoryMap(cat => cat.name)

  return {
    categoriesData: categories,
    categoriesMapById,
    categoriesMapByName,
  }
}
