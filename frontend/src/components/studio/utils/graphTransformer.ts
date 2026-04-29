import { Position } from '@vue-flow/core'
import type { ComponentDefinition } from '../data/component-definitions'
import type { Edge } from '../types/edge.types'
import type {
  ApiComponentInstance,
  ApiEdge,
  ApiRelationship,
  ComponentUpdateV2Data,
  GraphData,
  GraphV2Response,
  TopologyUpdateV2Data,
} from '../types/graph.types'
import type { Node, NodeData, Parameter, ToolDescription } from '../types/node.types'
import { createComponentDefinitionMap } from './componentLookup'
import { isRouterComponent } from './routerDetection'
import { generateRouterOutputs } from './routerTransformer'
import { logger } from '@/utils/logger'

// Type for graphTransformer to avoid circular reference
interface GraphTransformerType {
  toFlow: (apiData: GraphData, componentDefinitions?: ComponentDefinition[]) => { nodes: Node[]; edges: Edge[] }
  prepareTopologyForSaveV2: (nodes: Node[], edges: Edge[]) => TopologyUpdateV2Data
  extractComponentUpdateV2: (node: Node) => ComponentUpdateV2Data
  mergeV2Topology: (
    existingNodes: Node[],
    existingEdges: Edge[],
    v2Response: GraphV2Response
  ) => { nodes: Node[]; edges: Edge[]; unknownNodeIds: string[] }
  transformSingleInstanceData: (
    instance: ApiComponentInstance,
    componentDefinitions?: ComponentDefinition[]
  ) => Record<string, any>
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

  /**
   * Prepare topology-only payload for V2 PUT /map.
   * Converts VueFlow nodes/edges into the V2 topology format
   * ({nodes, edges with from/to refs, relationships with parent/child refs}).
   */
  prepareTopologyForSaveV2(nodes: Node[], edges: Edge[]): TopologyUpdateV2Data {
    const targetNodeIdsWithLeftConnection = new Set(
      edges.filter(edge => edge.targetHandle === 'left').map(edge => edge.target)
    )

    const topologyNodes = nodes.map(node => {
      const isStartNode =
        node.type === 'component' ? !targetNodeIdsWithLeftConnection.has(node.id) : (node.data?.is_start_node ?? false)
      return {
        instance_id: node.id,
        label: node.data?.name || node.data?.label || null,
        is_start_node: isStartNode,
      }
    })

    const topologyEdges = edges
      .filter(
        edge =>
          (edge.sourceHandle === 'right' && edge.targetHandle === 'left') ||
          (/^\d+$/.test(edge.sourceHandle || '') && edge.targetHandle === 'left')
      )
      .map(edge => {
        let edgeOrder = edge.order ?? null
        if (edgeOrder === null && /^\d+$/.test(edge.sourceHandle || '')) {
          edgeOrder = parseInt(edge.sourceHandle!, 10)
        }
        return {
          id: edge.id,
          from: { id: edge.source },
          to: { id: edge.target },
          order: edgeOrder,
        }
      })

    const relationshipEdges = edges.filter(
      edge => edge.sourceHandle === 'bottom' && edge.targetHandle === 'top'
    )

    const parentChildMap = new Map<string, Edge[]>()
    relationshipEdges.forEach(edge => {
      const children = parentChildMap.get(edge.source) || []
      children.push(edge)
      parentChildMap.set(edge.source, children)
    })

    const topologyRelationships = relationshipEdges.map(edge => {
      const parentNode = nodes.find(n => n.id === edge.source)
      const childNode = nodes.find(n => n.id === edge.target)
      const staticSubcomponentDefIds = new Set(
        (parentNode?.data?.subcomponents_info || []).map((sub: any) => sub.component_version_id)
      )
      const childComponentDefId = childNode?.data?.component_version_id
      const isStaticSubcomponent = childComponentDefId && staticSubcomponentDefIds.has(childComponentDefId)

      let order: number | null = null
      if (!isStaticSubcomponent) {
        const siblings = parentChildMap.get(edge.source) || []
        const toolSiblings = siblings.filter(e => {
          const cn = nodes.find(n => n.id === e.target)
          return !(cn?.data?.component_version_id && staticSubcomponentDefIds.has(cn.data.component_version_id))
        })
        toolSiblings.sort((a, b) => {
          const yA = nodes.find(n => n.id === a.target)?.position?.y ?? 0
          const yB = nodes.find(n => n.id === b.target)?.position?.y ?? 0
          return yA - yB
        })
        order = toolSiblings.findIndex(e => e.id === edge.id)
        if (order === -1) order = null
      }

      return {
        parent: { id: edge.source },
        child: { id: edge.target },
        parameter_name: edge.parameter_name || edge.data?.parameter_name || 'agent_tools',
        order,
      }
    })

    return {
      nodes: topologyNodes,
      edges: topologyEdges,
      relationships: topologyRelationships,
    }
  },

