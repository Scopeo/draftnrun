import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { type Ref, computed, ref, watch } from 'vue'
import { getComponentDefinitionFromCache, useComponentDefinitionsQuery } from './useComponentDefinitionsQuery'
import { scopeoApi } from '@/api'
import { logNetworkCall, logQueryStart } from '@/utils/queryLogger'
import {
  ensureProviderModelFormat,
  extractToolData,
  filterInputParameters,
  transformBackendParametersToLegacy,
  transformModelParametersToConfig,
} from '@/utils/agentUtils'
import { useSelectedOrg } from '@/composables/useSelectedOrg'
import { logger } from '@/utils/logger'

// Backend API Schema Interfaces
export interface BackendAgentParameter {
  id: string
  name: string
  type: string
  nullable: boolean
  default: string | number | boolean | null
  value: string | number | boolean | null
  display_order: number | null
  ui_component: string | null
  ui_component_properties: Record<string, any> | null
  is_advanced: boolean
  kind?: 'parameter' | 'input'
}

export interface BackendAgentTool {
  id?: string
  name: string
  component_id: string
  component_version_id: string
  version_tag?: string
  component_name: string
  component_description: string | null
  parameters: BackendAgentParameter[]
  tool_description: any
  is_start_node: boolean
  child_component_instance_id?: string
}

export interface BackendAgentInfo {
  name: string
  description: string | null
  organization_id: string
  system_prompt: string
  model_parameters: BackendAgentParameter[]
  tools: BackendAgentTool[]
  last_edited_time?: string | null
  last_edited_user_id?: string | null
  graph_runners?: GraphRunner[]
}

export interface GraphRunner {
  graph_runner_id: string
  env: string | null
  tag_name: string | null
}

export interface BackendProjectAgent {
  id: string
  name: string
  description: string | null
  graph_runners?: GraphRunner[]
}

export interface AgentSchema {
  id?: string
  name: string
  description?: string
  organization_id: string
  system_prompt: string
  model_config: {
    model: string
    temperature: number
    max_tokens?: number
    top_p?: number
    frequency_penalty?: number
    presence_penalty?: number
  }
  tools: Array<{
    name: string
    description: string
    parameters: Record<string, any>
    required?: string[]
  }>
  parameters?: Array<{
    name: string
    type: string
    value: any
    nullable: boolean
    description?: string
  }>
}

export interface Agent {
  id: string
  project_id?: string
  version_id?: string
  name: string
  description: string
  icon?: string
  icon_color?: string
  organization_id: string
  created_by: string
  created_at: string
  updated_at: string
  system_prompt: string
  model_config: Record<string, any>
  tools: Array<{ component_id: string; component_version_id: string; version_tag?: string }>
  toolInstanceIds?: Record<string, string>
  toolParameters?: Record<string, Record<string, any>>
  toolSchemas?: Record<
    string,
    {
      name: string
      component_description: string | null
      parameters: BackendAgentParameter[]
      tool_description: any
    }
  >
  parameters?: Array<{
    name: string
    type: string
    value: any
    default?: any
    nullable: boolean
    is_advanced?: boolean
    display_order?: number | null
    description?: string
    ui_component?: string | null
    ui_component_properties?: Record<string, any> | null
  }>
  is_template: boolean
  tags: string[]
  graph_config: Record<string, any>
  usage_count: number
  last_used_at: string
  last_edited_time?: string | null
  last_edited_user_id?: string | null
  last_edited_user_email?: string | null
  graph_runners?: GraphRunner[]
}

export interface AgentCreateData {
  id: string
  name: string
  description?: string
  icon?: string
  icon_color?: string
  template?: {
    template_graph_runner_id: string
    template_project_id: string
  }
}

export interface AgentUpdateData {
  name?: string
  description?: string
  system_prompt?: string
  model_config?: Record<string, any>
  tools?: Array<any>
  parameters?: Array<any>
  initial_prompt?: string
}

// --- Singleton State ---
const currentAgent = ref<Agent | null>(null)
const currentGraphRunner = ref<GraphRunner | null>(null)
const savingState = ref<Record<string, boolean>>({})
const saveErrors = ref<Record<string, string | null>>({})

/**
 * Query: Fetch all agents for an organization
 */
export function useAgentsQuery(orgId: Ref<string | undefined>) {
  const queryKey = computed(() => ['agents', orgId.value] as const)

  return useQuery<BackendProjectAgent[]>({
    queryKey,
    queryFn: async () => {
      logQueryStart(['agents', orgId.value], 'useAgentsQuery')

      if (!orgId.value) {
        return []
      }

      logNetworkCall(['agents', orgId.value], `/organizations/${orgId.value}/agents`)

      const data = await scopeoApi.agents.getAll(orgId.value)
      return data || []
    },
    enabled: computed(() => !!orgId.value),
    staleTime: 1000 * 60 * 5,
    gcTime: 1000 * 60 * 30,
    refetchOnMount: true,
  })
}

