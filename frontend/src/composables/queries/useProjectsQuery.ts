import { useAbility } from '@casl/vue'
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { type Ref, computed, ref, watch } from 'vue'
import { clearAllChatStates } from '@/composables/usePlaygroundChat'
import { scopeoApi } from '@/api'
import { logNetworkCall, logQueryStart } from '@/utils/queryLogger'
import { resolveUserEmail } from '@/utils/userEmail'
import { logger } from '@/utils/logger'

export interface GraphRunner {
  graph_runner_id: string
  env: string | null
  tag_name: string | null
}

export interface Project {
  project_id: string
  project_name: string
  description: string
  icon?: string
  icon_color?: string
  companion_image_url?: string
  organization_id?: string
  is_template?: boolean
  created_at?: string
  updated_at?: string
  graph_runners?: GraphRunner[] // Optional: only present when fetching individual project details
}

// Interface for project creation data
export interface CreateProjectData {
  project_name: string
  description?: string
  icon?: string
  icon_color?: string
  project_id?: string
  template?: {
    template_graph_runner_id: string
    template_project_id: string
  }
}

// --- Singleton State for current project and graph runner ---
const currentProject = ref<Project | null>(null)
const currentGraphRunner = ref<GraphRunner | null>(null)
const graphLastEditedTime = ref<string | null>(null)
const graphLastEditedUserId = ref<string | null>(null)
const graphLastEditedUserEmail = ref<string | null>(null)

const playgroundConfig = ref<{
  playground_input_schema?: Record<string, any>
  playground_field_types?: Record<string, 'messages' | 'json' | 'simple' | 'file'>
} | null>(null)
// --- End Singleton State ---

/**
 * Fetch all projects for an organization
 */
async function fetchProjects(
  organizationId: string,
  type?: 'AGENT' | 'WORKFLOW',
  includeTemplates?: boolean
): Promise<Project[]> {
  logNetworkCall(
    ['projects', organizationId, type, includeTemplates],
    `/projects/org/${organizationId}?type=${type}&include_templates=${includeTemplates}`
  )

  const data = await scopeoApi.projects.getByOrgId(organizationId, type, includeTemplates)
  return data || []
}

/**
 * Fetch a single project by ID with graph runners
 */
export async function fetchProject(projectId: string): Promise<Project> {
  logNetworkCall(['project', projectId], `/projects/${projectId}`)

  const data = await scopeoApi.projects.getById(projectId)
  if (!data) {
    throw new Error('Project not found')
  }
  return data
}

/**
 * Query: Fetch all projects for an organization
 */
export function useProjectsQuery(
  orgId: Ref<string | undefined>,
  type?: Ref<'AGENT' | 'WORKFLOW' | undefined> | 'AGENT' | 'WORKFLOW',
  includeTemplates?: Ref<boolean | undefined> | boolean
) {
  const typeValue = computed(() => (typeof type === 'object' ? type.value : type))

  const includeTemplatesValue = computed(() =>
    typeof includeTemplates === 'object' ? includeTemplates.value : includeTemplates
  )

  const queryKey = computed(() => ['projects', orgId.value, typeValue.value, includeTemplatesValue.value])

  logQueryStart(queryKey.value, 'useProjectsQuery')

  return useQuery({
    queryKey,
    queryFn: () => {
      if (!orgId.value) throw new Error('No organization ID provided')
      return fetchProjects(orgId.value, typeValue.value, includeTemplatesValue.value)
    },
    enabled: computed(() => !!orgId.value),
    staleTime: 1000 * 60 * 5,
    gcTime: 1000 * 60 * 30,
    refetchOnMount: true,
  })
}

/**
 * Query: Fetch a single project with graph runners
 */
export function useProjectQuery(projectId: Ref<string | undefined>) {
  const queryKey = computed(() => ['project', projectId.value])

  // Get ability for permission checks
  let ability: any = null
  try {
    ability = useAbility()
  } catch (error) {
    logger.warn('CASL ability not available, using limited fallback', { error })
    ability = {
      can: (action: string, subject: string) => {
        if (action === 'read' && ['all', 'Project'].includes(subject)) {
          return true
        }
        return false
      },
      cannot: () => false,
    }
  }

  logQueryStart(queryKey.value, 'useProjectQuery')

  const query = useQuery({
    queryKey,
    queryFn: async () => {
      if (!projectId.value) throw new Error('No project ID provided')
      return await fetchProject(projectId.value)
    },
    enabled: computed(() => !!projectId.value),
    staleTime: 1000 * 60 * 5,
    gcTime: 1000 * 60 * 30,
    refetchOnMount: true,
  })

  // Sync singleton state whenever query data changes — fires for BOTH cache hits and network responses.
  // Previously this lived inside queryFn, which meant cache hits left the singleton stale (A→B→A bug).
  watch(
    query.data,
    data => {
      if (!data) return

      const isProjectSwitching = currentProject.value?.project_id !== data.project_id

      if (isProjectSwitching) {
        currentGraphRunner.value = null
        playgroundConfig.value = null
        graphLastEditedTime.value = null
        graphLastEditedUserId.value = null
        graphLastEditedUserEmail.value = null
        clearAllChatStates()
      }

      currentProject.value = data

      const canUpdate = ability.can('update', 'Project')

      if (
        data?.graph_runners &&
        data.graph_runners.length > 0 &&
        (currentGraphRunner.value === null || isProjectSwitching)
      ) {
        const draftRunner = data.graph_runners.find((runner: GraphRunner) => runner.env === 'draft')
        const prodRunner = data.graph_runners.find((runner: GraphRunner) => runner.env === 'production')
        const validRunner = data.graph_runners.find((runner: GraphRunner) => runner.env && runner.env.trim() !== '')

        currentGraphRunner.value = canUpdate
          ? draftRunner || prodRunner || validRunner || data.graph_runners[0]
          : prodRunner || draftRunner || validRunner || data.graph_runners[0]
      }
    },
    { immediate: true }
  )

  return query
}

