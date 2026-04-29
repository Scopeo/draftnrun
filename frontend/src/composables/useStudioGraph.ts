import { useQueryClient } from '@tanstack/vue-query'
import {
  type GraphEdge,
  type GraphNode,
  Position,
  type Edge as VueFlowEdge,
  applyNodeChanges,
  useVueFlow,
} from '@vue-flow/core'
import { v4 as uuidv4 } from 'uuid'
import { type Ref, computed, ref, watch } from 'vue'
import { calculateLayout, positionNewNode } from '@/components/studio/layoutUtils'
import type { SubcomponentInfo } from '@/components/studio/data/component-definitions'
import type { Edge as StudioEdge } from '@/components/studio/types/edge.types'
import type { Parameter } from '@/components/studio/types/node.types'
import { isValidRouterConnection } from '@/components/studio/utils/connectionValidation'
import { graphTransformer } from '@/components/studio/utils/graphTransformer'
import { buildCreatePayload, createNodeData, processToolsRecursively } from '@/components/studio/utils/node-factory.utils'
import { isRouterComponent } from '@/components/studio/utils/routerDetection'
import { useNotifications } from '@/composables/useNotifications'
import { logger } from '@/utils/logger'
import { scopeoApi } from '@/api'
import { parseRoutes } from '@/utils/routeHelpers'
import {
  useCreateComponentV2Mutation,
  useDeleteComponentV2Mutation,
  useFetchComponentV2,
  useFetchGraphV2,
  useUpdateComponentV2Mutation,
  useUpdateGraphTopologyV2Mutation,
} from '@/composables/queries/useStudioQuery'
import type { GraphRunner } from '@/composables/queries/useProjectsQuery'
import type { ComponentCreateV2Data, GraphV2Response } from '@/components/studio/types/graph.types'

type Edge = VueFlowEdge & { data?: any } & Record<string, any>

export interface UseStudioGraphOptions {
  projectId: Ref<string>
  selectedOrgId: Ref<string | null | undefined>
  componentDefinitions: Ref<any[] | undefined>
  currentGraphRunner: Ref<GraphRunner | null>
  currentProject: Ref<any>
  setCurrentGraphRunner: (runner: GraphRunner) => void
  setGraphLastEditedInfo: (time: string | null, userId: string | null, orgId?: string) => void
  setPlaygroundConfig: (config: any) => void
  refreshProjectData: () => Promise<any>
  selectedNode: Ref<any>
}