/**
 * Fetch and transform a single agent by ID and version.
 * Shared between useAgentQuery and prefetching.
 */
export async function fetchAgentDetail(agentId: string, versionId: string): Promise<Agent> {
  logNetworkCall(['agent', agentId, versionId], `/agents/${agentId}/versions/${versionId}`)

  const backendAgent: BackendAgentInfo = await scopeoApi.agents.getById(agentId, versionId)

  const { toolParameters, toolInstanceIds, toolSchemas } = extractToolData(backendAgent.tools || [])

  let lastEditedUserEmail: string | null = null
  if (backendAgent.last_edited_user_id) {
    try {
      const { resolveUserEmail } = await import('@/utils/userEmail')
      const { selectedOrgId } = useSelectedOrg()
      if (selectedOrgId.value) {
        lastEditedUserEmail = await resolveUserEmail(backendAgent.last_edited_user_id, selectedOrgId.value)
      }
    } catch (e) {
      logger.warn('[fetchAgentDetail] Could not resolve user email', { error: e })
    }
  }

  return {
    id: agentId,
    version_id: versionId,
    name: backendAgent.name,
    description: backendAgent.description || '',
    organization_id: backendAgent.organization_id,
    system_prompt: backendAgent.system_prompt,
    model_config: transformModelParametersToConfig(backendAgent.model_parameters || []),
    tools: (backendAgent.tools || [])
      .map(tool => ({
        component_id: tool.component_id,
        component_version_id: tool.component_version_id,
        version_tag: tool.version_tag,
      }))
      .filter(t => t.component_id && t.component_version_id),
    toolInstanceIds,
    toolParameters,
    toolSchemas,
    parameters: transformBackendParametersToLegacy(backendAgent.model_parameters || []),
    created_by: 'system',
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    is_template: false,
    tags: [],
    graph_config: {},
    usage_count: 0,
    last_used_at: new Date().toISOString(),
    last_edited_time: backendAgent.last_edited_time || null,
    last_edited_user_id: backendAgent.last_edited_user_id || null,
    last_edited_user_email: lastEditedUserEmail,
    graph_runners: backendAgent.graph_runners || [],
  }
}

/**
 * Fetches a single agent by ID and version with full transformation
 */
export function useAgentQuery(
  agentId: Ref<string | undefined>,
  versionId: Ref<string | undefined>,
  options?: { enabled?: Ref<boolean> }
) {
  const queryKey = computed(() => ['agent', agentId.value, versionId.value] as const)

  return useQuery<Agent | null>({
    queryKey,
    queryFn: async () => {
      logQueryStart(['agent', agentId.value, versionId.value], 'useAgentQuery')

      if (!agentId.value || !versionId.value) {
        return null
      }

      const agent = await fetchAgentDetail(agentId.value, versionId.value)

      currentAgent.value = agent

      return agent
    },
    enabled: computed(() => (options?.enabled?.value ?? true) && !!agentId.value && !!versionId.value),
    staleTime: 1000 * 60,
    refetchOnMount: false,
  })
}

/**
 * Mutation to create a new agent
 */
export function useCreateAgentMutation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ orgId, data }: { orgId: string; data: AgentCreateData }) => {
      logNetworkCall(['create-agent'], `/organizations/${orgId}/agents`)
      return await scopeoApi.agents.create(orgId, data)
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['agents', variables.orgId] })
    },
  })
}

/**
 * Mutation to update an agent with full save logic
 */