/**
 * Mutation: Create a new project
 */
export function useCreateProjectMutation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ orgId, projectData }: { orgId: string; projectData: CreateProjectData }) => {
      // Prepare the request body according to the API format
      const requestBody: any = {
        project_id: projectData.project_id,
        project_name: projectData.project_name,
        description: projectData.description || '',
        companion_image_url: '',
      }

      // Add icon and icon_color if provided
      if (projectData.icon) {
        requestBody.icon = projectData.icon
      }
      if (projectData.icon_color) {
        requestBody.icon_color = projectData.icon_color
      }

      // Add template data if provided
      if (projectData.template) {
        requestBody.template = {
          template_graph_runner_id: projectData.template.template_graph_runner_id,
          template_project_id: projectData.template.template_project_id,
        }
      }

      logNetworkCall(['create-project', orgId], `/projects/${orgId}`)

      return await scopeoApi.projects.create(orgId, requestBody)
    },
    onSuccess: (_data, variables) => {
      // Invalidate projects list for this organization
      queryClient.invalidateQueries({ queryKey: ['projects', variables.orgId] })
    },
  })
}

/**
 * Mutation: Update a project (name, description, icon, and/or icon_color)
 */
export function useUpdateProjectMutation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({
      projectId,
      data,
    }: {
      projectId: string
      data: { name?: string; description?: string; icon?: string; icon_color?: string }
    }) => {
      const updateData: any = {}
      if (data.name !== undefined) {
        updateData.project_name = data.name
      }
      if (data.description !== undefined) {
        updateData.description = data.description
      }
      if (data.icon !== undefined) {
        updateData.icon = data.icon
      }
      if (data.icon_color !== undefined) {
        updateData.icon_color = data.icon_color
      }

      logNetworkCall(['update-project', projectId], `/projects/${projectId}`)
      await scopeoApi.projects.updateProject(projectId, updateData)

      // Update the current project if it matches
      if (currentProject.value?.project_id === projectId) {
        if (data.name !== undefined) {
          currentProject.value.project_name = data.name
        }
        if (data.description !== undefined) {
          currentProject.value.description = data.description
        }
        if (data.icon !== undefined) {
          currentProject.value.icon = data.icon
        }
        if (data.icon_color !== undefined) {
          currentProject.value.icon_color = data.icon_color
        }
      }
    },
    onSuccess: (_data, variables) => {
      // Invalidate both the single project and projects list
      queryClient.invalidateQueries({ queryKey: ['project', variables.projectId] })
      queryClient.invalidateQueries({ queryKey: ['projects'] })
      queryClient.invalidateQueries({ queryKey: ['agents'] })
    },
  })
}

/**
 * Mutation: Delete a project
 */
export function useDeleteProjectMutation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (projectId: string) => {
      logNetworkCall(['delete-project', projectId], `/projects/${projectId}`)
      await scopeoApi.projects.delete(projectId)
    },
    onSuccess: (_data, projectId) => {
      // Clear current project if it's the deleted one
      if (currentProject.value?.project_id === projectId) {
        currentProject.value = null
        currentGraphRunner.value = null
      }

      // Optimistically remove deleted project from all cached queries for immediate UI update
      queryClient.setQueriesData(
        {
          predicate: query => query.queryKey[0] === 'projects',
        },
        (oldData: Project[] | undefined) => {
          if (!oldData) return oldData
          return oldData.filter(p => p.project_id !== projectId)
        }
      )

      // Invalidate queries to mark as stale for background refetch
      // This allows the optimistic update to show immediately while ensuring fresh data
      queryClient.invalidateQueries({ queryKey: ['projects'] })
      queryClient.invalidateQueries({ queryKey: ['project', projectId] })
      queryClient.invalidateQueries({ queryKey: ['agents'] })
      queryClient.invalidateQueries({ queryKey: ['cron-jobs'] })
    },
  })
}

