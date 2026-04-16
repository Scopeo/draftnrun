import { v4 as uuidv4 } from 'uuid'
import type { SubcomponentInfo } from '@/components/studio/data/component-definitions'
import type { PortConfiguration } from '@/components/studio/types/graph.types'
import { getComponentDefinitionFromCache } from '@/composables/queries/useComponentDefinitionsQuery'

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
 * Recursively processes tools and their subcomponents
 * Creates nodes and relationships for all tools in the hierarchy
 *
 * @param parentId - ID of the parent component
 * @param tools - Array of tools/subcomponents to process
 * @param options - Processing options
 * @returns Object containing arrays of nodes and relationships
 */
export async function processToolsRecursively(
  parentId: string,
  tools: SubcomponentInfo[],
  componentDefinitions: any[],
  options: ProcessToolsOptions = {},
  processedTools = new Set<string>()
): Promise<{ nodes: any[]; relationships: any[] }> {
  const { filterRequired = false, includeIconIntegration = false } = options
  const allNodes: any[] = []
  const allRelationships: any[] = []

  for (const tool of tools) {
    // Skip if we've already processed this tool (prevent circular dependencies)
    if (processedTools.has(tool.component_version_id)) continue
    processedTools.add(tool.component_version_id)

    // Get the tool definition
    const toolDefinition = getComponentDefinitionFromCache(componentDefinitions, tool.component_version_id)
    if (!toolDefinition) continue

    // Create tool node
    const toolNodeId = uuidv4()

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

    // Add relationship with parameter_name
    allRelationships.push({
      parent_component_instance_id: parentId,
      child_component_instance_id: toolNode.id,
      parameter_name: tool.parameter_name,
      order: null,
    })

    allNodes.push(toolNode)

    // Recursively process this tool's subcomponents if any
    if (toolDefinition.subcomponents_info && toolDefinition.subcomponents_info.length > 0) {
      // Filter for required tools only if requested
      const subTools = filterRequired
        ? toolDefinition.subcomponents_info.filter((sub: SubcomponentInfo) => !sub.is_optional)
        : toolDefinition.subcomponents_info

      if (subTools.length > 0) {
        const { nodes: subNodes, relationships: subRelationships } = await processToolsRecursively(
          toolNode.id,
          subTools,
          componentDefinitions,
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
