import type { RouteLocationNormalized } from 'vue-router'
import type { RouteNamedMap, _RouterTyped } from 'unplugin-vue-router'
import { useSelectedOrg } from '@/composables/useSelectedOrg'
import type { UserData } from '@/services/auth'
import { getIsLoggingOut, hasExplicitlyLoggedOut, supabase } from '@/services/auth'
import { canNavigate } from '@/plugins/casl/navigation'
import { useAuthStore } from '@/stores/auth'
import { useOrgStore } from '@/stores/org'
import { logger } from '@/utils/logger'

function getOrgFromRoute(route: RouteLocationNormalized): string | null {
  const orgId = route.params.orgId as string
  return orgId || null
}

let cachedSuperAdmin: { value: boolean; at: number } | null = null
const SUPER_ADMIN_CACHE_TTL_MS = 60_000

export function clearSuperAdminCache() {
  cachedSuperAdmin = null
}

async function getSuperAdminStatus(force = false): Promise<boolean> {
  const now = Date.now()
  if (!force && cachedSuperAdmin && now - cachedSuperAdmin.at < SUPER_ADMIN_CACHE_TTL_MS) {
    return cachedSuperAdmin.value
  }

  const { data, error } = await supabase.functions.invoke('check-super-admin')
  if (error) throw error

  const value = data?.is_super_admin === true

  cachedSuperAdmin = { value, at: now }
  return value
}