/**
 * Mutation: Duplicate a project using the template mechanism
 */
export function useDuplicateProjectMutation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({
      orgId,
      projectId,
      graphRunnerId,
      name,
    }: {
      orgId: string
      projectId: string
      graphRunnerId: string
      name: string
    }) => {
      // Generate a new UUID for the duplicated project
      const newProjectId = crypto.randomUUID()

      // Create project using template (which clones the graph runner)
      const createData = {
        project_id: newProjectId,
        project_name: name,
        description: '',
        template: {
          template_graph_runner_id: graphRunnerId,
          template_project_id: projectId,
        },
      }

      logNetworkCall(['create-duplicate-project', orgId], `/projects/${orgId}`)

      return await scopeoApi.projects.create(orgId, createData)
    },
    onSuccess: () => {
      // Invalidate projects list to refresh with the new duplicate
      queryClient.invalidateQueries({ queryKey: ['projects'] })
    },
  })
}

// --- Modification History Types ---
export interface ModificationHistoryItem {
  time: string
  user_id: string
  email?: string
}

/**
 * Query: Fetch modification history for a graph runner (lazy loaded)
 * Only fetches when enabled is true - use for dialog/modal scenarios
 */
export function useModificationHistoryQuery(
  projectId: Ref<string | undefined>,
  graphRunnerId: Ref<string | undefined>,
  orgId: Ref<string | undefined>,
  enabled: Ref<boolean>
) {
  const queryKey = computed(() => ['modification-history', projectId.value, graphRunnerId.value])

  return useQuery({
    queryKey,
    queryFn: async (): Promise<ModificationHistoryItem[]> => {
      if (!projectId.value || !graphRunnerId.value) {
        return []
      }

      logNetworkCall(queryKey.value, `/studio/modification-history/${projectId.value}/${graphRunnerId.value}`)

      const data = await scopeoApi.studio.getModificationHistory(projectId.value, graphRunnerId.value)
      const historyItems: ModificationHistoryItem[] = Array.isArray(data?.history) ? data.history : []

      // Resolve all emails in a single batch call
      if (historyItems.length > 0 && orgId.value) {
        const { resolveUserEmailsBatch } = await import('@/utils/userEmail')
        const userIds = historyItems.map(item => item.user_id).filter(Boolean)
        const uniqueUserIds = [...new Set(userIds)]

        const emailMap = await resolveUserEmailsBatch(uniqueUserIds, orgId.value)

        // Map emails back to history items
        for (const item of historyItems) {
          if (item.user_id && emailMap.has(item.user_id)) {
            item.email = emailMap.get(item.user_id)
          }
        }
      }

      return historyItems
    },
    enabled: computed(() => enabled.value && !!projectId.value && !!graphRunnerId.value),
    staleTime: 30 * 1000, // 30 seconds - history changes infrequently
  })
}

/**
 * Composable to manage current project and graph runner state
 * This provides the same interface as the original useProjects composable
 */
export function useCurrentProject() {
  return {
    currentProject,
    currentGraphRunner,
    graphLastEditedTime,
    graphLastEditedUserId,
    graphLastEditedUserEmail,
    playgroundConfig,

    /**
     * Set the current graph runner
     */
    setCurrentGraphRunner: (graphRunner: GraphRunner) => {
      // Only update if the value is actually different
      if (!currentGraphRunner.value || currentGraphRunner.value.graph_runner_id !== graphRunner.graph_runner_id) {
        currentGraphRunner.value = graphRunner

        // Note: In the original implementation, this would refetch the project.
        // With TanStack Query, we rely on the component to refetch if needed.
      }
    },

    /**
     * Set the playground configuration
     */
    setPlaygroundConfig: (
      config: {
        playground_input_schema?: Record<string, any>
        playground_field_types?: Record<string, 'messages' | 'json' | 'simple'>
      } | null
    ) => {
      playgroundConfig.value = config
    },

    /**
     * Set the graph last edited info and resolve user email
     */
    setGraphLastEditedInfo: async (lastEditedTime: string | null, lastEditedUserId: string | null, orgId?: string) => {
      graphLastEditedTime.value = lastEditedTime
      graphLastEditedUserId.value = lastEditedUserId
      graphLastEditedUserEmail.value = null

      // Resolve email if we have userId and orgId
      if (lastEditedUserId && orgId) {
        const email = await resolveUserEmail(lastEditedUserId, orgId)

        graphLastEditedUserEmail.value = email
      }
    },

    /**
     * Clear current project state (useful when navigating away)
     */
    clearCurrentProject: () => {
      currentProject.value = null
      currentGraphRunner.value = null
      graphLastEditedTime.value = null
      graphLastEditedUserId.value = null
      graphLastEditedUserEmail.value = null
      playgroundConfig.value = null
    },
  }
}
