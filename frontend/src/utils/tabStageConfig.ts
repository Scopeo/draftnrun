/**
 * Tab-Stage Configuration
 *
 * Configure which tabs are visible for organizations based on their release stage.
 *
 * - Empty array [] = Tab is visible to ALL organizations (equivalent to 'public')
 * - Array with one stage = Minimum required release stage (higher privilege stages can also access)
 *
 * Release Stage Hierarchy (progressive access):
 * - internal: Highest privilege - can access everything
 * - beta: Can access beta and public tabs
 * - early_access: Can access early_access and public tabs
 * - public: Lowest privilege - can only access public tabs
 */

/**
 * Release stage hierarchy - lower number = higher privilege
 */
import { getReleaseStageRank } from '@/utils/releaseStages'

export interface TabStageConfig {
  [key: string]: string[]
}

export const TAB_STAGE_CONFIG: TabStageConfig = {
  studio: [], // Public - visible to all organizations
  qa: [], // Public - visible to all organizations
  integration: [], // Public - visible to all organizations
}

/**
 * Check if a tab should be visible based on organization's release stage
 * Uses hierarchical/progressive access: higher privilege stages can access lower privilege tabs
 */
export const isTabVisibleForStage = (tabKey: string, orgStage: string | null): boolean => {
  const requiredStages = TAB_STAGE_CONFIG[tabKey]

  // If no specific stages required, tab is visible to all (public)
  if (!requiredStages || requiredStages.length === 0) {
    return true
  }

  // If org has no stage, treat as public (lowest privilege)
  const orgStageLevel = getReleaseStageRank(orgStage)

  // Get the minimum required stage (should only be one stage in the array)
  const minRequiredStage = requiredStages[0]
  const minRequiredLevel = getReleaseStageRank(minRequiredStage)

  // Organization can access if their stage level is <= required level (lower number = higher privilege)
  return orgStageLevel <= minRequiredLevel
}

/**
 * Get tab metadata for display
 */
export const getTabMetadata = (tabKey: string) => {
  const metadata: Record<string, { title: string; icon: string; description: string }> = {
    studio: {
      title: 'Studio',
      icon: 'tabler-code',
      description: 'Visual workflow editor and designer',
    },
    integration: {
      title: 'Integration',
      icon: 'tabler-plug',
      description: 'API access and chat widget configuration',
    },
    qa: {
      title: 'QA',
      icon: 'tabler-test-pipe',
      description: 'Quality assurance testing tools',
    },
  }

  return (
    metadata[tabKey] || {
      title: tabKey.charAt(0).toUpperCase() + tabKey.slice(1),
      icon: 'tabler-tab',
      description: 'Application feature',
    }
  )
}
