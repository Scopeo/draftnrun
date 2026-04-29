import { type ComputedRef, type Ref, computed, ref, watch } from 'vue'
import { useVueFlow } from '@vue-flow/core'
import type { SubcomponentInfo } from '@/components/studio/data/component-definitions'
import {
  EXCLUDED_PARAM_NAMES,
  type SidebarParameter,
  type Source,
  fileToBase64,
  isUiComponentType,
  normalizeUiComponent,
} from '@/components/studio/components/edit-sidebar/types'
import type { FormDataShape } from '@/components/studio/components/edit-sidebar/form-initializer'
import {
  type CreateComponentFn,
  buildCreatePayload,
  createNodeData,
  processToolsRecursively,
} from '@/components/studio/utils/node-factory.utils'
import { parseJsonStringToJsonBuild, transformConditionsToJsonBuild } from '@/composables/useFieldExpressions'
import { getComponentDefinitionFromCache } from '@/composables/queries/useComponentDefinitionsQuery'
import { useNotifications } from '@/composables/useNotifications'
import { logger } from '@/utils/logger'

export interface AddToolsPayload {
  nodes: Array<{
    id: string
    type: string
    data: Record<string, unknown>
    position: { x: number; y: number }
  }>
  relationships: Array<{
    parent_component_instance_id: string
    child_component_instance_id: string
    parameter_name: string
  }>
}

export interface RemoveToolPayload {
  nodeIds: string[]
  parentId: string
}

export type EditSidebarEmit = {
  (event: 'save', component: Record<string, unknown>): void
  (event: 'add-tools', payload: AddToolsPayload): void
  (event: 'remove-tool', payload: RemoveToolPayload): void
}

