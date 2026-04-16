import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import * as Sentry from '@sentry/vue'
import { supabase } from '@/services/auth'
import { useAuthStore } from '@/stores/auth'
import { generateAbilityRules, updateAbilitySystem } from '@/utils/abilityRules'
import { logger } from '@/utils/logger'

interface Organization {
  id: string
  name: string
  role: string
}

export const useOrgStore = defineStore('org', () => {
  // State
  const selectedOrgId = ref<string>('')
  const selectedOrgRole = ref<string>('')
  const isLoading = ref(true)
  const isLoaded = ref(false)
  const organizations = ref<Organization[]>([])
  const fetchPromise = ref<Promise<void> | null>(null)

  // Getters
  const isOrgAdmin = computed(() => {
    if (isLoading.value) return false
    return selectedOrgRole.value?.toLowerCase() === 'admin'
  })

  const currentOrg = computed(() => {
    return organizations.value.find(org => org.id === selectedOrgId.value)
  })

  const hasMultipleOrgs = computed(() => {
    return organizations.value.length > 1
  })

  // Actions
  function initialize() {
    logger.info('[OrgStore] Initializing...')

    if (typeof window === 'undefined') {
      isLoading.value = false
      return
    }

    const storedOrgId = localStorage.getItem('selectedOrgId')
    const storedOrgRole = localStorage.getItem('selectedOrgRole')

    if (storedOrgId && storedOrgRole) {
      logger.info('[OrgStore] Loading from localStorage', { storedOrgId, storedOrgRole })
      selectedOrgId.value = storedOrgId
      selectedOrgRole.value = storedOrgRole
      isLoaded.value = true
      isLoading.value = false

      // Regenerate CASL abilities from stored role
      const authStore = useAuthStore()
      const abilityRules = generateAbilityRules(storedOrgRole, authStore.userData)

      updateAbilitySystem(abilityRules)

      logger.info('[OrgStore] Initialized from storage with abilities')
    } else {
      logger.info('[OrgStore] No stored org data found')
      isLoading.value = false
    }
  }

  async function fetchOrganizations(userId: string, force = false): Promise<void> {
    logger.info('[OrgStore] fetchOrganizations called', { userId, force, hasInFlightPromise: !!fetchPromise.value })

    // Return existing promise if in-flight (unless force = true)
    if (fetchPromise.value && !force) {
      logger.info('[OrgStore] Returning in-flight promise (deduplication)')
      return fetchPromise.value
    }

    isLoading.value = true

    const promise = (async () => {
      try {
        logger.info('[OrgStore] Starting fresh organization data fetch', { data: userId })

        // Get session to ensure we have authentication
        logger.info('[OrgStore] Checking auth session...')

        const { data: sessionData, error: sessionError } = await supabase.auth.getSession()
        if (sessionError || !sessionData.session) {
          logger.error('[OrgStore] No session found', { error: sessionError })
          isLoaded.value = true
          isLoading.value = false
          return
        }

        logger.info('[OrgStore] Session found, querying organization_members...')

        // Fetch user's organizations and roles from organization_members table
        const { data: memberships, error: membershipError } = await supabase
          .from('organization_members')
          .select('org_id, role')
          .eq('user_id', userId)

        logger.info('[OrgStore] organization_members query result', {
          data: { count: memberships?.length, error: membershipError?.message },
        })

        if (membershipError) {
          logger.error('[OrgStore] Error fetching organization memberships', { error: membershipError })
          isLoaded.value = true
          isLoading.value = false
          return
        }

        if (memberships.length === 0) {
          logger.warn('[OrgStore] No organization memberships found for user', { data: userId })

          Sentry.addBreadcrumb({ category: 'org', message: `No org memberships for user ${userId}`, level: 'warning' })
          isLoaded.value = true
          isLoading.value = false
          return
        }

        // Get the org IDs from memberships
        const orgIds = memberships.map(membership => membership.org_id)

        // Fetch organization details
        const { data: orgs, error: orgsError } = await supabase
          .from('organizations')
          .select('id, name')
          .in('id', orgIds)

        if (orgsError) {
          logger.error('[OrgStore] Error fetching organizations', { error: orgsError })
          isLoaded.value = true
          isLoading.value = false
          return
        }

        // Combine organization details with roles
        organizations.value = orgs.map(org => {
          const membership = memberships.find(m => m.org_id === org.id)
          const role = membership?.role || ''

          logger.info(`[OrgStore] Organization ${org.name} (${org.id}) has role: ${role}`)
          return {
            id: org.id,
            name: org.name,
            role,
          }
        })

        logger.info(`[OrgStore] Fetched ${organizations.value.length} organizations`)

        // Validate stored org is still valid
        if (selectedOrgId.value) {
          const isStillValid = organizations.value.some(org => org.id === selectedOrgId.value)
          if (!isStillValid) {
            logger.warn(
              `[OrgStore] Previously selected org ${selectedOrgId.value} is no longer available - user must select new org`
            )
            clearOrg()
            organizations.value = orgs.map(org => {
              const membership = memberships.find(m => m.org_id === org.id)
              return { id: org.id, name: org.name, role: membership?.role || '' }
            })
          }
        }

        // Auto-select first org when none is selected (e.g. after logout → login)
        if (!selectedOrgId.value && organizations.value.length > 0) {
          const firstOrg = organizations.value[0]

          setSelectedOrg(firstOrg.id, firstOrg.role)
          logger.info('[OrgStore] Auto-selected first org after fetch', { data: firstOrg.id })
        }

        isLoaded.value = true
        isLoading.value = false
        logger.info('[OrgStore] Organization data fetch completed successfully')
      } catch (error) {
        logger.error('[OrgStore] Error in fetchOrganizations', { error })
        isLoaded.value = true
        isLoading.value = false
      } finally {
        fetchPromise.value = null
      }
    })()

    fetchPromise.value = promise
    return promise
  }

  function setSelectedOrg(orgId: string, role: string) {
    const prevOrgId = selectedOrgId.value
    const prevRole = selectedOrgRole.value

    // CRITICAL: Guard clause - skip if no actual change
    if (prevOrgId === orgId && prevRole === role) {
      logger.info(`[OrgStore] setSelectedOrg called but no change detected (${orgId}, ${role}) - skipping`)
      return
    }

    logger.info(`[OrgStore] setSelectedOrg: changing from (${prevOrgId}, ${prevRole}) to (${orgId}, ${role})`)

    selectedOrgId.value = orgId
    selectedOrgRole.value = role

    // Persist to localStorage
    if (typeof window !== 'undefined') {
      localStorage.setItem('selectedOrgId', orgId)
      localStorage.setItem('selectedOrgRole', role)
    }

    // Generate CASL abilities
    const authStore = useAuthStore()
    const abilityRules = generateAbilityRules(role, authStore.userData)

    updateAbilitySystem(abilityRules)

    // Set Sentry organization context
    const org = organizations.value.find(o => o.id === orgId)

    Sentry.setContext('organization', { orgId, orgName: org?.name ?? null })

    // Mark as loaded
    isLoaded.value = true
    isLoading.value = false

    logger.info('[OrgStore] Organization changed and abilities updated')
  }

  function clearOrg() {
    logger.info('[OrgStore] Clearing organization state')
    selectedOrgId.value = ''
    selectedOrgRole.value = ''
    organizations.value = []
    isLoaded.value = false
    isLoading.value = true
    fetchPromise.value = null

    if (typeof window !== 'undefined') {
      localStorage.removeItem('selectedOrgId')
      localStorage.removeItem('selectedOrgRole')
    }
  }

  // Initialize on store creation
  initialize()

  return {
    // State
    selectedOrgId,
    selectedOrgRole,
    isLoading,
    isLoaded,
    organizations,

    // Getters
    isOrgAdmin,
    currentOrg,
    hasMultipleOrgs,

    // Actions
    initialize,
    fetchOrganizations,
    setSelectedOrg,
    clearOrg,
  }
})
