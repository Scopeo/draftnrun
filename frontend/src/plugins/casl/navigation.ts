import { useAbility } from '@casl/vue'
import { createMongoAbility } from '@casl/ability'
import type { RouteLocationNormalized } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { logger } from '@/utils/logger'

// Local nav types for CASL integration
interface AclProperties {
  action: string
  subject: string
}

interface NavLinkProps {
  to?: unknown
  href?: string
  target?: string
  rel?: string
}

interface NavLink extends NavLinkProps, Partial<AclProperties> {
  title: string
  icon?: unknown
  badgeContent?: string
  badgeClass?: string
  disable?: boolean
}

export interface NavGroup extends Partial<AclProperties> {
  title: string
  icon?: unknown
  badgeContent?: string
  badgeClass?: string
  children: (NavLink | NavGroup)[]
  disable?: boolean
  alwaysShow?: boolean
}

/**
 * Returns ability result if ACL is configured or else just return true
 * We should allow passing string | undefined to can because for admin ability we omit defining action & subject
 *
 * Useful if you don't know if ACL is configured or not
 * Used to handle absence of ACL without errors
 *
 * @param {string} action CASL Actions // https://casl.js.org/v4/en/guide/intro#basics
 * @param {string} subject CASL Subject // https://casl.js.org/v4/en/guide/intro#basics
 */
export const can = (action: string | undefined, subject: string | undefined) => {
  const vm = getCurrentInstance()

  if (!vm) return false

  const localCan = vm.proxy && '$can' in vm.proxy

  return localCan ? vm.proxy?.$can(action, subject) : true
}

/**
 * Check if user can view item based on it's ability
 * Based on item's action and subject & Hide group if all of it's children are hidden
 * @param {object} item navigation object item
 */
export const canViewNavMenuGroup = (item: NavGroup) => {
  if (item.alwaysShow) return can(item.action, item.subject)

  if (!item.children || !item.children.length) return can(item.action, item.subject)

  const hasAnyVisibleChild = item.children.some(i => can(i.action, i.subject))

  if (!(item.action && item.subject)) return hasAnyVisibleChild

  return can(item.action, item.subject) && hasAnyVisibleChild
}

export const canNavigate = async (to: RouteLocationNormalized) => {
  const targetRoute = to.matched[to.matched.length - 1]

  const requiresSuperAdmin =
    targetRoute?.meta?.requiresSuperAdmin ||
    targetRoute?.meta?.action === 'manage' ||
    targetRoute?.meta?.subject === 'SuperAdmin'

  if (requiresSuperAdmin) {
    try {
      const authStore = useAuthStore()
      const currentSuperAdmin = authStore.userData?.super_admin || false

      if (currentSuperAdmin) {
        return true
      }
    } catch (error) {
      logger.warn('[canNavigate] Failed to check super admin from userData', { error })
    }
  }

  let ability: any = null
  try {
    ability = useAbility()
  } catch (error) {
    logger.warn('[canNavigate] CASL ability not available, falling back to stored rules', { error })

    // Fall back to ability rules from auth store instead of failing open
    try {
      const authStore = useAuthStore()

      if (authStore.userData?.super_admin) {
        return true
      }

      const storedRules = authStore.abilityRules
      if (storedRules && storedRules.length > 0) {
        ability = createMongoAbility(storedRules)
      } else {
        // No stored rules and no CASL — deny by default
        return false
      }
    } catch (storeError) {
      logger.warn('[canNavigate] Could not build fallback ability from auth store', { error: storeError })
      return false
    }
  }

  if (targetRoute?.meta?.action && targetRoute?.meta?.subject) {
    return ability.can(targetRoute.meta.action, targetRoute.meta.subject)
  }

  return to.matched.some(route => {
    if (route.meta.action && route.meta.subject) {
      return ability.can(route.meta.action, route.meta.subject)
    }
    return true
  })
}