export function useStudioGraph(options: UseStudioGraphOptions) {
  const {
    projectId,
    selectedOrgId,
    componentDefinitions,
    currentGraphRunner,
    currentProject,
    setCurrentGraphRunner,
    setGraphLastEditedInfo,
    setPlaygroundConfig,
    refreshProjectData,
    selectedNode,
  } = options

  const queryClient = useQueryClient()
  const updateTopologyV2Mutation = useUpdateGraphTopologyV2Mutation()
  const { fetchGraphV2 } = useFetchGraphV2()
  const { fetchComponentV2 } = useFetchComponentV2()
  const createComponentV2Mutation = useCreateComponentV2Mutation()
  const updateComponentV2Mutation = useUpdateComponentV2Mutation()
  const deleteComponentV2Mutation = useDeleteComponentV2Mutation()
  const { notify } = useNotifications()

  // ─── State ─────────────────────────────────────────────────────────
  const activeComponentId = ref<string | null>(null)
  const hasUnsavedChanges = ref(false)
  const isDeploying = ref(false)
  const saveError = ref<string | null>(null)
  const validationStatus = ref<'valid' | 'invalid' | 'saving' | 'just_saved'>('valid')
  const isSaving = ref(false)
  const showAllNodes = ref(false)
  const isLoadingGraph = ref(false)
  const isTransformingGraph = ref(false)
  let pendingTopologyRefreshPid: string | null = null

  // ─── VueFlow ───────────────────────────────────────────────────────
  function checkConnectionValidity(connection: any): boolean {
    const sourceNode = nodes.value.find(node => node.id === connection.source)
    const targetNode = nodes.value.find(node => node.id === connection.target)
    if (!sourceNode || !targetNode) return false

    if (sourceNode.type === 'component' && targetNode.type === 'component')
      return connection.sourceHandle === 'right' && connection.targetHandle === 'left'

    if (sourceNode.type === 'router' || targetNode.type === 'router') return isValidRouterConnection(connection)

    if (sourceNode.type === 'component' && targetNode.type === 'worker')
      return connection.sourceHandle === 'bottom' && connection.targetHandle === 'top'

    if (sourceNode.type === 'worker' && targetNode.type === 'worker')
      return connection.sourceHandle === 'bottom' && connection.targetHandle === 'top'

    return false
  }

  const {
    nodes,
    edges,
    setNodes,
    setEdges,
    addNodes,
    addEdges,
    removeEdges,
    fitView,
    onNodesChange,
    onEdgesChange,
    onConnect,
    onEdgeClick,
    onNodeDragStop,
    onEdgeUpdateEnd,
    viewport,
    nodesDraggable,
    nodesConnectable,
    elementsSelectable,
  } = useVueFlow({
    id: 'studio-flow',
    defaultEdgeOptions: {
      type: 'smoothstep',
      animated: true,
      interactionWidth: 40,
      style: { strokeWidth: 2, stroke: 'rgb(var(--v-theme-primary))' },
    },
    deleteKeyCode: 'Backspace',
    nodesDraggable: true,
    nodesConnectable: true,
    elementsSelectable: true,
    connectOnClick: true,
    snapToGrid: true,
    snapGrid: [15, 15],
    isValidConnection: (conn: any) => checkConnectionValidity(conn),
    autoPanOnNodeDrag: true,
    elevateEdgesOnSelect: true,
  })

  // ─── Computed ──────────────────────────────────────────────────────
  const isDraftMode = computed(() => currentGraphRunner.value?.env === 'draft')

  const hasProductionDeployment = computed(() => {
    if (!currentProject.value?.graph_runners) return false
    return currentProject.value.graph_runners.some((runner: any) => runner.env === 'production')
  })

  const activeNodeData = computed(() => {
    if (!activeComponentId.value) return null
    return nodes.value.find(n => n.id === activeComponentId.value)?.data ?? null
  })

  // ─── Auto-save ─────────────────────────────────────────────────────
  let saveTimeout: ReturnType<typeof setTimeout> | null = null
  let validationResetTimeout: ReturnType<typeof setTimeout> | null = null

  // Callback set after both composables are initialized (avoids circular deps)
  let onBeforeLoadCallback: (() => void) | null = null

  function setOnBeforeLoad(fn: () => void) {
    onBeforeLoadCallback = fn
  }

  function cleanup() {
    if (saveTimeout) clearTimeout(saveTimeout)
    if (validationResetTimeout) clearTimeout(validationResetTimeout)
  }

  function autoSave() {
    if (!isDraftMode.value) return
    if (saveTimeout) clearTimeout(saveTimeout)
    saveTimeout = setTimeout(() => saveChanges(), 1000)
  }

  function markDirty() {
    hasUnsavedChanges.value = true
    autoSave()
  }

  // ─── VueFlow event handlers ────────────────────────────────────────
  const handleNodesChange = (changes: any[]) => {
    if (!isDraftMode.value) return
    setNodes(nds => applyNodeChanges(changes, nds))

    if (!isLoadingGraph.value && changes.some(c => c.type === 'remove')) markDirty()
  }

  const handleEdgesChange = (changes: any[]) => {
    setEdges(eds => {
      const newEdges = [...eds]

      changes.forEach(change => {
        if (change.type === 'remove') {
          const index = newEdges.findIndex(e => e.id === change.id)
          if (index !== -1) newEdges.splice(index, 1)
        }
      })
      return newEdges
    })

    if (!isLoadingGraph.value && changes.some(c => c.type === 'remove')) markDirty()
  }

  const handleNodeDragStop = () => {
    if (!isDraftMode.value) return
    markDirty()
  }

  const handleConnect = (connection: any) => {
    if (!isDraftMode.value) return

    const sourceNode = nodes.value.find(n => n.id === connection.source)
    const isRouterEdge = sourceNode?.type === 'router' && /^\d+$/.test(connection.sourceHandle || '')

    let edgeOrder = null
    let routeOrder = null

    if (isRouterEdge && connection.sourceHandle) {
      const handleIndex = parseInt(connection.sourceHandle, 10)
      const parameters = (sourceNode?.data?.parameters ?? []) as Parameter[]
      const routesParam = parameters.find((p: Parameter) => p.name === 'routes')
      const routes = parseRoutes(routesParam?.value)

      if (routes[handleIndex]) {
        routeOrder = routes[handleIndex].routeOrder ?? handleIndex
        edgeOrder = routeOrder
        if (routes[handleIndex].routeOrder === undefined || routes[handleIndex].routeOrder === null) {
          routes[handleIndex].routeOrder = handleIndex
        }
      } else {
        edgeOrder = handleIndex
        routeOrder = handleIndex
      }
    }

    const newEdge = {
      id: uuidv4(),
      source: connection.source,
      target: connection.target,
      sourceHandle: connection.sourceHandle,
      targetHandle: connection.targetHandle,
      type: 'smoothstep',
      interactionWidth: 40,
      sourcePosition: connection.sourceHandle === 'right' ? Position.Right : Position.Bottom,
      targetPosition: connection.targetHandle === 'left' ? Position.Left : Position.Top,
      style: { strokeWidth: 2, stroke: 'rgb(var(--v-theme-primary))' },
      data: { routeOrder },
      order: edgeOrder,
    }

    setEdges(eds => [...eds, newEdge])
    markDirty()
  }

  const handleEdgeUpdateEnd = () => {
    if (!isDraftMode.value) return
    markDirty()
  }

  const handleEdgeClick = (_params: any) => {
    // Edge selection is handled automatically by VueFlow — intentional no-op
  }

  // Register VueFlow event handlers
  onNodesChange(handleNodesChange)
  onEdgesChange(handleEdgesChange)
  onConnect(handleConnect)
  onNodeDragStop(handleNodeDragStop)
  onEdgeUpdateEnd(handleEdgeUpdateEnd)
  onEdgeClick(handleEdgeClick)

  // ─── Node visibility & active component ────────────────────────────
  function setActiveComponent(id: string | null) {
    activeComponentId.value = id

    if (id) {
      const directChildEdges = edges.value.filter(edge => edge.source === id)
      const directChildIds = new Set(directChildEdges.map(edge => edge.target))

      const updatedNodes = nodes.value.map(node => {
        const isTargetComponent = node.id === id
        const isDirectChild = node.type === 'worker' && directChildIds.has(node.id)
        return { ...node, hidden: !(isTargetComponent || isDirectChild) }
      })

      setNodes(updatedNodes)

      const pipelineEdges = edges.value.filter(edge => {
        const src = nodes.value.find(n => n.id === edge.source)
        const tgt = nodes.value.find(n => n.id === edge.target)
        return src?.type === 'component' && tgt?.type === 'component'
      })

      const connectedNodeIds = new Set<string>()

      pipelineEdges.forEach(edge => {
        connectedNodeIds.add(edge.source)
        connectedNodeIds.add(edge.target)
      })

      const { nodes: positionedNodes, edges: visibleEdges } = calculateLayout(updatedNodes, edges.value, id)

      setNodes(
        positionedNodes.map(pNode => {
          const originalNode = updatedNodes.find(n => n.id === pNode.id)

          const shouldPreservePosition =
            !connectedNodeIds.has(pNode.id) && pNode.type === 'component' && pNode.id !== id

          return {
            ...pNode,
            hidden: originalNode?.hidden ?? true,
            position: shouldPreservePosition ? originalNode?.position || pNode.position : pNode.position,
          }
        })
      )
      setEdges(visibleEdges)
      setTimeout(() => fitView({ padding: 0.4 }), 100)
    } else {
      const nodesForOverview = nodes.value.map(node => ({ ...node, hidden: node.type === 'worker' }))

      const pipelineEdges = edges.value.filter(edge => {
        const src = nodes.value.find(n => n.id === edge.source)
        const tgt = nodes.value.find(n => n.id === edge.target)
        return src?.type === 'component' && tgt?.type === 'component'
      })

      const connectedNodeIds = new Set<string>()

      pipelineEdges.forEach(edge => {
        connectedNodeIds.add(edge.source)
        connectedNodeIds.add(edge.target)
      })

      if (connectedNodeIds.size > 0) {
        const { nodes: positionedNodes, edges: visibleEdges } = calculateLayout(
          nodesForOverview,
          edges.value,
          undefined
        )

        setNodes(
          positionedNodes.map(pNode => {
            const originalNode = nodesForOverview.find(n => n.id === pNode.id)
            const shouldPreservePosition = !connectedNodeIds.has(pNode.id) && pNode.type === 'component'
            return {
              ...pNode,
              hidden: originalNode?.hidden ?? false,
              position: shouldPreservePosition ? originalNode?.position || pNode.position : pNode.position,
            }
          })
        )
        setEdges(visibleEdges)
      } else {
        setNodes(nodesForOverview)

        const visibleEdges = edges.value.map(edge => ({
          ...edge,
          hidden: !pipelineEdges.some(pe => pe.id === edge.id),
        }))

        setEdges(visibleEdges)
      }
      setTimeout(() => fitView({ padding: 0.4 }), 100)
    }
  }

  // ─── Graph loading ─────────────────────────────────────────────────
  async function loadGraphData(pid: string, retryCount = 0) {
    const maxRetries = 3
    const retryDelay = 500

    if (isLoadingGraph.value) {
      logger.warn('loadGraphData: Already loading, skipping concurrent load')
      return
    }

    isLoadingGraph.value = true
    isTransformingGraph.value = false

    setNodes([])
    setEdges([])
    activeComponentId.value = null
    hasUnsavedChanges.value = false
    validationStatus.value = 'valid'
    saveError.value = null
    onBeforeLoadCallback?.()

    try {
      if (!componentDefinitions.value || componentDefinitions.value.length === 0) {
        logger.info('[StudioFlow] Waiting for component definitions to load...')
        await new Promise(resolve => setTimeout(resolve, 100))
        if (!componentDefinitions.value || componentDefinitions.value.length === 0) {
          logger.warn('[StudioFlow] Component definitions not loaded, proceeding without client-side enrichment')
        }
      }

      let sourceData
      try {
        if (!currentGraphRunner.value) {
          if (retryCount < maxRetries) {
            logger.warn(
              `loadGraphData: No graph runner selected, retrying in ${retryDelay}ms (attempt ${retryCount + 1}/${maxRetries})`
            )
            isLoadingGraph.value = false
            setTimeout(() => loadGraphData(pid, retryCount + 1), retryDelay)
            return
          } else {
            logger.warn('loadGraphData: No graph runner selected after retries, cannot fetch graph.')
            setNodes([])
            setEdges([])
            return
          }
        }

        const graphRunnerId = currentGraphRunner.value.graph_runner_id
        // TODO: replace V1 getGraph with V2 endpoint once all component data is available from V2
        const response = await scopeoApi.studio.getGraph(pid, graphRunnerId)

        sourceData = response

        if (response?.playground_input_schema || response?.playground_field_types) {
          const config = {
            ...(response.playground_input_schema && { playground_input_schema: response.playground_input_schema }),
            ...(response.playground_field_types && { playground_field_types: response.playground_field_types }),
          }

          setPlaygroundConfig(config)
        } else {
          setPlaygroundConfig(null)
        }

        setGraphLastEditedInfo(
          response?.last_edited_time || null,
          response?.last_edited_user_id || null,
          selectedOrgId.value || undefined
        )
      } catch (error) {
        logger.error(`Error fetching graph data for project ${pid}`, { error })
        sourceData = { component_instances: [], relationships: [], edges: [] }
        setGraphLastEditedInfo(null, null, undefined)
        setPlaygroundConfig(null)
      }

      isTransformingGraph.value = true
      isLoadingGraph.value = false

      const transformResult = graphTransformer.toFlow(sourceData, componentDefinitions.value)
      const { nodes: initialNodes, edges: initialEdges } = transformResult

      let positionedNodes = initialNodes
      let visibleEdges = initialEdges as unknown as GraphEdge[]

      if (initialNodes.length > 0) {
        const layoutResult = calculateLayout(initialNodes, initialEdges as unknown as GraphEdge[], undefined)

        positionedNodes = layoutResult.nodes
        visibleEdges = layoutResult.edges as any
      }

      const nodesWithHiddenWorkers = positionedNodes.map(node => ({
        ...node,
        hidden: node.type === 'worker',
      }))

      setNodes(nodesWithHiddenWorkers as any)
      setEdges(visibleEdges)
      hasUnsavedChanges.value = false

      setTimeout(() => fitView({ padding: 0.5 }), 150)
    } catch (error) {
      logger.error(`Error during loadGraphData for project ${pid}`, { error })
      setNodes([])
      setEdges([])
    } finally {
      isLoadingGraph.value = false
      isTransformingGraph.value = false
    }
  }

  // ─── V2 lightweight topology refresh (used by WS reload) ──────────
  async function refreshGraphTopologyV2(pid: string) {
    if (!currentGraphRunner.value) return

    if (hasUnsavedChanges.value || isSaving.value) {
      pendingTopologyRefreshPid = pid
      return
    }
    pendingTopologyRefreshPid = null

    const graphRunnerId = currentGraphRunner.value.graph_runner_id
    try {
      const v2Response: GraphV2Response = await fetchGraphV2(pid, graphRunnerId)

      if (v2Response?.last_edited_time !== null && v2Response?.last_edited_time !== undefined) {
        setGraphLastEditedInfo(
          v2Response.last_edited_time,
          v2Response.last_edited_user_id || null,
          selectedOrgId.value || undefined
        )
      }

      const { nodes: mergedNodes, edges: mergedEdges, unknownNodeIds } = graphTransformer.mergeV2Topology(
        nodes.value,
        edges.value as unknown as StudioEdge[],
        v2Response
      )

      if (unknownNodeIds.length > 0) {
        logger.info(
          `V2 topology contains ${unknownNodeIds.length} unknown node(s), falling back to full graph load`,
          { unknownNodeIds }
        )
        await loadGraphData(pid)
        return
      }

      setNodes(mergedNodes as any)
      setEdges(mergedEdges as unknown as GraphEdge[])
    } catch (error) {
      logger.error(`Error during V2 topology refresh for project ${pid}`, { error })
    }
  }

  // ─── Graph saving ──────────────────────────────────────────────────
  function applyAutoGeneratedFieldExpressions(
    autoExprs:
      | Array<{
          component_instance_id: string
          field_name: string
          expression_json?: any
          expression_text?: string
        }>
      | undefined
      | null
  ) {
    if (!autoExprs || autoExprs.length === 0) return

    const exprsByInstance = new Map<string, typeof autoExprs>()
    for (const expr of autoExprs) {
      let list = exprsByInstance.get(expr.component_instance_id)
      if (!list) {
        list = []
        exprsByInstance.set(expr.component_instance_id, list)
      }
      list.push(expr)
    }

    const updatedNodes = nodes.value.map(node => {
      const exprsForNode = exprsByInstance.get(node.id)
      if (!exprsForNode) return node

      const existingExprs: Array<{
        field_name: string
        expression_json?: any
        expression_text?: string
      }> = Array.isArray(node.data?.field_expressions) ? [...node.data.field_expressions] : []

      const updatedParams = node.data?.parameters ? [...node.data.parameters] : []

      for (const autoExpr of exprsForNode) {
        const idx = existingExprs.findIndex(e => e.field_name === autoExpr.field_name)

        const newEntry = {
          field_name: autoExpr.field_name,
          expression_json: autoExpr.expression_json,
          expression_text: autoExpr.expression_text,
        }

        if (idx !== -1) existingExprs[idx] = newEntry
        else existingExprs.push(newEntry)

        const paramIdx = updatedParams.findIndex((p: any) => p.name === autoExpr.field_name)
        if (paramIdx !== -1) {
          updatedParams[paramIdx] = { ...updatedParams[paramIdx], value: autoExpr.expression_text }
        }
      }

      return { ...node, data: { ...node.data, field_expressions: existingExprs, parameters: updatedParams } }
    })

    setNodes(updatedNodes)

    if (selectedNode.value && exprsByInstance.has(selectedNode.value.id)) {
      const freshNode = updatedNodes.find(n => n.id === selectedNode.value!.id)
      if (freshNode) selectedNode.value = { ...freshNode } as GraphNode
    }
  }

  async function saveChanges() {
    if (!isDraftMode.value || isSaving.value) return

    saveError.value = null
    validationStatus.value = 'saving'
    isSaving.value = true

    try {
      if (!currentGraphRunner.value) throw new Error('Cannot save graph: No graph runner selected.')

      const pid = projectId.value
      const runnerId = currentGraphRunner.value.graph_runner_id

      const topologyData = graphTransformer.prepareTopologyForSaveV2(nodes.value, edges.value as StudioEdge[])

      const topologyResponse = await updateTopologyV2Mutation.mutateAsync({
        projectId: pid,
        graphRunnerId: runnerId,
        data: topologyData,
      })

      if (topologyResponse?.playground_input_schema || topologyResponse?.playground_field_types) {
        const newConfig = {
          ...(topologyResponse.playground_input_schema && {
            playground_input_schema: topologyResponse.playground_input_schema,
          }),
          ...(topologyResponse.playground_field_types && {
            playground_field_types: topologyResponse.playground_field_types,
          }),
        }

        setPlaygroundConfig(newConfig)
      }

      if (topologyResponse?.last_edited_time !== null && topologyResponse?.last_edited_time !== undefined) {
        setGraphLastEditedInfo(
          topologyResponse.last_edited_time,
          topologyResponse.last_edited_user_id || null,
          selectedOrgId.value || undefined
        )
      }

      applyAutoGeneratedFieldExpressions(topologyResponse?.auto_generated_field_expressions)

      queryClient.invalidateQueries({
        queryKey: ['modification-history', pid, runnerId],
      })

      hasUnsavedChanges.value = false
      validationStatus.value = 'just_saved'
      saveError.value = null
      if (validationResetTimeout) clearTimeout(validationResetTimeout)
      validationResetTimeout = setTimeout(() => {
        if (validationStatus.value === 'just_saved') validationStatus.value = 'valid'
      }, 2000)
    } catch (error: unknown) {
      logger.error('[StudioFlow] Error saving graph', { error })
      saveError.value = error instanceof Error ? error.message : 'Failed to save graph. Please try again.'
      validationStatus.value = 'invalid'
    } finally {
      isSaving.value = false
    }
  }

  // ─── Node CRUD ─────────────────────────────────────────────────────
  function getAllDescendantIds(nodeId: string, processedIds = new Set<string>()): string[] {
    if (processedIds.has(nodeId)) return []
    processedIds.add(nodeId)

    const descendantIds: string[] = []

    const childEdges = edges.value.filter(
      edge => edge.source === nodeId && edge.sourceHandle === 'bottom' && edge.targetHandle === 'top'
    )

    for (const edge of childEdges) {
      descendantIds.push(edge.target)
      descendantIds.push(...getAllDescendantIds(edge.target, processedIds))
    }
    return descendantIds
  }

  async function handleNodeDelete(nodeData: any) {
    if (!isDraftMode.value) return
    const nodeId = nodeData.id

    if (nodeData.data?.is_required_tool) {
      logger.warn('Cannot delete required tool')
      return
    }

    const startComponentId = import.meta.env.VITE_START_COMPONENT_ID
    if (nodeData.data?.component_id === startComponentId) {
      logger.warn('Cannot delete Start component')
      return
    }

    const descendantIds = getAllDescendantIds(nodeId)
    const allIdsToDelete = [nodeId, ...descendantIds]

    if (currentGraphRunner.value) {
      const pid = projectId.value
      const runnerId = currentGraphRunner.value.graph_runner_id
      const results = await Promise.allSettled(
        allIdsToDelete.map(id =>
          deleteComponentV2Mutation.mutateAsync({ projectId: pid, graphRunnerId: runnerId, instanceId: id })
        )
      )
      const failures = results.filter(r => r.status === 'rejected')
      if (failures.length > 0) {
        logger.error(`Failed to delete ${failures.length}/${allIdsToDelete.length} component(s), reloading graph`, {
          reasons: failures.map(f => (f as PromiseRejectedResult).reason),
        })
        await loadGraphData(pid)
        return
      }
    }

    setNodes(nodes.value.filter(node => !allIdsToDelete.includes(node.id)))
    setEdges(edges.value.filter(edge => !allIdsToDelete.includes(edge.source) && !allIdsToDelete.includes(edge.target)))

    if (activeComponentId.value === nodeId) setActiveComponent(null)
    markDirty()
  }

  function handleEdgeDelete(edgeId: string) {
    if (!isDraftMode.value) return
    removeEdges([edgeId])
    markDirty()
  }

  function createComponentOnServer(data: ComponentCreateV2Data) {
    if (!currentGraphRunner.value) throw new Error('Cannot create component: No graph runner selected.')
    return createComponentV2Mutation.mutateAsync({
      projectId: projectId.value,
      graphRunnerId: currentGraphRunner.value.graph_runner_id,
      data,
    })
  }

  async function createNodeFromTemplate(template: any) {
    if (!currentGraphRunner.value) throw new Error('Cannot create node: No graph runner selected.')

    const isRouter = isRouterComponent(template)
    const payload = buildCreatePayload(template, template.name)
    const response = await createComponentOnServer(payload)
    const newInstanceId = response.instance_id

    const mainNode = {
      id: newInstanceId,
      type: isRouter ? 'router' : 'component',
      data: createNodeData(template, { instanceId: newInstanceId, includeIconIntegration: true }),
      position: { x: 100, y: 100 },
    }

    const requiredTools =
      (template.subcomponents_info as SubcomponentInfo[] | undefined)?.filter(tool => !tool.is_optional) || []

    let toolNodes: any[] = []
    let toolRelationships: any[] = []

    if (requiredTools.length > 0 && componentDefinitions.value) {
      const result = await processToolsRecursively(
        newInstanceId, requiredTools, componentDefinitions.value, createComponentOnServer, {
          includeIconIntegration: true,
        }
      )

      toolNodes = result.nodes
      toolRelationships = result.relationships
    }

    return { nodes: [mainNode, ...toolNodes], relationships: toolRelationships }
  }

  async function addComponentToGraph(newNodeData: any, isToolMode: boolean) {
    const parentNodeId = activeComponentId.value
    let addedNodeIds: string[] = []

    if (Array.isArray(newNodeData.nodes) && newNodeData.nodes.length > 0) {
      const { nodes: newNodes, relationships: newRelationshipsFromDialog } = newNodeData
      let finalRelationships = newRelationshipsFromDialog || []
      const nodesToAdd = [...newNodes]

      if (isToolMode && parentNodeId) {
        const parentData = activeNodeData.value
        const toolParamName = parentData?.tool_parameter_name || 'agent_tools'
        const toolNode = nodesToAdd[0]

        if (toolNode) {
          toolNode.type = 'worker'
          toolNode.data = {
            ...toolNode.data,
            parent_component_id: parentNodeId,
            is_optional: true,
            is_required_tool: false,
            parameter_name: toolParamName,
          }
          finalRelationships = [
            {
              id: uuidv4(),
              parent_component_instance_id: parentNodeId,
              child_component_instance_id: toolNode.id,
              parameter_name: toolParamName,
              order: null,
            },
            ...finalRelationships,
          ]
          for (let i = 1; i < nodesToAdd.length; i++) nodesToAdd[i].type = 'worker'
        }
      } else if (isToolMode && !parentNodeId) {
        logger.error('Tool mode active, but no parentNodeId found. Cannot add tool correctly.')
        return
      }

      const positionedNodes = nodesToAdd.map((node, index) => {
        const isMainNode = isToolMode ? index === 0 : node.type === 'component' || node.type === 'router'

        let position = { x: 0, y: 0 }
        if (isMainNode) {
          if (isToolMode && activeComponentId.value) {
            const parentNode = nodes.value.find(n => n.id === activeComponentId.value)
            if (parentNode?.position) {
              const existingTools = nodes.value.filter(
                n =>
                  n.type === 'worker' &&
                  !n.hidden &&
                  edges.value.some(e => e.source === activeComponentId.value && e.target === n.id)
              )

              let lowestY = parentNode.position.y + 200
              if (existingTools.length > 0) {
                lowestY = Math.max(...existingTools.map(t => t.position?.y || 0)) + 150
              }
              position = { x: parentNode.position.x, y: lowestY }
            }
          } else {
            position = positionNewNode(nodes.value, node).position
          }
        }

        return {
          ...node,
          hidden: node.type === 'worker' && (!isToolMode || index > 0),
          position,
        }
      })

      addNodes(positionedNodes)
      addedNodeIds = positionedNodes.map(n => n.id)

      const newEdges = finalRelationships.map((rel: any) => ({
        id: rel.id || uuidv4(),
        source: rel.parent_component_instance_id,
        target: rel.child_component_instance_id,
        sourceHandle: 'bottom',
        targetHandle: 'top',
        type: 'smoothstep',
        sourcePosition: Position.Bottom,
        targetPosition: Position.Top,
        style: { strokeWidth: 2, stroke: 'rgb(var(--v-theme-primary))' },
        parameter_name: rel.parameter_name,
        data: { parameter_name: rel.parameter_name },
        hidden: positionedNodes.find(n => n.id === rel.child_component_instance_id)?.hidden ?? false,
      }))

      addEdges(newEdges)
      setTimeout(() => fitView({ padding: 0.4 }), 100)
    } else {
      logger.warn('addComponentToGraph received unexpected data format', { data: newNodeData })
      if (newNodeData && !Array.isArray(newNodeData) && typeof newNodeData === 'object' && newNodeData.id) {
        const positioned = positionNewNode(nodes.value, newNodeData)
        addNodes([positioned])
        addedNodeIds = [positioned.id]
        setTimeout(() => fitView({ padding: 0.4 }), 100)
      }
    }

    markDirty()
  }

  function updateNodeData(nodeId: string, data: any): GraphNode | null {
    const nodeIndex = nodes.value.findIndex(node => node.id === nodeId)
    if (nodeIndex === -1) return null

    const updatedNodes = [...nodes.value]

    updatedNodes[nodeIndex] = { ...nodes.value[nodeIndex], data } as GraphNode
    setNodes(updatedNodes)

    return updatedNodes[nodeIndex] as GraphNode
  }

  async function saveComponentV2(nodeId: string) {
    if (!isDraftMode.value || isSaving.value) return
    if (!currentGraphRunner.value) return

    const node = nodes.value.find(n => n.id === nodeId)
    if (!node) return

    isSaving.value = true
    saveError.value = null
    validationStatus.value = 'saving'

    try {
      const pid = projectId.value
      const runnerId = currentGraphRunner.value.graph_runner_id
      const componentData = graphTransformer.extractComponentUpdateV2(node)
      const response = await updateComponentV2Mutation.mutateAsync({
        projectId: pid,
        graphRunnerId: runnerId,
        instanceId: nodeId,
        data: componentData,
      })

      if (response?.last_edited_time !== null && response?.last_edited_time !== undefined) {
        setGraphLastEditedInfo(
          response.last_edited_time,
          response.last_edited_user_id || null,
          selectedOrgId.value || undefined
        )
      }

      queryClient.invalidateQueries({
        queryKey: ['modification-history', pid, runnerId],
      })

      validationStatus.value = 'just_saved'
      saveError.value = null
      if (validationResetTimeout) clearTimeout(validationResetTimeout)
      validationResetTimeout = setTimeout(() => {
        if (validationStatus.value === 'just_saved') validationStatus.value = 'valid'
      }, 2000)
    } catch (error: unknown) {
      logger.error(`[StudioFlow] Error saving component ${nodeId}`, { error })
      const message = error instanceof Error ? error.message : 'Failed to save component. Please try again.'
      saveError.value = message
      notify.error(message)
      validationStatus.value = 'invalid'
    } finally {
      isSaving.value = false
    }
  }

  async function handleAddTools({ nodes: newNodes, relationships }: { nodes: any[]; relationships: any[] }) {
    const positionedNodes = newNodes.map((node: any) => ({
      ...node,
      position: { x: 0, y: 0 },
    }))

    addNodes(positionedNodes)

    const newEdges = relationships.map((rel: any) => ({
      id: uuidv4(),
      source: rel.parent_component_instance_id,
      target: rel.child_component_instance_id,
      sourceHandle: 'bottom',
      targetHandle: 'top',
      type: 'smoothstep',
      sourcePosition: Position.Bottom,
      targetPosition: Position.Top,
      style: { strokeWidth: 2, stroke: 'rgb(var(--v-theme-info))' },
      parameter_name: rel.parameter_name,
      data: { parameter_name: rel.parameter_name },
    }))

    addEdges(newEdges)

    const { nodes: layoutedNodes, edges: layoutedEdges } = calculateLayout(
      [...nodes.value],
      [...edges.value],
      activeComponentId.value ?? undefined
    )

    setNodes(layoutedNodes)
    setEdges(layoutedEdges)

    markDirty()
  }

  async function handleRemoveTool({ nodeIds, parentId }: { nodeIds: string[]; parentId: string }) {
    if (currentGraphRunner.value) {
      const pid = projectId.value
      const runnerId = currentGraphRunner.value.graph_runner_id
      const results = await Promise.allSettled(
        nodeIds.map(id =>
          deleteComponentV2Mutation.mutateAsync({ projectId: pid, graphRunnerId: runnerId, instanceId: id })
        )
      )
      const failures = results.filter(r => r.status === 'rejected')
      if (failures.length > 0) {
        logger.error(`Failed to delete ${failures.length}/${nodeIds.length} tool(s), reloading graph`, {
          reasons: failures.map(f => (f as PromiseRejectedResult).reason),
        })
        await loadGraphData(pid)
        return
      }
    }

    setNodes(nodes.value.filter(node => !nodeIds.includes(node.id)))
    setEdges(
      edges.value.filter(edge => {
        const notConnectedToDeletedNodes = !nodeIds.includes(edge.source) && !nodeIds.includes(edge.target)

        const notParentChildRelationship = !(
          edge.source === parentId &&
          nodeIds.includes(edge.target) &&
          edge.sourceHandle === 'bottom' &&
          edge.targetHandle === 'top'
        )

        return notConnectedToDeletedNodes && notParentChildRelationship
      })
    )

    const { nodes: layoutedNodes, edges: layoutedEdges } = calculateLayout(
      nodes.value,
      edges.value,
      activeComponentId.value ?? undefined
    )

    setNodes(layoutedNodes)
    setEdges(layoutedEdges)
    markDirty()
  }

  // ─── Layout ────────────────────────────────────────────────────────
  function resetLayout() {
    if (!isDraftMode.value || nodes.value.length === 0) return

    const { nodes: positionedNodes, edges: visibleEdges } = calculateLayout(
      nodes.value,
      edges.value,
      activeComponentId.value ?? undefined
    )

    setNodes(
      positionedNodes.map(node => ({
        ...node,
        hidden: node.type === 'worker' && !activeComponentId.value,
      }))
    )
    setEdges(visibleEdges)
    setTimeout(() => fitView(), 100)
    markDirty()
  }

  // ─── Deploy ────────────────────────────────────────────────────────
  async function handleDeployConfirm() {
    if (!currentGraphRunner.value) return

    isDeploying.value = true
    try {
      const draftGraphRunnerId = currentGraphRunner.value.graph_runner_id
      const deployResponse = await scopeoApi.studio.deployGraph(projectId.value, draftGraphRunnerId)

      if (deployResponse.draft_graph_runner_id) {
        await refreshProjectData()
        hasUnsavedChanges.value = false
        await new Promise(resolve => setTimeout(resolve, 100))

        setCurrentGraphRunner({
          graph_runner_id: deployResponse.draft_graph_runner_id,
          env: 'draft',
          tag_name: null,
        })
        return deployResponse
      } else {
        throw new Error('Deploy response missing draft_graph_runner_id')
      }
    } finally {
      isDeploying.value = false
    }
  }

  // ─── Helpers ───────────────────────────────────────────────────────
  function nodeHasChildren(nodeId: string): boolean {
    return edges.value.some(
      edge => edge.source === nodeId && edge.sourceHandle === 'bottom' && edge.targetHandle === 'top'
    )
  }

  function getEnhancedNode(nodeId: string): GraphNode | null {
    const fullNode = nodes.value.find(n => n.id === nodeId)
    if (!fullNode) return null

    let canEditToolDescription = false
    if (fullNode.data?.function_callable === true) {
      const parentChildEdges = edges.value.filter(
        edge => edge.targetHandle === 'top' && edge.sourceHandle === 'bottom' && edge.target === fullNode.id
      )

      for (const edge of parentChildEdges) {
        const parentNode = nodes.value.find(n => n.id === edge.source)
        if (parentNode?.data?.can_use_function_calling === true) {
          canEditToolDescription = true
          break
        }
      }
    }

    return { ...fullNode, data: { ...fullNode.data, canEditToolDescription } } as GraphNode
  }

  async function refreshNodeFromServer(nodeId: string): Promise<GraphNode | null> {
    if (!currentGraphRunner.value) return null

    const existingNode = nodes.value.find(n => n.id === nodeId)
    if (!existingNode) return null

    try {
      const response = await fetchComponentV2(
        projectId.value,
        currentGraphRunner.value.graph_runner_id,
        nodeId
      )

      const freshData = graphTransformer.transformSingleInstanceData(
        response.component_instance,
        componentDefinitions.value
      )

      const structuralFields = {
        parent_component_id: existingNode.data?.parent_component_id,
        parent_info: existingNode.data?.parent_info,
        is_required_tool: existingNode.data?.is_required_tool,
        is_optional: existingNode.data?.is_optional,
        parameter_name: existingNode.data?.parameter_name,
        positionedByUser: existingNode.data?.positionedByUser,
        label: existingNode.data?.label,
      }

      const mergedData = { ...freshData, ...structuralFields }

      const updatedNodes = nodes.value.map(n =>
        n.id === nodeId ? { ...n, data: mergedData } as GraphNode : n
      )
      setNodes(updatedNodes)

      return getEnhancedNode(nodeId)
    } catch (error) {
      logger.error(`Failed to refresh node ${nodeId} from server`, { error })
      notify.error('Could not refresh component; showing cached data.')
      return getEnhancedNode(nodeId)
    }
  }

  function getNodeName(id: string): string {
    return nodes.value.find(n => n.id === id)?.data?.label || id
  }

  function getNodeType(id: string): string {
    return nodes.value.find(n => n.id === id)?.type || 'unknown'
  }

  function getActiveName(): string {
    if (!activeComponentId.value) return ''
    return nodes.value.find(node => node.id === activeComponentId.value)?.data?.name || 'Component'
  }

  // ─── Watchers ──────────────────────────────────────────────────────
  watch(projectId, async (newId, oldId) => {
    if (newId && newId !== oldId && !isLoadingGraph.value) await loadGraphData(newId)
  })

  watch(
    currentGraphRunner,
    async (newRunner, oldRunner) => {
      if (
        newRunner &&
        (!oldRunner || newRunner.graph_runner_id !== oldRunner.graph_runner_id) &&
        projectId.value &&
        !isLoadingGraph.value
      )
        await loadGraphData(projectId.value)
    },
    { deep: true }
  )

  watch(isSaving, (saving) => {
    if (!saving && pendingTopologyRefreshPid) {
      const pid = pendingTopologyRefreshPid
      pendingTopologyRefreshPid = null
      refreshGraphTopologyV2(pid)
    }
  })

  watch(
    isDraftMode,
    isDraft => {
      if (nodesDraggable) nodesDraggable.value = isDraft
      if (nodesConnectable) nodesConnectable.value = isDraft
      if (elementsSelectable) elementsSelectable.value = isDraft
    },
    { immediate: true }
  )

  // ─── Return ────────────────────────────────────────────────────────
  return {
    // VueFlow state
    nodes,
    edges,
    viewport,
    nodesDraggable,
    nodesConnectable,
    elementsSelectable,
    fitView,

    // State
    activeComponentId,
    isLoadingGraph,
    isTransformingGraph,
    hasUnsavedChanges,
    isDraftMode,
    hasProductionDeployment,
    isSaving,
    isDeploying,
    saveError,
    validationStatus,

    // Event handlers (exposed for template bindings)
    handleEdgeClick,
    handleNodeDelete,
    handleEdgeDelete,

    // Node CRUD
    createComponentOnServer,
    createNodeFromTemplate,
    addComponentToGraph,
    updateNodeData,
    saveComponentV2,
    handleAddTools,
    handleRemoveTool,

    // Layout & navigation
    resetLayout,
    setActiveComponent,
    nodeHasChildren,
    getEnhancedNode,
    refreshNodeFromServer,
    getNodeName,
    getNodeType,
    getActiveName,

    // Persistence
    loadGraphData,
    refreshGraphTopologyV2,
    saveChanges,
    autoSave,
    handleDeployConfirm,

    // Lifecycle
    setOnBeforeLoad,
    cleanup,
  }
}
