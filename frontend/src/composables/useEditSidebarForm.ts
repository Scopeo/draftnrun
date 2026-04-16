import { type ComputedRef, computed, ref, watch } from 'vue'
import type { ComponentParameter } from '@/components/studio/data/component-definitions'
import {
  type GroupedParameterBucket,
  MAX_FILE_SIZE,
  type SidebarParameter,
  type SidebarParameterGroup,
  type Source,
} from '@/components/studio/components/edit-sidebar/types'
import {
  EMPTY_FORM_DATA,
  type FormDataShape,
  buildFormDataFromDefinition,
  buildFormDataFromExistingComponent,
} from '@/components/studio/components/edit-sidebar/form-initializer'
import { getComponentDefinitionFromCache } from '@/composables/queries/useComponentDefinitionsQuery'
import { useNotifications } from '@/composables/useNotifications'
import { useSelectedOrg } from '@/composables/useSelectedOrg'
import { scopeoApi } from '@/api'
import { logger } from '@/utils/logger'

export function useEditSidebarForm(
  componentData: ComputedRef<any>,
  componentDefinition: ComputedRef<any>,
  componentDefinitions: ComputedRef<any[]>,
  currentComponentId: ComputedRef<string | null>,
  isReadOnlyMode: ComputedRef<boolean>,
  drawer: ComputedRef<boolean>,
  componentId: ComputedRef<string | null>
) {
  const { notify } = useNotifications()
  const { selectedOrgId } = useSelectedOrg()

  const formData = ref<FormDataShape>({ ...EMPTY_FORM_DATA })
  const portConfigurations = ref<any[]>([])
  const showAdvanced = ref(false)
  const groupVisibility = ref<Record<string, boolean>>({})
  const jsonValidationState = ref<Record<string, 'valid' | 'invalid' | null>>({})
  const currentEditingComponentId = ref<string | null>(null)
  const sources = ref<Source[]>([])

  const isToolDescriptionEditable = computed(() => componentData.value?.canEditToolDescription === true)

  // --- Sources fetching ---
  async function fetchSources() {
    if (!selectedOrgId.value) return
    try {
      const response = await scopeoApi.sources.getAll(selectedOrgId.value)

      sources.value = response.map((s: any) => ({ id: s.id, name: s.name }))
    } catch (error) {
      logger.error('Error fetching sources', { error })
    }
  }

  watch(
    selectedOrgId,
    () => {
      fetchSources()
    },
    { immediate: true }
  )

  // --- Parameter grouping ---
  const visibleParameters = computed<SidebarParameter[]>(() => {
    const componentParams = (componentData.value?.parameters || []) as SidebarParameter[]

    const enrichedParams: SidebarParameter[] = componentParams.map((param: SidebarParameter) => {
      if (param.parameter_group_id) return param
      let defParam: ComponentParameter | null = null
      if (componentDefinition.value?.parameters)
        defParam = componentDefinition.value.parameters.find((p: ComponentParameter) => p.name === param.name) ?? null
      if (!defParam && currentComponentId.value && componentDefinitions.value) {
        const def = getComponentDefinitionFromCache(componentDefinitions.value, currentComponentId.value)
        if (def?.parameters) defParam = def.parameters.find((p: ComponentParameter) => p.name === param.name) ?? null
      }
      if (defParam) {
        const enriched: SidebarParameter = { ...param }
        if (defParam.parameter_order_within_group != null)
          enriched.parameter_order_within_group = defParam.parameter_order_within_group
        if (defParam.parameter_group_id) {
          enriched.parameter_group_id = defParam.parameter_group_id
          enriched.parameter_group_name = defParam.parameter_group_name
        }
        return enriched
      }
      return param
    })

    let filtered = enrichedParams.filter((p: SidebarParameter) => p.ui_component !== null)
    if (isToolDescriptionEditable.value) {
      filtered = filtered.filter(
        (p: SidebarParameter) =>
          p.kind === 'parameter' || p.kind === undefined || (p.kind === 'input' && p.is_tool_input === false)
      )
    }
    return filtered
  })

  const groupedParameters = computed(() => {
    const groups = new Map<string, GroupedParameterBucket>()
    const ungrouped: { basic: SidebarParameter[]; advanced: SidebarParameter[] } = { basic: [], advanced: [] }

    const findGroupDefinition = (groupId: string): SidebarParameterGroup | null => {
      if (componentDefinition.value?.parameter_groups) {
        const found = componentDefinition.value.parameter_groups.find((g: SidebarParameterGroup) => g.id === groupId)
        if (found) return found
      }
      if (currentComponentId.value && componentDefinitions.value) {
        const def = getComponentDefinitionFromCache(componentDefinitions.value, currentComponentId.value)
        if (def?.parameter_groups) {
          const found = def.parameter_groups.find((g: SidebarParameterGroup) => g.id === groupId)
          if (found) return found
        }
      }
      return null
    }

    visibleParameters.value.forEach((param: SidebarParameter) => {
      if (param.parameter_group_id) {
        const groupId = param.parameter_group_id
        if (!groups.has(groupId)) {
          groups.set(groupId, {
            group: findGroupDefinition(groupId),
            parameters: [],
            hasAdvanced: false,
            hasBasic: false,
          })
        }
        const group = groups.get(groupId)!

        group.parameters.push(param)
        if (param.is_advanced) group.hasAdvanced = true
        else group.hasBasic = true
      } else {
        if (param.is_advanced) ungrouped.advanced.push(param)
        else ungrouped.basic.push(param)
      }
    })

    const sortParams = (a: SidebarParameter, b: SidebarParameter) => {
      if (a.parameter_order_within_group != null && b.parameter_order_within_group != null)
        return a.parameter_order_within_group - b.parameter_order_within_group
      const aOrd = a.display_order ?? a.order
      const bOrd = b.display_order ?? b.order
      const aHas = aOrd !== null && aOrd !== undefined
      const bHas = bOrd !== null && bOrd !== undefined
      if (aHas && !bHas) return -1
      if (!aHas && bHas) return 1
      return (aOrd ?? 0) - (bOrd ?? 0)
    }

    groups.forEach(g => g.parameters.sort(sortParams))
    ungrouped.basic.sort(sortParams)
    ungrouped.advanced.sort(sortParams)

    const sortedGroups = Array.from(groups.values())
      .map(g => {
        if (!g.group && g.parameters.length > 0) {
          const first = g.parameters[0]
          if (first.parameter_group_name) {
            g.group = {
              id: first.parameter_group_id ?? `group-${first.name}`,
              name: first.parameter_group_name,
              group_order_within_component_version: 0,
            }
          }
        }
        return g
      })
      .filter((g): g is GroupedParameterBucket & { group: SidebarParameterGroup } => g.group !== null)
      .sort(
        (a, b) =>
          (a.group.group_order_within_component_version || 0) - (b.group.group_order_within_component_version || 0)
      )

    return { groups: sortedGroups, ungrouped }
  })

  const hasAdvancedParameters = computed(
    () =>
      groupedParameters.value.ungrouped.advanced.length > 0 ||
      groupedParameters.value.groups.some(g => g.hasAdvanced && !g.hasBasic)
  )

  watch(
    groupedParameters,
    newGroups => {
      newGroups.groups.forEach(group => {
        if (group.group && !(group.group.id in groupVisibility.value)) groupVisibility.value[group.group.id] = true
      })
    },
    { immediate: true, deep: true }
  )

  // --- JSON validation ---
  function validateAndFormatJson(paramName: string, value: string) {
    if (!value || value.trim() === '') {
      jsonValidationState.value[paramName] = null
      return value
    }
    try {
      const formatted = JSON.stringify(JSON.parse(value), null, 2)

      jsonValidationState.value[paramName] = 'valid'
      return formatted
    } catch {
      jsonValidationState.value[paramName] = 'invalid'
      return value
    }
  }

  function handleJsonFieldBlur(paramName: string) {
    const currentValue = formData.value.parameters[paramName]
    if (typeof currentValue === 'string') {
      const formatted = validateAndFormatJson(paramName, currentValue)
      if (jsonValidationState.value[paramName] === 'valid') formData.value.parameters[paramName] = formatted
    }
  }

  function validateExistingJsonFields() {
    if (formData.value.parameters.output_format) {
      const value = formData.value.parameters.output_format
      if (typeof value === 'string') {
        validateAndFormatJson('output_format', value)
      } else if (typeof value === 'object') {
        formData.value.parameters.output_format = JSON.stringify(value, null, 2)
        jsonValidationState.value.output_format = 'valid'
      }
    }
  }

  // --- File handling ---
  function handleFileSelection(paramName: string, file: File | File[] | FileList | null) {
    const existingValue = formData.value.parameters[paramName]
    if (!file) {
      formData.value.parameters[paramName] = null
      return
    }
    if (file instanceof FileList) {
      if (file.length === 0) {
        formData.value.parameters[paramName] = null
        return
      }
      file = file[0]
    }
    if (Array.isArray(file)) {
      if (file.length === 0) {
        formData.value.parameters[paramName] = null
        return
      }
      file = file[0]
    }
    if (file.size > MAX_FILE_SIZE) {
      notify.error(
        `File "${file.name}" exceeds the maximum size of 500KB. Current size: ${(file.size / 1024).toFixed(2)}KB. Please select a smaller file.`
      )
      formData.value.parameters[paramName] = existingValue
      return
    }
    formData.value.parameters[paramName] = file
  }

  function onFileModelUpdate(paramName: string, value: unknown) {
    handleFileSelection(paramName, value as File | File[] | FileList | null)
  }

  function handlePortConfigurationsUpdate(configs: any[]) {
    portConfigurations.value = configs
  }

  // --- Form initialization ---
  watch(
    () => [componentData.value, componentId.value],
    ([newComponentData]) => {
      const cid = (newComponentData as any)?.id || componentId.value
      if (drawer.value && cid && cid === currentEditingComponentId.value) return
      currentEditingComponentId.value = cid || null
      formData.value = { ...EMPTY_FORM_DATA, parameters: {}, toolDescription: { name: '', description: '' } }

      if (componentData.value) {
        const result = buildFormDataFromExistingComponent(
          componentData.value,
          componentDefinition.value,
          componentDefinitions.value,
          currentComponentId.value,
          isReadOnlyMode.value,
          sources.value
        )

        formData.value = result.formData
        portConfigurations.value = result.portConfigurations
        validateExistingJsonFields()
      } else if (componentId.value && componentDefinition.value) {
        const result = buildFormDataFromDefinition(componentDefinition.value)

        formData.value = result.formData
        portConfigurations.value = result.portConfigurations
        validateExistingJsonFields()
      }
    },
    { immediate: true }
  )

  // Merge auto-generated field expressions into the open form without resetting it
  watch(
    () => componentData.value?.field_expressions,
    (newExprs, oldExprs) => {
      if (!drawer.value || !currentEditingComponentId.value) return
      if (!Array.isArray(newExprs) || newExprs.length === 0) return
      const validParamNames = new Set(componentData.value?.parameters?.map((p: { name: string }) => p.name) || [])
      const oldTextByField = new Map<string, string>()
      if (Array.isArray(oldExprs)) {
        for (const e of oldExprs as Array<{ field_name: string; expression_text?: string }>) {
          if (e.expression_text) oldTextByField.set(e.field_name, e.expression_text)
        }
      }
      for (const expr of newExprs as Array<{ field_name: string; expression_text?: string }>) {
        if (!expr.expression_text || !validParamNames.has(expr.field_name)) continue
        const currentValue = formData.value.parameters[expr.field_name]
        const previousAutoText = oldTextByField.get(expr.field_name)
        if (!currentValue || currentValue === previousAutoText)
          formData.value.parameters[expr.field_name] = expr.expression_text
      }
    }
  )

  // Reset form when drawer is closed
  watch(
    () => drawer.value,
    isOpen => {
      if (!isOpen) {
        formData.value = { ...EMPTY_FORM_DATA, parameters: {}, toolDescription: { name: '', description: '' } }
        currentEditingComponentId.value = null
      }
    }
  )

  return {
    formData,
    portConfigurations,
    visibleParameters,
    groupedParameters,
    hasAdvancedParameters,
    showAdvanced,
    groupVisibility,
    jsonValidationState,
    handleJsonFieldBlur,
    handleFileSelection,
    onFileModelUpdate,
    handlePortConfigurationsUpdate,
    sources,
    isToolDescriptionEditable,
  }
}
