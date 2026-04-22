import type { SubcomponentInfo } from '@/components/studio/data/component-definitions'
import type { ComponentCreateV2Data, ComponentV2Response, PortConfiguration } from '@/components/studio/types/graph.types'
import { getComponentDefinitionFromCache } from '@/composables/queries/useComponentDefinitionsQuery'

export type CreateComponentFn = (data: ComponentCreateV2Data) => Promise<ComponentV2Response>

/**
 * Options for creating node data
 */
export interface NodeDataOptions {
  instanceId?: string
  parentId?: string
  parameterName?: string
  isOptional?: boolean
  includeIconIntegration?: boolean
}

/**
 * Options for processing tools recursively
 */
export interface ProcessToolsOptions {
  filterRequired?: boolean
  includeIconIntegration?: boolean
}

/**
 * Helper function to detect if icon is an external provider logo
 */
export function isProviderLogo(icon?: string): boolean {
  return icon?.startsWith('logos') || icon?.startsWith('custom') || false
}

/**
 * Formats component parameters to node parameter format
 */
export function formatNodeParameters(parameters: any[]): any[] {
  return (
    parameters?.map(param => ({
      name: param.name,
      value: param.type === 'boolean' ? (param.default ?? false) : (param.default ?? null),
      type: param.type,
      order: param.order ?? null,
      nullable: param.nullable ?? false,
      default: param.default ?? null,
      ui_component: param.ui_component ?? null,
      ui_component_properties: param.ui_component_properties ?? null,
      is_advanced: param.is_advanced ?? false,
      kind: param.kind ?? 'parameter',
      is_tool_input: param.is_tool_input ?? true,
    })) || []
  )
}

/**
 * Formats tool description with null checks
 */
export function formatToolDescription(toolDescription: any): any {
  if (!toolDescription) return null

  return {
    name: toolDescription.name,
    description: toolDescription.description,
    tool_properties: toolDescription.tool_properties || {},
    required_tool_properties: toolDescription.required_tool_properties || [],
  }
}

function createInitialPortConfigurations(definition: any, componentInstanceId: string): PortConfiguration[] {
  const params = Array.isArray(definition?.parameters) ? definition.parameters : []

  return params
    .filter(
      (p: any) => p?.kind === 'input' && p?.is_tool_input === true && typeof p?.id === 'string' && p.id.length > 0
    )
    .map(
      (p: any): PortConfiguration => ({
        component_instance_id: componentInstanceId,
        parameter_id: p.id,
        input_port_instance_id: null,
        setup_mode: 'ai_filled',
        expression_json: null,
        ai_name_override: null,
        ai_description_override: null,
        is_required_override: null,
        custom_port_name: null,
        custom_port_description: null,
        custom_parameter_type: null,
        custom_ui_component_properties: null,
        json_schema_override: null,
      })
    )
}

/**
 * Creates complete node data structure
 */
export function createNodeData(definition: any, options: NodeDataOptions = {}): any {
  const { instanceId, parentId, parameterName, isOptional = false, includeIconIntegration = false } = options

  const baseData = {
    ref: definition.name,
    name: definition.name,
    component_id: definition.id || definition.component_id,
    component_version_id: definition.component_version_id,
    is_agent: definition.is_agent ?? false,
    is_start_node: false,
    component_name: definition.name,
    component_description: definition.description ?? '',
    parameters: formatNodeParameters(definition.parameters || []),
    tool_description: formatToolDescription(definition.tool_description),
    inputs: definition.inputs || [],
    outputs: definition.outputs || [],
    can_use_function_calling: definition.can_use_function_calling ?? false,
    function_callable: definition.function_callable ?? false,
    tools: definition.tools || [],
    subcomponents_info: definition.subcomponents_info || [],
    ...(instanceId && { port_configurations: createInitialPortConfigurations(definition, instanceId) }),
  }

  // Add parent/optional fields if provided
  if (parentId) {
    Object.assign(baseData, {
      is_required_tool: !isOptional,
      is_optional: isOptional,
      parent_component_id: parentId,
    })
    if (parameterName) {
      Object.assign(baseData, { parameter_name: parameterName })
    }
  }

  // Add icon and integration if requested
  if (includeIconIntegration) {
    Object.assign(baseData, {
      icon: definition.icon,
      integration: definition.integration,
    })
  }

  return baseData
}

/**
 * Build a ComponentCreateV2Data payload from a component definition.
 */
export function buildCreatePayload(definition: any, label: string, isStartNode = false): ComponentCreateV2Data {
  const parameters = formatNodeParameters(definition.parameters || []).map((p: any) => {
    let value = p.value
    if (value === '' || value === 'None') value = null
    return { ...p, value }
  })

  return {
    component_id: definition.id || definition.component_id,
    component_version_id: definition.component_version_id,
    label: label || definition.name || 'Untitled',
    is_start_node: isStartNode,
    parameters,
    input_port_instances: [],
    port_configurations: null,
    integration: definition.integration || null,
    tool_description_override: null,
  }
}

/**
 * Recursively processes tools and their subcomponents.
 * Each tool is created on the backend first via `createComponent`, so all
 * returned node IDs are server-assigned.
 */
export async function processToolsRecursively(
  parentId: string,
  tools: SubcomponentInfo[],
  componentDefinitions: any[],
  createComponent: CreateComponentFn,
  options: ProcessToolsOptions = {},
  processedTools = new Set<string>()
): Promise<{ nodes: any[]; relationships: any[] }> {
  const { filterRequired = false, includeIconIntegration = false } = options
  const allNodes: any[] = []
  const allRelationships: any[] = []

  for (const tool of tools) {
    const dedupKey = `${tool.component_version_id}|${tool.parameter_name}`
    if (processedTools.has(dedupKey)) continue
    processedTools.add(dedupKey)

    const toolDefinition = getComponentDefinitionFromCache(componentDefinitions, tool.component_version_id)
    if (!toolDefinition) continue

    const payload = buildCreatePayload(toolDefinition, toolDefinition.name)
    const response = await createComponent(payload)
    const toolNodeId = response.instance_id

    const toolNode = {
      id: toolNodeId,
      type: 'worker',
      data: createNodeData(toolDefinition, {
        instanceId: toolNodeId,
        parentId,
        parameterName: tool.parameter_name,
        isOptional: tool.is_optional,
        includeIconIntegration,
      }),
      position: { x: 100, y: 200 },
    }

    allRelationships.push({
      parent_component_instance_id: parentId,
      child_component_instance_id: toolNodeId,
      parameter_name: tool.parameter_name,
      order: null,
    })

    allNodes.push(toolNode)

    if (toolDefinition.subcomponents_info && toolDefinition.subcomponents_info.length > 0) {
      const subTools = filterRequired
        ? toolDefinition.subcomponents_info.filter((sub: SubcomponentInfo) => !sub.is_optional)
        : toolDefinition.subcomponents_info

      if (subTools.length > 0) {
        const { nodes: subNodes, relationships: subRelationships } = await processToolsRecursively(
          toolNodeId,
          subTools,
          componentDefinitions,
          createComponent,
          options,
          processedTools
        )

        allNodes.push(...subNodes)
        allRelationships.push(...subRelationships)
      }
    }
  }

  return { nodes: allNodes, relationships: allRelationships }
}