export function useUpdateAgentMutation() {
  const queryClient = useQueryClient()
  const { selectedOrgId } = useSelectedOrg()
  const { components: componentDefinitions } = useComponentDefinitionsQuery(selectedOrgId)

  return useMutation({
    mutationFn: async ({
      agentId,
      versionId,
      data,
      cachedAgent,
    }: {
      agentId: string
      versionId: string
      data: AgentUpdateData
      cachedAgent?: Agent | null
    }) => {
      savingState.value[agentId] = true
      saveErrors.value[agentId] = null

      try {
        logNetworkCall(['update-agent', agentId, versionId], `/agents/${agentId}/versions/${versionId}`)

        // Get current agent state from API
        const currentAgent = await scopeoApi.agents.getById(agentId, versionId)

        // Build model parameters
        const modelParameters: Array<{ name: string; value: any }> = []

        if (currentAgent.model_parameters && Array.isArray(currentAgent.model_parameters)) {
          currentAgent.model_parameters.forEach((param: BackendAgentParameter) => {
            const updatedParam = { name: param.name, value: param.value }
            const uiUpdatedParam = cachedAgent?.parameters?.find(p => p.name === param.name)

            if (param.name === 'completion_model') {
              const modelValue = uiUpdatedParam?.value || data.model_config?.model || param.value || param.default

              updatedParam.value = ensureProviderModelFormat(String(modelValue))
            } else if (param.name === 'default_temperature') {
              updatedParam.value =
                uiUpdatedParam?.value !== undefined
                  ? uiUpdatedParam.value
                  : data.model_config?.temperature || param.value || param.default
            } else if (param.name === 'initial_prompt') {
              const uiValue = uiUpdatedParam?.value

              updatedParam.value =
                uiValue !== undefined
                  ? uiValue
                  : data.initial_prompt !== undefined
                    ? data.initial_prompt
                    : (data.system_prompt ?? (param.value !== undefined ? param.value : param.default))
            } else {
              updatedParam.value =
                uiUpdatedParam?.value !== undefined
                  ? uiUpdatedParam.value
                  : param.value !== undefined
                    ? param.value
                    : param.default
            }

            modelParameters.push(updatedParam)
          })
        } else {
          modelParameters.push({
            name: 'completion_model',
            value: ensureProviderModelFormat(data.model_config?.model || 'openai:gpt-4o'),
          })

          const uiInitialParam = cachedAgent?.parameters?.find(p => p.name === 'initial_prompt')?.value

          modelParameters.push({
            name: 'initial_prompt',
            value: uiInitialParam !== undefined ? uiInitialParam : (data.initial_prompt ?? data.system_prompt ?? ''),
          })
        }

        // Transform tools
        let transformedTools: BackendAgentTool[] = []
        if (data.tools && Array.isArray(data.tools)) {
          transformedTools = data.tools
            .map((tool: any) => {
              const toolId = typeof tool === 'string' ? tool : tool.id || tool.component_version_id || tool.component_id

              const componentVersionId =
                typeof tool === 'object' && tool.component_version_id ? tool.component_version_id : toolId

              // Check for saved schema
              const savedToolInfo = cachedAgent?.toolSchemas?.[componentVersionId]

              if (savedToolInfo) {
                const customToolParams = cachedAgent?.toolParameters?.[toolId] || {}
                const componentId = tool.component_id
                const existingInstanceId = cachedAgent?.toolInstanceIds?.[componentId]

                // Get valid parameter names from component definition to filter out agent-level params
                const componentDef = componentDefinitions.value
                  ? getComponentDefinitionFromCache(componentDefinitions.value, componentVersionId)
                  : null

                const validParamNames = new Set(componentDef?.parameters?.map((p: any) => p.name) || [])

                return {
                  ...(existingInstanceId && { id: existingInstanceId }),
                  name: savedToolInfo.name,
                  component_id: componentId,
                  component_version_id: componentVersionId,
                  component_name: savedToolInfo.name,
                  component_description: savedToolInfo.component_description,
                  parameters: filterInputParameters(savedToolInfo.parameters)
                    .filter(param => validParamNames.size === 0 || validParamNames.has(param.name))
                    .map(param => ({
                      ...param,
                      value: customToolParams[param.name] !== undefined ? customToolParams[param.name] : param.value,
                    })),
                  tool_description: savedToolInfo.tool_description,
                  is_start_node: false,
                  ...(existingInstanceId && { child_component_instance_id: existingInstanceId }),
                } as BackendAgentTool
              } else if (componentDefinitions.value) {
                const componentDef = getComponentDefinitionFromCache(componentDefinitions.value, toolId)

                if (componentDef) {
                  const customToolParams = cachedAgent?.toolParameters?.[toolId] || {}
                  const componentId = componentDef.component_id || componentDef.id || ''
                  const existingInstanceId = cachedAgent?.toolInstanceIds?.[componentId]

                  return {
                    ...(existingInstanceId && { id: existingInstanceId }),
                    name: componentDef.name,
                    component_id: componentId,
                    component_version_id: componentVersionId,
                    component_name: componentDef.name,
                    component_description: componentDef.description || null,
                    parameters:
                      filterInputParameters(componentDef.parameters).map((param: any) => ({
                        id: param.name,
                        name: param.name,
                        type: param.type,
                        nullable: param.nullable ?? false,
                        default: param.default ?? null,
                        value:
                          customToolParams[param.name] !== undefined
                            ? customToolParams[param.name]
                            : (param.default ?? null),
                        display_order: param.display_order ?? null,
                        ui_component: param.ui_component ?? null,
                        ui_component_properties: param.ui_component_properties ?? null,
                        is_advanced: param.is_advanced ?? false,
                      })) || [],
                    tool_description: componentDef.tool_description || null,
                    is_start_node: false,
                    ...(existingInstanceId && { child_component_instance_id: existingInstanceId }),
                  } as BackendAgentTool
                }
              }
              return null
            })
            .filter((t): t is BackendAgentTool => t !== null)
        } else if (currentAgent.tools) {
          transformedTools = currentAgent.tools
        }

        const initialPromptParam = modelParameters.find(p => p.name === 'initial_prompt')
        const systemPrompt = initialPromptParam?.value ?? data.initial_prompt ?? data.system_prompt ?? ''

        const updateData = {
          name: data.name || '',
          description: data.description || '',
          organization_id: selectedOrgId.value,
          system_prompt: systemPrompt,
          model_parameters: modelParameters,
          tools: transformedTools,
        }

        return await scopeoApi.agents.update(agentId, versionId, updateData)
      } finally {
        savingState.value[agentId] = false
      }
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['agent', variables.agentId] })
      queryClient.invalidateQueries({ queryKey: ['agents'] })
      queryClient.invalidateQueries({ queryKey: ['modification-history', variables.agentId, variables.versionId] })
    },
    onError: (error, variables) => {
      saveErrors.value[variables.agentId] = error instanceof Error ? error.message : 'Failed to save agent'
    },
  })
}