export const setupGuards = (router: _RouterTyped<RouteNamedMap & { [key: string]: any }>) => {
  // 👉 router.beforeEach
  // Docs: https://router.vuejs.org/guide/advanced/navigation-guards.html#global-before-guards
  router.beforeEach(async to => {
    // Handle legacy URLs that don't have org context (must run before public route check)
    const legacyPaths = ['/agents', '/projects', '/data-sources', '/monitoring', '/scheduler', '/organization']
    const matchedLegacyPath = legacyPaths.find(path => to.path === path || to.path.startsWith(`${path}/`))

    if (matchedLegacyPath) {
      const orgStore = useOrgStore()

      // If user has a selected org, redirect to new org-scoped URL
      if (orgStore.selectedOrgId) {
        const newPath = to.path.replace(matchedLegacyPath, `/org/${orgStore.selectedOrgId}${matchedLegacyPath}`)
        return { path: newPath, replace: true }
      }

      return { name: 'login', replace: true }
    }

    /*
     * If it's a public route, continue navigation. This kind of pages are allowed to visited by login & non-login users. Basically, without any restrictions.
     * Examples of public routes are, 404, under maintenance, etc.
     */
    if (to.meta.public) return

    /**
     * Check if user is logged in by checking if token & user data exists in local storage
     * Feel free to update this logic to suit your needs
     */
    const authStore = useAuthStore()

    let isLoggedIn = authStore.isAuthenticated

    // Fallback: Check Supabase session if store isn't synced yet
    // But don't recover during logout process or if user has explicitly logged out
    if (!isLoggedIn && to.name !== 'login' && !getIsLoggingOut() && !hasExplicitlyLoggedOut()) {
      try {
        const {
          data: { session },
        } = await supabase.auth.getSession()

        if (session?.user) {
          logger.info('Router guard: Found valid Supabase session, recovering auth state')
          isLoggedIn = true

          if (!authStore.userData && session.user) {
            const recoveredUserData: UserData = {
              id: session.user.id,
              fullName: session.user.user_metadata.full_name || session.user.email?.split('@')[0],
              username: session.user.user_metadata.username || session.user.email?.split('@')[0],
              email: session.user.email,
              avatar:
                session.user.user_metadata.avatar_url ||
                session.user.user_metadata.picture ||
                session.user.user_metadata.photo ||
                null,
              role: session.user.user_metadata.role || 'client',
              super_admin: session.user.user_metadata.super_admin || false,
            }

            authStore.setAuth(recoveredUserData, session.access_token, authStore.abilityRules)
            logger.info('Router guard: Auto-recovered auth state from session')
          }
        }
      } catch (error) {
        logger.info('Router guard: Session check failed', { data: error })
      }
    }

    // Special case: If this is the reset-password page with a token, always allow access
    // This is because Supabase might create a temporary session during password reset
    if (to.name === 'reset-password' && (to.query.token || window.location.hash.includes('access_token'))) {
      return
    }

    // Handle pages that should only be accessible when not logged in (login, register, forgot-password)
    if (to.meta.unauthenticatedOnly) {
      return isLoggedIn ? '/' : undefined
    }

    // Always allow access to login when not logged in
    if (to.name === 'login') {
      // Clear explicit logout flag when user goes to login page
      if (hasExplicitlyLoggedOut()) {
        const { clearExplicitLogout } = await import('@/services/auth')

        clearExplicitLogout()
      }
      return isLoggedIn ? '/' : undefined
    }

    // If not logged in, redirect to login
    if (!isLoggedIn) {
      return {
        name: 'login',
        query: {
          to: to.fullPath !== '/' ? to.fullPath : undefined,
        },
      }
    }

    const userData = authStore.userData

    // Sync store from org in URL
    const orgId = getOrgFromRoute(to)
    if (orgId) {
      const orgStore = useOrgStore()

      // Only update if different from current
      if (orgStore.selectedOrgId !== orgId) {
        logger.info('[Guards] Syncing store to URL org', { data: orgId })

        // Fetch orgs if not loaded
        if (!orgStore.organizations.length && userData?.id) {
          try {
            await orgStore.fetchOrganizations(userData.id)
          } catch (error) {
            logger.error('[Guards] Failed to fetch organizations', { error })
            return { name: 'login', replace: true }
          }
        }

        const org = orgStore.organizations.find(o => o.id === orgId)
        if (org) {
          // Update store (silently, no navigation)
          orgStore.setSelectedOrg(orgId, org.role)
        } else {
          logger.warn('[Guards] Org not found in user memberships', { data: orgId })

          // User doesn't have access to this org
          // Redirect to their first available org, or home if they have orgs
          sessionStorage.setItem(
            'org_access_denied',
            JSON.stringify({
              attemptedOrgId: orgId,
              message: 'You do not have access to this organization',
            })
          )

          const firstOrg = orgStore.organizations[0]
          if (firstOrg) {
            return {
              path: `/org/${firstOrg.id}/projects`,
              replace: true,
            }
          } else {
            return { name: 'login', replace: true }
          }
        }
      }
    }

    const orgStore = useOrgStore()
    if (!orgStore.organizations.length && userData?.id) {
      try {
        await orgStore.fetchOrganizations(userData.id)
      } catch (error) {
        logger.error('[Guards] Failed to fetch organizations', { error })
        return { name: 'login', replace: true }
      }
    }

    // Get super admin status from userData (with short-lived backend cache fallback)
    let isSuperAdmin = userData?.super_admin || false

    // Get the selected org role from the composable
    const { isOrgAdmin, isOrgDataLoading, isOrgDataLoaded } = useSelectedOrg()

    // Routes with meta.allowAllAuthenticated bypass admin/role checks
    const ALLOW_ALL_ROUTE_NAMES = new Set([
      'index',
      'dashboards-crm',
      'org-org-id-projects',
      'org-org-id-projects-id',
      'org-org-id-agents',
      'org-org-id-agents-id',
      'org-org-id-scheduler',
      'org-org-id-monitoring',
      'org-org-id-data-sources',
    ])

    if (to.meta.allowAllAuthenticated || (to.name && ALLOW_ALL_ROUTE_NAMES.has(to.name as string))) {
      return
    }

    // For organization and variables pages, wait for org data to load before making decision
    if (to.name === 'org-org-id-organization' || to.name === 'org-org-id-variables') {
      // If org data is not ready yet, trigger a single fetch instead of polling
      if (!isOrgDataLoaded.value || isOrgDataLoading.value) {
        if (userData?.id) {
          try {
            await orgStore.fetchOrganizations(userData.id)
          } catch (error) {
            logger.error('[Guards] Failed to fetch organizations for admin check', { error })
            return { name: 'not-authorized' }
          }
        } else {
          return { name: 'not-authorized' }
        }
      }

      // Now check admin access with fresh data
      if (isSuperAdmin || isOrgAdmin.value) {
        return // Allow access
      }

      // Store may be stale — double-check super admin via cached API lookup
      try {
        const actualIsSuperAdmin = await getSuperAdminStatus()
        if (actualIsSuperAdmin) {
          isSuperAdmin = true
          if (userData) {
            authStore.updateUserData({ ...userData, super_admin: true })
          }
          return // Allow access
        }
      } catch (err) {
        logger.error('[Guards] Error checking super admin status', { error: err })
      }

      return { name: 'not-authorized' }
    }

    // Other admin-only routes
    if (
      (to.name === 'access-control' || to.meta.subject === 'Organization' || to.meta.subject === 'Acl') &&
      !isSuperAdmin
    ) {
      return { name: 'not-authorized' }
    }

    // Special routes for super admin - check API for accurate status
    if (to.meta.requiresSuperAdmin) {
      // If cookie says false, double-check with API in case user was recently promoted
      if (!isSuperAdmin) {
        try {
          const actualIsSuperAdmin = await getSuperAdminStatus()

          if (actualIsSuperAdmin) {
            isSuperAdmin = true
            if (userData) {
              authStore.updateUserData({ ...userData, super_admin: true })
            }
            return
          }
        } catch (err) {
          logger.error('[Guards] Error checking super admin status', { error: err })
        }
      }

      // Block if not super admin
      if (!isSuperAdmin) {
        return { name: 'not-authorized' }
      }
    }

    // Check CASL abilities for other routes
    if (!(await canNavigate(to))) {
      return { name: 'not-authorized' }
    }
  })
}
