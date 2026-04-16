import type { BackendAgentParameter, BackendAgentTool } from '@/composables/queries/useAgentsQuery'

/**
 * Transform model parameters from backend format to config object
 */
export function transformModelParametersToConfig(modelParameters: BackendAgentParameter[]): Record<string, any> {
  const config: Record<string, any> = {}

  modelParameters.forEach(param => {
    switch (param.name) {
      case 'completion_model':
        config.model = param.value ?? param.default ?? 'gpt-4'
        break
      case 'default_temperature':
        config.temperature = param.value ?? param.default ?? 0.7
        break
      case 'max_tokens':
        config.max_tokens = param.value ?? param.default
        break
      case 'top_p':
        config.top_p = param.value ?? param.default
        break
      case 'frequency_penalty':
        config.frequency_penalty = param.value ?? param.default
        break
      case 'presence_penalty':
        config.presence_penalty = param.value ?? param.default
        break
    }
  })

  return config
}

/**
 * Transform backend parameters to legacy format
 */
export function transformBackendParametersToLegacy(parameters: BackendAgentParameter[]): any[] {
  return parameters.map(param => ({
    name: param.name,
    type: param.type,
    value: param.value ?? param.default,
    default: param.default,
    nullable: param.nullable,
    is_advanced: param.is_advanced,
    display_order: param.display_order,
    description: '',
    ui_component: param.ui_component,
    ui_component_properties: param.ui_component_properties,
  }))
}

/**
 * Ensure model format is provider:model
 */
export function ensureProviderModelFormat(model: string): string {
  if (!model) return 'openai:gpt-4o'

  // If already has provider prefix, return as-is
  if (model.includes(':')) return model

  // Add openai prefix for common models
  if (model.startsWith('gpt-') || model.startsWith('o1-')) {
    return `openai:${model}`
  }

  // Default to openai prefix
  return `openai:${model}`
}

/**
 * Filter out input parameters (keep only regular parameters)
 */
export function filterInputParameters<T extends { kind?: 'parameter' | 'input' }>(params: T[] | undefined): T[] {
  if (!params) return []
  return params.filter(param => param.kind !== 'input')
}

/**
 * Extract tool data from backend agent tools
 */
export function extractToolData(tools: BackendAgentTool[]) {
  const toolParameters: Record<string, Record<string, any>> = {}
  const toolInstanceIds: Record<string, string> = {}

  const toolSchemas: Record<
    string,
    {
      name: string
      component_description: string | null
      parameters: BackendAgentParameter[]
      tool_description: any
    }
  > = {}

  if (tools && tools.length > 0) {
    tools.forEach(tool => {
      const componentId = tool.component_id
      const componentVersionId = tool.component_version_id
      const instanceId = tool.id

      if (instanceId) {
        toolInstanceIds[componentId] = instanceId

        const params: Record<string, any> = {}

        if (tool.parameters) {
          // Store full tool info using component_version_id as key
          toolSchemas[componentVersionId] = {
            name: tool.component_name,
            component_description: tool.component_description,
            parameters: tool.parameters,
            tool_description: tool.tool_description,
          }

          tool.parameters.forEach(param => {
            if (param.value !== param.default && param.value !== null && param.value !== undefined) {
              params[param.name] = param.value
            }
          })
        }

        if (Object.keys(params).length > 0) {
          toolParameters[componentVersionId] = params
        }
      }
    })
  }

  return { toolParameters, toolInstanceIds, toolSchemas }
}

/**
 * Find draft graph runner from list
 */
export function findDraftGraphRunner(
  graphRunners?: Array<{ graph_runner_id: string; env: string | null; tag_name: string | null }>
) {
  if (!graphRunners || graphRunners.length === 0) return null
  return graphRunners.find(gr => gr.env === 'draft' && gr.tag_name === null) || graphRunners[0]
}