  /**
   * Extract V2 component update payload from a VueFlow node.
   * Used for PUT /v2/.../components/{instance_id}.
   */
  extractComponentUpdateV2(node: Node): ComponentUpdateV2Data {
    const nodeData = (node.data || {}) as any

    const handledFieldExprNames = new Set<string>()

    const parameters = (nodeData.parameters || []).map((param: any) => {
      let value = param.value
      if (value === '' || value === 'None') value = null

      if ((param.kind ?? 'parameter') === 'input') {
        handledFieldExprNames.add(param.name)
      }

      return {
        name: param.name,
        value,
        order: param.display_order ?? null,
        type: param.type ?? typeof param.value,
        nullable: param.nullable ?? false,
        default: param.default,
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

    if (nodeData.field_expressions && Array.isArray(nodeData.field_expressions)) {
      for (const fe of nodeData.field_expressions) {
        if (handledFieldExprNames.has(fe.field_name)) continue
        const exprJson = fe.expression_json ?? fe.expression_text
        if (exprJson) {
          parameters.push({
            name: fe.field_name,
            value: exprJson,
            order: null,
            type: 'string',
            nullable: true,
            default: null,
            ui_component: null,
            ui_component_properties: null,
            is_advanced: false,
            parameter_group_id: null,
            parameter_order_within_group: null,
            parameter_group_name: null,
            kind: 'input',
            is_tool_input: true,
          })
        }
      }
    }

    const toolDescription = nodeData.tool_description
      ? nodeData.tool_description.description || null
      : null

    return {
      parameters,
      input_port_instances: [],
      port_configurations: nodeData.port_configurations || null,
      integration: nodeData.integration || null,
      tool_description_override: toolDescription,
      label: nodeData.name || null,
    }
  },

  /**
   * Merge a V2 topology response into existing VueFlow nodes/edges.
   * Preserves full component data (parameters, field expressions, etc.)
   * while updating topology (edges, relationships, node metadata).
   */
  mergeV2Topology(
    existingNodes: Node[],
    existingEdges: Edge[],
    v2Response: GraphV2Response
  ): { nodes: Node[]; edges: Edge[]; unknownNodeIds: string[] } {
    const { graph_map } = v2Response
    const existingNodeMap = new Map(existingNodes.map(n => [n.id, n]))

    const unknownNodeIds: string[] = []
    const mergedNodes: Node[] = []

    for (const v2Node of graph_map.nodes) {
      const nodeId = v2Node.instance_id!
      const existing = existingNodeMap.get(nodeId)
      if (existing) {
        mergedNodes.push({
          ...existing,
          data: {
            ...existing.data,
            name: v2Node.label ?? existing.data?.name,
            is_start_node: v2Node.is_start_node ?? existing.data?.is_start_node,
          },
        })
      } else {
        unknownNodeIds.push(nodeId)
        logger.warn(`[mergeV2Topology] Node ${nodeId} not found in existing nodes — full graph reload required`)
      }
    }

    const v2NodeIds = new Set(graph_map.nodes.map(n => n.instance_id))

    const componentEdges: Edge[] = (graph_map.edges || []).map(v2Edge => {
      const sourceId = v2Edge.from?.id || ''
      const targetId = v2Edge.to?.id || ''
      const sourceNode = mergedNodes.find(n => n.id === sourceId)
      let sourceHandle = 'right'
      if (sourceNode?.type === 'router' && v2Edge.order !== null && v2Edge.order !== undefined) {
        sourceHandle = String(v2Edge.order)
      }
      return {
        id: v2Edge.id || `e-${sourceId}-${targetId}`,
        source: sourceId,
        target: targetId,
        type: 'smoothstep',
        animated: true,
        hidden: false,
        sourcePosition: Position.Right,
        targetPosition: Position.Left,
        sourceHandle,
        targetHandle: 'left',
        selectable: true,
        deletable: true,
        order: v2Edge.order ?? null,
      }
    })

    const relationshipEdges: Edge[] = (graph_map.relationships || []).map(v2Rel => {
      const parentId = v2Rel.parent?.id || ''
      const childId = v2Rel.child?.id || ''
      return {
        id: `r-${parentId}-${childId}`,
        source: parentId,
        target: childId,
        type: 'smoothstep',
        animated: true,
        hidden: false,
        sourcePosition: Position.Bottom,
        targetPosition: Position.Top,
        sourceHandle: 'bottom',
        targetHandle: 'top',
        selectable: true,
        deletable: true,
        order: v2Rel.order ?? null,
        parameter_name: v2Rel.parameter_name,
        data: { parameter_name: v2Rel.parameter_name },
      }
    })

    const relationshipChildIds = new Set((graph_map.relationships || []).map(r => r.child?.id).filter(Boolean))

    const childToRelationship = new Map(
      (graph_map.relationships || []).filter(r => r.child?.id).map(r => [r.child!.id!, r] as const)
    )

    for (const node of mergedNodes) {
      if (relationshipChildIds.has(node.id)) {
        if (node.type !== 'worker') {
          node.type = 'worker'
        }
        const v2Rel = childToRelationship.get(node.id)!

        node.data.parent_component_id = v2Rel.parent?.id || null
        node.data.parameter_name = v2Rel.parameter_name
        node.data.is_optional = true
        node.data.is_required_tool = false
      } else if (node.data) {
        node.type = isRouterComponent(node.data) ? 'router' : 'component'
        node.data.parent_component_id = null
        node.data.parameter_name = undefined
        node.data.is_optional = false
        node.data.is_required_tool = false
      }
    }

    return {
      nodes: mergedNodes.filter(n => v2NodeIds.has(n.id)),
      edges: [...componentEdges, ...relationshipEdges],
      unknownNodeIds,
    }
  },

  transformSingleInstanceData(
    instance: ApiComponentInstance,
    componentDefinitions?: ComponentDefinition[]
  ): Record<string, any> {
    const componentDefMap = createComponentDefinitionMap(componentDefinitions)
    const instanceAny = instance as any

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

    const componentDef =
      componentDefMap.get(component_version_id) || componentDefMap.get(component_id) || componentDefMap.get(id)

    const formattedParameters: Parameter[] = parameters.map(param => {
      let finalValue = param.value

      if (finalValue === '[JSON_BUILD]' && Array.isArray(instanceAny.field_expressions)) {
        const fieldExpr = instanceAny.field_expressions.find((expr: any) => expr.field_name === param.name)
        if (fieldExpr?.expression_json) {
          finalValue = fieldExpr.expression_json
        }
      }

      if (finalValue === null && param.nullable === false && param.default != null) finalValue = param.default
      else if (param.type === 'boolean' && finalValue == null) finalValue = param.default ?? false

      let groupId = (param as any).parameter_group_id ?? null
      let groupOrder = (param as any).parameter_order_within_group ?? null
      let groupName = (param as any).parameter_group_name ?? null
      let displayOrder = (param as any).display_order ?? (param as any).order ?? null

      if ((!groupId || displayOrder == null) && componentDef?.parameters) {
        const defParam = componentDef.parameters.find((p: any) => p.name === param.name)
        if (defParam) {
          if (!groupId) {
            groupId = defParam.parameter_group_id ?? null
            groupOrder = defParam.parameter_order_within_group ?? null
            groupName = defParam.parameter_group_name ?? null
          }
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

    const formattedToolDescription: ToolDescription | null = tool_description
      ? {
          name: tool_description.name,
          description: tool_description.description,
          tool_properties: tool_description.tool_properties || {},
          required_tool_properties: tool_description.required_tool_properties || [],
        }
      : null

    const isRouter = isRouterComponent(instance)
    let finalOutputs = outputs
    if (isRouter) {
      const { outputs: routerOutputs, routesCount } = generateRouterOutputs(formattedParameters, outputs)
      if (routesCount > 0) {
        finalOutputs = routerOutputs
      }
    }

    return {
      id,
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
      component_name: instanceAny.component_name || name,
      component_description: instanceAny.component_description || '',
      is_start_node: instanceAny.is_start_node ?? false,
      subcomponents_info: instanceAny.subcomponents_info || [],
      icon: instanceAny.icon || null,
      ...(instanceAny.integration && { integration: instanceAny.integration }),
      ...(instanceAny.field_expressions && { field_expressions: instanceAny.field_expressions }),
      ...(instanceAny.port_configurations && { port_configurations: instanceAny.port_configurations }),
    }
  },
}