/**
 * Mutation to delete an agent
 */
export function useDeleteAgentMutation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ agentId, orgId }: { agentId: string; orgId: string }) => {
      logNetworkCall(['delete-agent', agentId], `/projects/${agentId}`)
      return await scopeoApi.projects.delete(agentId)
    },
    onSuccess: (_data, variables) => {
      // Also invalidate projects queries since agents are also projects
      queryClient.invalidateQueries({ queryKey: ['projects'] })

      // Invalidate and remove queries
      queryClient.invalidateQueries({ queryKey: ['agents', variables.orgId] })
      queryClient.removeQueries({ queryKey: ['agent', variables.agentId] })
    },
  })
}

/**
 * Mutation to deploy an agent
 */
export function useDeployAgentMutation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ agentId, versionId }: { agentId: string; versionId: string }) => {
      logNetworkCall(['deploy-agent', agentId, versionId], `/agents/${agentId}/versions/${versionId}/deploy`)
      return await scopeoApi.agents.deploy(agentId, versionId)
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['agent', variables.agentId] })
      queryClient.invalidateQueries({ queryKey: ['agents'] })
    },
  })
}

/**
 * Validate tools before saving
 */
export async function validateAgentTools(
  tools: any[],
  componentDefinitions: any[] | undefined
): Promise<{ valid: boolean; errors: string[] }> {
  const errors: string[] = []

  if (!tools || tools.length === 0) {
    return { valid: true, errors: [] }
  }

  if (!componentDefinitions) {
    errors.push('Component definitions not loaded yet')
    return { valid: false, errors }
  }

  for (const tool of tools) {
    const toolId = typeof tool === 'string' ? tool : tool.id || tool.component_id
    const componentDef = getComponentDefinitionFromCache(componentDefinitions, toolId)

    if (!componentDef) {
      errors.push(`Component definition not found for tool: ${toolId}`)
      continue
    }

    if (componentDef.parameters && Array.isArray(componentDef.parameters)) {
      for (const param of componentDef.parameters) {
        const isComponentType = param.type === 'component'
        const isRequired = param.nullable === false

        if (isRequired && isComponentType) {
          const hasValue = param.default !== null && param.default !== undefined

          if (!hasValue) {
            errors.push(
              `Tool "${componentDef.name}" requires configuration of "${param.name}" (component) which cannot be configured in agent mode.`
            )
          }
        }
      }
    }
  }

  return { valid: errors.length === 0, errors }
}

/**
 * Composable to manage current agent and graph runner state
 */
export function useCurrentAgent() {
  const { selectedOrgId, orgChangeCounter } = useSelectedOrg()

  // Watch for org changes to clear state
  watch(orgChangeCounter, () => {
    currentAgent.value = null
    currentGraphRunner.value = null
  })

  return {
    currentAgent,
    currentGraphRunner,
    savingState,
    saveErrors,

    setCurrentGraphRunner: (graphRunner: GraphRunner) => {
      if (!currentGraphRunner.value || currentGraphRunner.value.graph_runner_id !== graphRunner.graph_runner_id) {
        currentGraphRunner.value = graphRunner
      }
    },

    clearCurrentAgent: () => {
      currentAgent.value = null
      currentGraphRunner.value = null
    },
  }
}
