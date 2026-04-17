import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { useAgentsQuery } from '@/composables/queries/useAgentsQuery'
import { type Project, useProjectsQuery } from '@/composables/queries/useProjectsQuery'
import { useOrgReleaseStagesQuery, useSuperAdminQuery } from '@/composables/queries/useReleaseStagesQuery'
import { useOrgStore } from '@/stores/org'
import { logger } from '@/utils/logger'

// Define a basic type for Nav items based on usage
interface NavLink {
  name?: string
  params?: Record<string, any>
  query?: Record<string, any>
}

export interface NavItem {
  title?: string
  icon?: { icon: string }
  to?: NavLink | string
  children?: NavItem[]
  heading?: string
  group?: 'build' | 'configure' | 'observe'
  badgeClass?: string
  badgeContent?: string
  action?: string | string[]
  subject?: string
  openOnHover?: boolean
  defaultOpen?: boolean
  toggleOnClick?: boolean
  class?: string
  exactPath?: boolean
  alwaysShow?: boolean
}

const dynamicNavItems = ref<NavItem[]>([])

export const initializeNavItems = async () => {
  const orgStore = useOrgStore()
  const { selectedOrgId, isOrgAdmin } = storeToRefs(orgStore)

  const {
    data: projects,
    refetch: fetchProjectsFromComposable,
    isLoading: loading,
    error,
  } = useProjectsQuery(selectedOrgId)

  const { data: agents, isLoading: agentsLoading, error: agentsError } = useAgentsQuery(selectedOrgId)
  const router = useRouter()

  const { data: isSuperAdmin } = useSuperAdminQuery()
  const { data: orgReleaseStages, refetch: fetchOrgReleaseStages } = useOrgReleaseStagesQuery(selectedOrgId)

  // Fetch initial data
  if (selectedOrgId.value) {
    await fetchOrgReleaseStages()
  }

  // Function to update navigation based on current projects and roles
  const updateDynamicNav = () => {
    // Early return if no meaningful data change
    const currentProjectCount = projects.value?.length || 0
    const currentAgentCount = (agents.value || []).length
    const currentIsAdmin = isSuperAdmin.value || isOrgAdmin.value

    const projectItems = (projects.value || []).map(
      (project: Project): NavItem => ({
        title: project.project_name,
        icon: { icon: 'tabler-folder' },
        to: {
          name: 'org-org-id-projects-id',
          params: { orgId: selectedOrgId.value, id: project.project_id },
        },
        action: 'read',
        subject: 'Project',
        exactPath: true,
      })
    )

    const agentItems = (agents.value || []).map(
      (agent): NavItem => ({
        title: agent.name,
        icon: { icon: 'tabler-robot' },
        to: { name: 'org-org-id-agents-id', params: { orgId: selectedOrgId.value, id: agent.id } },
        action: 'read',
        subject: 'Agent',
        exactPath: true,
      })
    )

    const currentNavs: NavItem[] = [{ heading: 'Others' }]

    // Add Super Admin Dashboard FIRST (highest priority)
    if (isSuperAdmin.value) {
      const superAdminItem = {
        title: 'Super Admin',
        icon: { icon: 'tabler-shield-check' },
        to: 'admin-super-admin',
        action: 'read',
        subject: 'all',
      }

      currentNavs.push(superAdminItem)
    }

    // Add standard navigation items in the requested order: Agents, Workflows, Knowledge, Settings

    currentNavs.push({
      title: 'Agents',
      icon: { icon: 'tabler-robot' },
      to: { name: 'org-org-id-agents', params: { orgId: selectedOrgId.value } },
      action: 'read',
      subject: 'Agent',
      group: 'build',
      alwaysShow: true,
    })

    currentNavs.push({
      title: 'Workflows',
      icon: { icon: 'tabler-route' },
      to: { name: 'org-org-id-projects', params: { orgId: selectedOrgId.value } },
      action: 'read',
      subject: 'Project',
      group: 'build',
      alwaysShow: true,
    })

    currentNavs.push({
      title: 'Scheduler',
      icon: { icon: 'tabler-calendar-time' },
      to: { name: 'org-org-id-scheduler', params: { orgId: selectedOrgId.value } },
      action: 'read',
      subject: 'CronJob',
      group: 'configure',
      alwaysShow: true,
    })

    currentNavs.push({
      title: 'Knowledge',
      icon: { icon: 'tabler-database' },
      to: { name: 'org-org-id-data-sources', params: { orgId: selectedOrgId.value } },
      action: 'read',
      subject: 'DataSource',
      group: 'configure',
    })

    currentNavs.push({
      title: 'Variables',
      icon: { icon: 'tabler-variable' },
      to: { name: 'org-org-id-variables', params: { orgId: selectedOrgId.value } },
      action: 'read',
      subject: 'Organization',
      group: 'configure',
    })

    currentNavs.push({
      title: 'Integrations',
      icon: { icon: 'tabler-plug-connected' },
      to: { name: 'org-org-id-connections', params: { orgId: selectedOrgId.value } },
      action: 'read',
      subject: 'Project',
      group: 'configure',
    })

    currentNavs.push({
      title: 'Runs',
      icon: { icon: 'tabler-player-play' },
      to: { name: 'org-org-id-runs', params: { orgId: selectedOrgId.value } },
      action: 'read',
      subject: 'Project',
      group: 'observe',
      alwaysShow: true,
    })

    currentNavs.push({
      title: 'Monitoring',
      icon: { icon: 'tabler-chart-line' },
      to: { name: 'org-org-id-monitoring', params: { orgId: selectedOrgId.value } },
      action: 'read',
      subject: 'Project',
      group: 'observe',
      alwaysShow: true,
    })

    // Settings (renamed from Organization) - when available for admins
    if (currentIsAdmin) {
      const settingsItem: NavItem = {
        title: 'Settings',
        icon: { icon: 'tabler-settings' },
        to: { name: 'org-org-id-organization', params: { orgId: selectedOrgId.value } },
        action: 'read',
        subject: 'Organization',
      }

      currentNavs.push(settingsItem)
    }
    dynamicNavItems.value = currentNavs
  }

  // Watch for changes that require nav update
  const isOnSuperAdmin = computed(() => router.currentRoute.value?.name === 'admin-super-admin')

  watch(
    [projects, agents, isOrgAdmin, isSuperAdmin, selectedOrgId],
    () => {
      updateDynamicNav()
    },
    { immediate: true } // Remove deep watching to improve performance
  )

  // Separate watcher for loading/error states to avoid unnecessary updates
  watch([loading, error, agentsLoading, agentsError], () => {
    if (!loading.value && !agentsLoading.value) {
      // Only update when loading is complete
      updateDynamicNav()
    }
  })

  // Watch for selectedOrgId to re-fetch projects when organization changes
  // Note: Agents query will automatically refetch when selectedOrgId changes (included in query key)
  watch(
    selectedOrgId,
    async (newOrgId, oldOrgId) => {
      if (newOrgId !== oldOrgId && newOrgId) {
        logger.info('Organization changed, refetching nav data')
        if (!isOnSuperAdmin.value) {
          // Fetch projects and release stage data
          // Agents will refetch automatically via TanStack Query when orgId changes
          await Promise.all([
            fetchProjectsFromComposable(), // refetch
            fetchOrgReleaseStages(),
          ])
          // updateDynamicNav will be triggered by the watchers above
        }
      }
    },
    { immediate: false }
  ) // No need for immediate here, initial fetch handled by watchers

  // Initial fetch of projects for the current/initial selectedOrgId
  // Agents will be fetched automatically via TanStack Query
  if (selectedOrgId.value && !isOnSuperAdmin.value) {
    await fetchProjectsFromComposable()
  }

  return dynamicNavItems // This is a Ref, DefaultLayoutWithVerticalNav watches it
}

export default dynamicNavItems
