import { Position } from '@vue-flow/core'
import type { ComponentDefinition, Integration } from '../data/component-definitions'
import type { Edge } from '../types/edge.types'
import type { ApiComponentInstance, ApiEdge, ApiRelationship, GraphData } from '../types/graph.types'
import type { Node, NodeData, Parameter, ToolDescription } from '../types/node.types'
import { createComponentDefinitionMap } from './componentLookup'
import { isRouterComponent } from './routerDetection'
import { generateRouterOutputs } from './routerTransformer'
import { logger } from '@/utils/logger'

// Update Edge data interface to include order property
interface EnhancedEdgeData {
  parameter?: string
  order?: number
}

// Extended node data interface
interface EnhancedNodeData extends NodeData {
  positionedByUser?: boolean
  can_use_function_calling?: boolean
  function_callable?: boolean
  tools?: any[]
  component_name?: string
  component_description?: string
  is_start_node?: boolean
  subcomponents_info?: any[]
  tool_parameter_name?: string | null
  integration?: Integration
}

// Type for graphTransformer to avoid circular reference
interface GraphTransformerType {
  toFlow: (apiData: GraphData, componentDefinitions?: ComponentDefinition[]) => { nodes: Node[]; edges: Edge[] }
  fromFlow: (flowData: { nodes: Node[]; edges: Edge[] }) => {
    component_instances: ApiComponentInstance[]
    relationships: ApiRelationship[]
    edges: ApiEdge[]
  }
  prepareGraphDataForSave: (
    nodes: Node[],
    edges: Edge[]
  ) => {
    component_instances: ApiComponentInstance[]
    relationships: ApiRelationship[]
    edges: ApiEdge[]
  }
}