export function useEditSidebarSubmit(
  componentData: ComputedRef<any>,
  componentDefinition: ComputedRef<any>,
  componentDefinitions: ComputedRef<any[]>,
  formData: Ref<FormDataShape>,
  portConfigurations: Ref<any[]>,
  sources: Ref<Source[]>,
  isToolDescriptionEditable: ComputedRef<boolean>,
  drawer: {
    get: () => boolean
    set: (v: boolean) => void
  },
  emit: EditSidebarEmit,
  createComponent?: CreateComponentFn
) {
  const { nodes, edges, removeEdges } = useVueFlow()
  const { notify } = useNotifications()

  const showSaveError = ref(false)
  const saveErrorMessage = ref('')
  const pendingToolChanges = ref<{ toAdd: string[]; toRemove: string[] }>({ toAdd: [], toRemove: [] })

  const componentSubcomponents = computed<SubcomponentInfo[]>(
    () => ((componentData.value?.subcomponents_info as SubcomponentInfo[] | undefined) || []) as SubcomponentInfo[]
  )

  const optionalSubcomponents = computed(() =>
    componentSubcomponents.value.filter((sub: SubcomponentInfo) => sub.is_optional)
  )

  const enabledOptionalTools = ref<Record<string, boolean>>({})

  function handleOptionalToolToggle(toolId: string, enabled: boolean) {
    if (!componentData.value) return
    if (enabled) {
      const toolDef = getComponentDefinitionFromCache(componentDefinitions.value, toolId)
      if (!toolDef) return

      const subcompInfo = componentSubcomponents.value.find(
        (sub: SubcomponentInfo) => sub.component_version_id === toolId
      )

      if (!subcompInfo) return
      pendingToolChanges.value.toRemove = pendingToolChanges.value.toRemove.filter(id => id !== toolId)
      if (!pendingToolChanges.value.toAdd.includes(toolId)) pendingToolChanges.value.toAdd.push(toolId)
    } else {
      pendingToolChanges.value.toAdd = pendingToolChanges.value.toAdd.filter(id => id !== toolId)
      if (!pendingToolChanges.value.toRemove.includes(toolId)) pendingToolChanges.value.toRemove.push(toolId)
    }
  }

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

  async function onSubmit() {
    try {
      // Build parameters for update
      const parametersForUpdate = buildParametersForUpdate()

      // Process pending tool changes
      await processPendingToolAdditions()
      processPendingToolRemovals()
      pendingToolChanges.value = { toAdd: [], toRemove: [] }

      // Convert File objects to base64
      const processedParameters = await convertFilesToBase64(parametersForUpdate)

      // Cleanup router edges
      cleanupRouterEdges(processedParameters)

      // Build field expressions and finalize parameters
      const { fieldExpressions, regularParameters } = buildFieldExpressions(processedParameters)

      // Build and emit final component
      const updatedComponent = {
        ...componentData.value,
        ref: formData.value.label,
        name: formData.value.name,
        description: formData.value.description,
        parameters: regularParameters,
        field_expressions: fieldExpressions,
        ...(!componentData.value &&
          componentDefinition.value && {
            component_id: componentDefinition.value.component_id || componentDefinition.value.id,
            component_version_id: componentDefinition.value.component_version_id,
            component_name: componentDefinition.value.name,
            component_description: componentDefinition.value.description,
            inputs:
              componentDefinition.value.inputs ||
              componentDefinition.value.port_definitions?.filter((p: any) => p.port_type === 'INPUT'),
            outputs:
              componentDefinition.value.outputs ||
              componentDefinition.value.port_definitions?.filter((p: any) => p.port_type === 'OUTPUT'),
            function_callable: componentDefinition.value.function_callable,
            can_use_function_calling: componentDefinition.value.can_use_function_calling,
            subcomponents_info: componentDefinition.value.subcomponents_info,
            icon: componentDefinition.value.icon,
          }),
      }

      if (isToolDescriptionEditable.value) {
        updatedComponent.tool_description = {
          name: formData.value.toolDescription.name,
          description: formData.value.toolDescription.description,
        }
      }
      updatedComponent.port_configurations = portConfigurations.value

      emit('save', updatedComponent)
      drawer.set(false)
    } catch (error) {
      logger.error('[EditSidebar] Error saving component', { error })
      saveErrorMessage.value = `Failed to save: ${(error as Error)?.message || String(error) || 'Unknown error'}`
      showSaveError.value = true
    }
  }

  function buildParametersForUpdate(): SidebarParameter[] {
    const result: SidebarParameter[] = []
    for (const [paramName, paramValue] of Object.entries(formData.value.parameters)) {
      let paramDef: SidebarParameter | any | undefined
      if (componentData.value) {
        paramDef = (componentData.value.parameters || []).find((p: SidebarParameter) => p.name === paramName)
      } else if (componentDefinition.value) {
        paramDef = componentDefinition.value.parameters?.find((p: any) => p.name === paramName)
      }
      let finalValue = paramValue

      if (paramDef?.type === 'data_source') {
        const idsToSources = (ids: string[]) =>
          ids
            .map(id => {
              const s = sources.value.find(src => src.id === id)
              return s ? { id: s.id, name: s.name } : null
            })
            .filter(Boolean)

        if (Array.isArray(paramValue)) finalValue = idsToSources(paramValue)
        else if (paramValue && typeof paramValue === 'string') finalValue = idsToSources([paramValue])
        else finalValue = []
      }

      const isFileType = paramDef?.ui_component === 'FileUpload'
      if (isFileType) {
        if (paramValue instanceof File) {
          if (paramValue.size > 512000)
            throw new Error(
              `File "${paramValue.name}" exceeds the maximum size of 500KB. Current size: ${(paramValue.size / 1024).toFixed(2)}KB`
            )
          finalValue = paramValue
        } else if (paramValue instanceof FileList && paramValue.length > 0) {
          if (paramValue[0].size > 512000)
            throw new Error(
              `File "${paramValue[0].name}" exceeds the maximum size of 500KB. Current size: ${(paramValue[0].size / 1024).toFixed(2)}KB`
            )
          finalValue = paramValue[0]
        } else if (Array.isArray(paramValue) && paramValue.length > 0 && paramValue[0] instanceof File) {
          if (paramValue[0].size > 512000)
            throw new Error(
              `File "${paramValue[0].name}" exceeds the maximum size of 500KB. Current size: ${(paramValue[0].size / 1024).toFixed(2)}KB`
            )
          finalValue = paramValue[0]
        } else if (typeof paramValue === 'string' && paramValue.length > 0) {
          finalValue = paramValue
        } else if (paramValue != null) {
          finalValue = paramValue
        } else {
          finalValue = null
        }
      } else if (paramDef?.type === 'boolean') {
        finalValue = paramValue ?? false
      }

      if (Array.isArray(finalValue) && isUiComponentType(paramDef, 'MULTISELECT'))
        finalValue = JSON.stringify(finalValue)

      result.push({
        name: paramName,
        value: finalValue,
        kind: paramDef?.kind ?? 'parameter',
        type: paramDef?.type || typeof paramValue,
        nullable: paramDef?.nullable ?? true,
        ui_component: paramDef?.ui_component || null,
        ui_component_properties: paramDef?.ui_component_properties || null,
        is_advanced: paramDef?.is_advanced || false,
        is_tool_input: paramDef?.is_tool_input ?? true,
      })
    }
    return result
  }

  async function processPendingToolAdditions() {
    if (!createComponent) {
      if (pendingToolChanges.value.toAdd.length > 0) {
        logger.error('processPendingToolAdditions: createComponent callback not provided')
        notify.error('Unable to add tools: the component creation callback is unavailable.')
        throw new Error('Cannot process tool additions: createComponent callback not provided')
      }
      return
    }

    for (const toolId of pendingToolChanges.value.toAdd) {
      const toolDef = getComponentDefinitionFromCache(componentDefinitions.value, toolId)
      if (!toolDef) continue

      const subcompInfo = componentSubcomponents.value.find(
        (sub: SubcomponentInfo) => sub.component_version_id === toolId
      )

      if (!subcompInfo) continue

      const payload = buildCreatePayload(toolDef, toolDef.name)
      const response = await createComponent(payload)
      const mainNodeId = response.instance_id

      const mainNode = {
        id: mainNodeId,
        type: 'worker',
        data: createNodeData(toolDef, {
          instanceId: mainNodeId,
          parentId: componentData.value.id,
          parameterName: subcompInfo.parameter_name,
          isOptional: true,
          includeIconIntegration: false,
        }),
        position: { x: 0, y: 0 },
      }

      const requiredTools = toolDef.subcomponents_info?.filter((tool: any) => !tool.is_optional) || []
      if (requiredTools.length > 0) {
        const { nodes: toolNodes, relationships } = await processToolsRecursively(
          mainNodeId,
          requiredTools,
          componentDefinitions.value,
          createComponent,
          { filterRequired: true }
        )

        emit('add-tools', {
          nodes: [mainNode, ...toolNodes],
          relationships: [
            {
              parent_component_instance_id: componentData.value.id,
              child_component_instance_id: mainNodeId,
              parameter_name: subcompInfo.parameter_name,
            },
            ...relationships,
          ],
        })
      } else {
        emit('add-tools', {
          nodes: [mainNode],
          relationships: [
            {
              parent_component_instance_id: componentData.value.id,
              child_component_instance_id: mainNodeId,
              parameter_name: subcompInfo.parameter_name,
            },
          ],
        })
      }
    }
  }

  function processPendingToolRemovals() {
    for (const toolId of pendingToolChanges.value.toRemove) {
      const nodesToRemove = nodes.value.filter(
        node => node.data.component_version_id === toolId && node.data.parent_component_id === componentData.value.id
      )

      nodesToRemove.forEach(node => {
        const allIdsToDelete = [node.id, ...getAllDescendantIds(node.id)]

        emit('remove-tool', { nodeIds: allIdsToDelete, parentId: componentData.value.id })
      })
    }
  }

  async function convertFilesToBase64(params: SidebarParameter[]): Promise<SidebarParameter[]> {
    return Promise.all(
      params.map(async param => {
        if (param.ui_component === 'FileUpload' && param.value instanceof File) {
          try {
            const dataUrl = await fileToBase64(param.value)
            const base64String = dataUrl.includes(',') ? dataUrl.split(',')[1] : dataUrl
            return { ...param, value: base64String }
          } catch (error) {
            logger.error(`Failed to convert file to base64 for parameter ${param.name}`, { error })
            return { ...param, value: null }
          }
        }
        return param
      })
    )
  }

  function cleanupRouterEdges(processedParameters: SidebarParameter[]) {
    if (!componentData.value?.id) return
    const node = nodes.value.find(n => n.id === componentData.value.id)
    if (node?.type !== 'router') return
    const routesParam = processedParameters.find(p => p.name === 'routes')
    if (!routesParam || !Array.isArray(routesParam.value)) return

    const routes = routesParam.value
    const validRouteOrders = new Set(routes.map((r: any, idx: number) => r.routeOrder ?? idx))
    const routerEdges = edges.value.filter(e => e.source === node.id && /^\d+$/.test(e.sourceHandle || ''))
    const edgesToRemove = routerEdges.filter(edge => !validRouteOrders.has(parseInt(edge.sourceHandle || '0', 10)))
    if (edgesToRemove.length > 0) removeEdges(edgesToRemove.map(e => e.id))

    const routeOrderMap = new Map<number, number>()

    routes.forEach((route: any, newIndex: number) => {
      const oldOrder = route.routeOrder ?? newIndex

      routeOrderMap.set(oldOrder, newIndex)
      route.routeOrder = newIndex
    })

    const remainingRouterEdges = edges.value.filter(e => e.source === node.id && /^\d+$/.test(e.sourceHandle || ''))

    remainingRouterEdges.forEach(edge => {
      const oldHandle = parseInt(edge.sourceHandle || '0', 10)
      const newHandle = routeOrderMap.get(oldHandle)
      if (newHandle !== undefined && newHandle !== oldHandle) {
        edge.sourceHandle = String(newHandle)
        ;(edge as any).order = newHandle
      }
    })
  }

  function buildFieldExpressions(processedParameters: SidebarParameter[]) {
    const fieldExpressions: Array<{ field_name: string; expression_text: string }> = []
    const previouslyHadExpressions = new Set<string>()
    if (componentData.value?.field_expressions && Array.isArray(componentData.value.field_expressions)) {
      componentData.value.field_expressions.forEach((expr: { field_name: string }) =>
        previouslyHadExpressions.add(expr.field_name)
      )
    }

    const regularParameters = processedParameters.map(param => {
      const paramDef = componentDefinition.value?.parameters?.find((p: any) => p.name === param.name)

      const needsTransformation =
        (isUiComponentType(paramDef, 'CONDITIONBUILDER') || isUiComponentType(paramDef, 'ROUTEBUILDER')) &&
        Array.isArray(param.value) &&
        param.value.length > 0

      if (needsTransformation) {
        const jsonBuildNode = transformConditionsToJsonBuild(param.value)
        if (isUiComponentType(paramDef, 'ROUTEBUILDER')) {
          jsonBuildNode.template = jsonBuildNode.template.map((transformed: any, index: number) => ({
            ...param.value[index],
            ...transformed,
          }))
        }
        return { ...param, value: jsonBuildNode }
      }

      const paramUiNorm = normalizeUiComponent(param.ui_component)

      const isJsonTextarea =
        paramUiNorm === 'JSON_TEXTAREA' ||
        paramUiNorm === 'JSONTEXTAREA' ||
        isUiComponentType(paramDef, 'JSON_TEXTAREA') ||
        isUiComponentType(paramDef, 'JSONTEXTAREA')

      if (isJsonTextarea && typeof param.value === 'string' && param.value.trim()) {
        const result = parseJsonStringToJsonBuild(param.value)
        return { ...param, value: result ?? param.value }
      }

      const hasExpression =
        typeof param.value === 'string' &&
        /@\{\{[^}]+\}\}/.test(param.value) &&
        !EXCLUDED_PARAM_NAMES.includes(param.name) &&
        param.type !== 'number' &&
        param.type !== 'integer'

      if (hasExpression) {
        fieldExpressions.push({ field_name: param.name, expression_text: param.value })
        return param
      }

      return param
    })

    return { fieldExpressions, regularParameters }
  }

  // Reset pending changes when drawer closes
  watch(
    () => drawer.get(),
    isOpen => {
      if (!isOpen) {
        pendingToolChanges.value = { toAdd: [], toRemove: [] }
        if (componentData.value) {
          const childEdges = edges.value.filter(
            edge =>
              edge.source === componentData.value.id && edge.sourceHandle === 'bottom' && edge.targetHandle === 'top'
          )

          const existingChildIds = new Set(
            nodes.value
              .filter(node => childEdges.some(edge => edge.target === node.id))
              .map(node => node.data.component_version_id)
          )

          optionalSubcomponents.value.forEach((sub: SubcomponentInfo) => {
            enabledOptionalTools.value[sub.component_version_id] = existingChildIds.has(sub.component_version_id)
          })
        }
      }
    },
    { immediate: true }
  )

  // Initialize enabled tools when component changes
  watch(
    () => componentData.value,
    component => {
      if (component?.id) {
        enabledOptionalTools.value = {}

        const childEdges = edges.value.filter(
          edge => edge.source === component.id && edge.sourceHandle === 'bottom' && edge.targetHandle === 'top'
        )

        const childComponentIds = new Map<string, string>()

        nodes.value
          .filter(node => childEdges.some(edge => edge.target === node.id))
          .forEach(node => childComponentIds.set(node.data.component_version_id, node.id))
        optionalSubcomponents.value.forEach((sub: SubcomponentInfo) => {
          enabledOptionalTools.value[sub.component_version_id] = childComponentIds.has(sub.component_version_id)
        })
      }
    },
    { immediate: true }
  )

  return {
    onSubmit,
    showSaveError,
    saveErrorMessage,
    pendingToolChanges,
    handleOptionalToolToggle,
    componentSubcomponents,
    optionalSubcomponents,
    enabledOptionalTools,
  }
}
