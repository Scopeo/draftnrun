import { type Ref, computed } from 'vue'
import type { GraphRunner } from '@/types/version'

/**
 * Composable for sorting and labeling graph runner versions.
 *
 * Versions are sorted with draft last (as it's the "latest")
 */
export function useVersionSorting(graphRunners: Ref<GraphRunner[]>) {
  const sortedGraphRunners = computed(() => {
    return (graphRunners.value || [])
      .map((runner, index) => ({
        ...runner,
        originalIndex: index,
      }))
      .sort((a, b) => {
        // Draft (env=draft) always goes last (at the very bottom)
        if (a.env === 'draft') return 1
        if (b.env === 'draft') return -1

        // For production versions, sort by tag_name (oldest first at top, newest just before draft)
        // Versions without tags come after versions with tags
        if (!a.tag_name && b.tag_name) return 1
        if (a.tag_name && !b.tag_name) return -1

        // If both have tags, sort by semantic version (ascending - oldest at top, newest at bottom before draft)
        if (a.tag_name && b.tag_name) {
          // Simple comparison - assumes format v0.1.1
          return a.tag_name.localeCompare(b.tag_name)
        }

        // Otherwise maintain original order
        return a.originalIndex - b.originalIndex
      })
      .map(runner => ({
        ...runner,
        // Display label:
        // - For versions with tag_name: use the tag (e.g., "v0.1.1")
        // - For draft environment (tag_name=null): use "Current changes"
        versionLabel: runner.tag_name || 'Current changes',
      }))
  })

  // Get environment chip color based on environment
  const getEnvColor = (env: string | null) => {
    if (!env) return 'default'
    return env === 'production' ? 'success' : 'warning'
  }

  // Get display label for environment chip
  const getEnvLabel = (env: string | null) => {
    if (!env) return ''
    return env.charAt(0).toUpperCase() + env.slice(1)
  }

  return {
    sortedGraphRunners,
    getEnvColor,
    getEnvLabel,
  }
}