export const graphTransformer: GraphTransformerType = {
  // Convert API data to VueFlow format
  toFlow(apiData: GraphData, componentDefinitions?: ComponentDefinition[]) {
    logger.info('Transforming API data', { data: apiData })

    if (!apiData.component_instances) {
      logger.error('No component instances in API data')

      return { nodes: [], edges: [] }
    }

    const componentDefMap = createComponentDefinitionMap(componentDefinitions)

    // Create a map of parent components and their STATIC subcomponents_info
    const componentSubcomponentsMap = new Map<string, any[]>(
      apiData.component_instances
        .filter(instance => instance.subcomponents_info && instance.subcomponents_info.length > 0)
        .map(instance => [instance.id, instance.subcomponents_info || []])
    )

    // --- NEW: Create a set of all nodes that are children in relationships ---
    const relationshipChildIds = new Set<string>(
      (apiData.relationships || []).map(rel => rel.child_component_instance_id)
    )

    // Transform nodes
    const nodes: Node[] = apiData.component_instances.map((instance: ApiComponentInstance) => {
      let parentInfo = null
      let isStaticSubcomponent = false // Flag if found in subcomponents_info

      // Check static subcomponents_info first
      for (const [parentId, subcomponents] of componentSubcomponentsMap) {
        // Find subcomponent by definition ID (component_version_id)
        const subcompInfo = subcomponents?.find(sub => sub.component_version_id === instance.component_version_id)
        if (subcompInfo) {
          parentInfo = {
            parent_id: parentId, // This is the instance ID of the parent
            is_optional: subcompInfo.is_optional,
            parameter_name: subcompInfo.parameter_name,
          }
          isStaticSubcomponent = true
          break // Found in static definition
        }
      }

      // Determine node type
      const isRelationshipChild = relationshipChildIds.has(instance.id)

      // Check if this is a Router component using centralized detection
      const isRouter = isRouterComponent(instance)

      let nodeType: string
      if (isStaticSubcomponent || isRelationshipChild) {
        nodeType = 'worker'
      } else if (isRouter) {
        nodeType = 'router'
      } else {
        nodeType = 'component'
      }

      if (isRelationshipChild && !isStaticSubcomponent)
        logger.info(`Node ${instance.id} (${instance.name}) identified as dynamic worker via relationship.`)

      // Extract instance properties safely
      const {
        id,
        ref,
        name,
        component_id,
        component_version_id,
        parameters = [],
        tool_description,
        inputs = [],
        outputs = [],
        tools = [],
      } = instance

      // Handle potential additional properties that might be in the instance
      // but not in the ApiComponentInstance interface
      const instanceAny = instance as any

      // Get component definition to enrich parameters with group info
      const componentDef =
        componentDefMap.get(component_version_id) || componentDefMap.get(component_id) || componentDefMap.get(id)

      // Format parameters to match Parameter interface
      const formattedParameters: Parameter[] = parameters.map(param => {
        let finalValue = param.value

        // TODO: [Backend Migration] This [JSON_BUILD] marker handling should be moved to backend.
        // Waiting for component instance API to include a boolean flag or options to indicate
        // when field_expressions should be auto-resolved. Currently frontend manually looks up
        // field_expressions, but backend should handle this transformation.
        // Handle [JSON_BUILD] marker - look up actual value from field_expressions
        if (finalValue === '[JSON_BUILD]' && Array.isArray((instance as any).field_expressions)) {
          const fieldExpr = (instance as any).field_expressions.find((expr: any) => expr.field_name === param.name)
          if (fieldExpr?.expression_json) {
            finalValue = fieldExpr.expression_json
          }
        }

        // If value is null and parameter is not nullable, use default value
        if (finalValue === null && param.nullable === false && param.default != null) finalValue = param.default
        // For boolean type, ensure we never have null
        else if (param.type === 'boolean' && finalValue == null) finalValue = param.default ?? false

        // Try to get group info from API response first, then from component definition
        let groupId = (param as any).parameter_group_id ?? null
        let groupOrder = (param as any).parameter_order_within_group ?? null
        let groupName = (param as any).parameter_group_name ?? null
        let displayOrder = (param as any).display_order ?? (param as any).order ?? null

        // If not in API response, try to get from component definition
        if ((!groupId || displayOrder == null) && componentDef?.parameters) {
          const defParam = componentDef.parameters.find((p: any) => p.name === param.name)
          if (defParam) {
            if (!groupId) {
              groupId = defParam.parameter_group_id ?? null
              groupOrder = defParam.parameter_order_within_group ?? null
              groupName = defParam.parameter_group_name ?? null
            }
            // Enrich order from component definition if missing
            if (displayOrder == null && defParam.order != null) {
              displayOrder = defParam.order
            }
          }
        }

        return {
          name: param.name,
          value: finalValue,
          display_order: displayOrder,
          type: param.type ?? typeof param.value,
          nullable: param.nullable ?? false,
          default: param.type === 'boolean' ? (param.default ?? false) : (param.default ?? null),
          ui_component: param.ui_component ?? null,
          ui_component_properties: param.ui_component_properties ?? null,
          is_advanced: param.is_advanced ?? false,
          parameter_group_id: groupId,
          parameter_order_within_group: groupOrder,
          parameter_group_name: groupName,
          kind: (param.kind ?? 'parameter') as 'parameter' | 'input',
          is_tool_input: param.is_tool_input ?? true,
        }
      })

      // Format tool_description to match ToolDescription interface
      // Note: tool_properties and required_tool_properties are generated by backend from port_configurations
      const formattedToolDescription: ToolDescription | null = tool_description
        ? {
            name: tool_description.name,
            description: tool_description.description,
            tool_properties: tool_description.tool_properties || {}, // Read-only from backend
            required_tool_properties: tool_description.required_tool_properties || [], // Read-only from backend
          }
        : null

      // Find the relationship where this node is the child to get the correct parameter_name for dynamically added tools
      let dynamicParameterName: string | undefined
      if (isRelationshipChild && !isStaticSubcomponent) {
        const relationship = (apiData.relationships || []).find(rel => rel.child_component_instance_id === instance.id)

        dynamicParameterName = relationship?.parameter_name
      }

      // WORKAROUND: Dynamically generate outputs for Router components if missing
      // The backend doesn't persist/return the outputs field, so we regenerate it from routes
      let finalOutputs = outputs
      if (isRouter) {
        const { outputs: routerOutputs, routesCount } = generateRouterOutputs(formattedParameters, outputs)
        if (routesCount > 0) {
          finalOutputs = routerOutputs
        }
      }

      return {
        id,
        type: nodeType, // Use the correctly determined type
        data: {
          id, // Include id in data for field expressions
          ref,
          name: name || ref,
          component_id,
          component_version_id,
          is_agent: instanceAny.is_agent ?? false,
          parameters: formattedParameters,
          tool_description: formattedToolDescription,
          inputs,
          outputs: finalOutputs,
          can_use_function_calling: instanceAny.can_use_function_calling ?? false,
          function_callable: instanceAny.function_callable ?? false,
          tool_parameter_name: instanceAny.tool_parameter_name ?? null,
          tools,
          component_name: instanceAny.component_name || name, // Fallback to name
          component_description: instanceAny.component_description || '',
          is_start_node: instanceAny.is_start_node ?? false, // Default to false
          subcomponents_info: instanceAny.subcomponents_info || [], // Default to empty array
          parent_info: parentInfo, // Info if it's a STATIC subcomponent
          icon: instanceAny.icon || null,

          // Determine if required based on static info (dynamic tools are treated as optional)
          is_required_tool: parentInfo ? !parentInfo.is_optional : false,
          is_optional: parentInfo ? parentInfo.is_optional : isRelationshipChild, // Static optionality or true if dynamic child
          // Use parameter_name from static info OR from dynamic relationship
          parameter_name: parentInfo?.parameter_name ?? dynamicParameterName,
          positionedByUser: !!instanceAny.position,

          // Include integration data if it exists
          ...(instanceAny.integration && { integration: instanceAny.integration }),
          // Include field_expressions if they exist
          ...(instanceAny.field_expressions && { field_expressions: instanceAny.field_expressions }),
          // Include port_configurations if they exist
          ...(instanceAny.port_configurations && { port_configurations: instanceAny.port_configurations }),
        },
        position: instanceAny.position || { x: 0, y: 0 },
        hidden: false,
        selected: false,
        dragging: false,
        selectable: true,
        connectable: true,

        // Deletable based on static info or if it's a dynamic child (assume deletable)
        deletable: !parentInfo || parentInfo.is_optional || isRelationshipChild,
      }
    })

    // Create node map for quick lookup
    const nodeMap = new Map(nodes.map(node => [node.id, node]))

    // Transform edges (Component-to-Component)
    const componentEdges: Edge[] = (apiData.edges || [])
      .filter(edge => {
        // Filter out invalid edges
        if (!edge.origin || !edge.destination) {
          logger.warn('[graphTransformer] ⚠️ Skipping invalid edge', { data: edge })
          return false
        }
        return true
      })
      .map((edge: ApiEdge) => {
        // For router edges, derive sourceHandle from order
        let sourceHandle = 'right'

        const sourceNode = nodeMap.get(edge.origin)
        if (sourceNode?.type === 'router' && edge.order !== null && edge.order !== undefined) {
          sourceHandle = String(edge.order)
        }

        return {
          id: edge.id,
          source: edge.origin,
          target: edge.destination,
          type: 'smoothstep',
          animated: true,
          hidden: false,
          sourcePosition: Position.Right,
          targetPosition: Position.Left,
          sourceHandle,
          targetHandle: 'left',
          selectable: true,
          deletable: true,
          order: edge.order ?? null,
          parameter_name: (edge as any).parameter_name,
          data: { parameter_name: (edge as any).parameter_name },
        }
      })

    // Transform relationships (Parent-to-Child Tool)
    const relationshipEdges: Edge[] = (apiData.relationships || []).map((rel: ApiRelationship) => ({
      // Ensure generated ID is unique enough or use rel.id if provided by backend
      id: `r-${rel.parent_component_instance_id}-${rel.child_component_instance_id}`,
      source: rel.parent_component_instance_id,
      target: rel.child_component_instance_id,
      type: 'smoothstep',
      animated: true,
      hidden: false,
      sourcePosition: Position.Bottom,
      targetPosition: Position.Top,
      sourceHandle: 'bottom',
      targetHandle: 'top',
      selectable: true,
      deletable: true, // Relationships representing tools should be deletable
      order: rel.order ?? null, // Use order from API
      parameter_name: rel.parameter_name,
      data: { parameter_name: rel.parameter_name },
    }))

    const edges = [...componentEdges, ...relationshipEdges]

    logger.info('Transformed data', { nodes, edges })

    return { nodes, edges }
  },

  // Convert VueFlow format back to API format
  fromFlow(flowData: { nodes: Node[]; edges: Edge[]; playgroundConfig?: any }) {
    // Ensure nodes passed to this function have valid positions
    const nodesWithPosition = flowData.nodes.map(node => ({
      ...node,
      position: node.position ?? { x: 0, y: 0 }, // Ensure position exists TODO: Check if this is not preventing edges cases
    }))

    // Calculate is_start_node: a component is a start node if it has no incoming left-handle connections
    const targetNodeIdsWithLeftConnection = new Set(
      flowData.edges.filter(edge => edge.targetHandle === 'left').map(edge => edge.target)
    )

    // --- Calculate relationship order ---
    const relationshipEdges = flowData.edges.filter(
      edge => edge.sourceHandle === 'bottom' && edge.targetHandle === 'top'
    )

    const parentChildMap = new Map<string, Edge[]>()

    // Group children by parent
    relationshipEdges.forEach(edge => {
      const children = parentChildMap.get(edge.source) || []

      children.push(edge)
      parentChildMap.set(edge.source, children)
    })

    // Assign order within each parent group
    const edgeOrderMap = new Map<string, number | null>()

    parentChildMap.forEach((childEdges, parentId) => {
      // Get parent node to check its static subcomponents definition
      const parentNode = flowData.nodes.find(n => n.id === parentId)

      // Assuming subcomponents_info holds definition IDs of static subcomponents
      const staticSubcomponentDefIds = new Set(
        (parentNode?.data?.subcomponents_info || []).map(sub => sub.component_version_id)
      )

      const toolEdges: Edge[] = [] // Collect edges representing tools

      childEdges.forEach(edge => {
        // Find the child node instance

        const childNode = flowData.nodes.find(n => n.id === edge.target)
        const childComponentDefId = childNode?.data?.component_version_id

        // Check if the child's component definition ID is in the parent's static list
        if (childComponentDefId && staticSubcomponentDefIds.has(childComponentDefId)) {
          // It's a static subcomponent, order should be null
          edgeOrderMap.set(edge.id, null)
        } else {
          // It's not found in the static list, treat as a tool
          toolEdges.push(edge)
        }
      })

      // Sort and assign numerical order only to the identified tool edges
      toolEdges.sort((a, b) => {
        const nodeA = flowData.nodes.find(n => n.id === a.target)
        const nodeB = flowData.nodes.find(n => n.id === b.target)
        const yA = nodeA?.position?.y ?? 0
        const yB = nodeB?.position?.y ?? 0

        return yA - yB
      })

      toolEdges.forEach((edge, index) => {
        // Assign 0, 1, 2... order to tools
        edgeOrderMap.set(edge.id, index)
      })
    })

    // --- End Calculate relationship order ---

    const result: any = {
      component_instances: nodesWithPosition.map(node => {
        const nodeData = (node.data || {}) as EnhancedNodeData

        // Create a clean copy of the tool_description to avoid issues with proxies
        // Note: tool_properties and required_tool_properties are generated by backend from port_configurations
        // Do NOT send these fields - backend generates them automatically
        const toolDescription = nodeData.tool_description
          ? {
              name: nodeData.tool_description.name || '',
              description: nodeData.tool_description.description || '',
            }
          : undefined

        // Map parameters carefully, ensuring properties exist
        const parameters = (nodeData.parameters || []).map((param: Parameter) => {
          // Convert empty strings and "None" to null when sending to backend
          let value = param.value
          if (value === '' || value === 'None') value = null

          return {
            name: param.name,
            value,
            order: param.display_order ?? null,
            type: param.type ?? typeof param.value, // Use type from param or infer
            nullable: param.nullable ?? false,
            default: param.default, // Include default if needed by backend
            ui_component: param.ui_component ?? null,
            ui_component_properties: param.ui_component_properties ?? null,
            is_advanced: param.is_advanced ?? false,
            parameter_group_id: param.parameter_group_id ?? null,
            parameter_order_within_group: param.parameter_order_within_group ?? null,
            parameter_group_name: param.parameter_group_name ?? null,
            kind: param.kind ?? 'parameter',
            is_tool_input: param.is_tool_input ?? true,
          }
        })

        // Calculate is_start_node: component nodes without incoming left-handle connections are start nodes
        const isStartNode =
          node.type === 'component' ? !targetNodeIdsWithLeftConnection.has(node.id) : (nodeData.is_start_node ?? false)

        return {
          id: node.id,
          ref: nodeData.ref || '', // Provide default empty string
          name: nodeData.name || '', // Provide default empty string
          component_id: nodeData.component_id,
          component_version_id: nodeData.component_version_id, // Include component_version_id from node data
          is_agent: nodeData.is_agent ?? false,
          is_start_node: isStartNode,
          component_name: nodeData.component_name || nodeData.name,
          component_description: nodeData.component_description || '',
          can_use_function_calling: nodeData.can_use_function_calling ?? false,
          function_callable: nodeData.function_callable ?? false,
          tool_parameter_name: nodeData.tool_parameter_name ?? null, // Include this
          tools: nodeData.tools || [],
          icon: nodeData.icon || null,
          subcomponents_info: nodeData.subcomponents_info || [],
          parameters, // Use mapped parameters
          tool_description: toolDescription,
          ...(nodeData.integration && { integration: nodeData.integration }),
          // Include field_expressions only if they exist AND are not empty
          ...((nodeData as any).field_expressions &&
            Array.isArray((nodeData as any).field_expressions) &&
            (nodeData as any).field_expressions.length > 0 && {
              field_expressions: (nodeData as any).field_expressions,
            }),
          // Include port_configurations only if they exist AND are not empty
          ...((nodeData as any).port_configurations &&
            Array.isArray((nodeData as any).port_configurations) &&
            (nodeData as any).port_configurations.length > 0 && {
              port_configurations: (nodeData as any).port_configurations,
            }),
          // Only include position if it was originally set by the user
          position: nodeData.positionedByUser ? node.position : null,
        }
      }),
      relationships: relationshipEdges // Use the original filtered list for mapping
        .map(edge => ({
          parent_component_instance_id: edge.source,
          child_component_instance_id: edge.target,
          parameter_name: edge.parameter_name || edge.data?.parameter_name, // Check both places
          // Get the calculated order (null for subcomponents, 0+ for tools)
          order: edgeOrderMap.get(edge.id) ?? null,
        })),
      edges: flowData.edges
        .filter(
          edge =>
            // Include regular component-to-component edges
            (edge.sourceHandle === 'right' && edge.targetHandle === 'left') ||
            // Include router output edges (numeric handles: 0, 1, 2, etc.)
            (/^\d+$/.test(edge.sourceHandle || '') && edge.targetHandle === 'left')
        )
        .map(edge => {
          // Calculate order from sourceHandle for router edges if not already set
          let edgeOrder = edge.order ?? null
          if (edgeOrder === null && /^\d+$/.test(edge.sourceHandle || '')) {
            edgeOrder = parseInt(edge.sourceHandle!, 10)
          }

          return {
            id: edge.id,
            origin: edge.source,
            destination: edge.target,
            parameter_name: edge.parameter_name || edge.data?.parameter_name,
            order: edgeOrder,
          }
        }),
    }

    if (flowData.playgroundConfig?.playground_input_schema) {
      result.playground_input_schema = flowData.playgroundConfig.playground_input_schema
    }
    if (flowData.playgroundConfig?.playground_field_types) {
      result.playground_field_types = flowData.playgroundConfig.playground_field_types
    }

    return result
  },

  /**
   * Prepare graph data for saving — delegates transformation to fromFlow()
   */
  prepareGraphDataForSave(
    nodes: Node[],
    edges: Edge[]
  ): {
    component_instances: ApiComponentInstance[]
    relationships: ApiRelationship[]
    edges: ApiEdge[]
  } {
    return graphTransformer.fromFlow({ nodes, edges })
  },
}
