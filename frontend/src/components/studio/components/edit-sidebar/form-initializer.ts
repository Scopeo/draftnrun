import type { ComponentParameter } from '../../data/component-definitions'
import { type SidebarParameter, type Source, isUiComponentType } from './types'
import { transformJsonBuildToConditions, transformJsonBuildToJsonObject } from '@/composables/useFieldExpressions'

export interface FormDataShape {
  label: string
  name: string
  parameters: Record<string, any>
  description: string
  toolDescription: { name: string; description: string }
}

export const EMPTY_FORM_DATA: FormDataShape = {
  label: '',
  name: '',
  parameters: {},
  description: '',
  toolDescription: { name: '', description: '' },
}

function getSelectDisplayValue(param: SidebarParameter, value: any, sources: Source[]): any {
  if (!value) return ''
  if (param.type === 'data_source') {
    if (Array.isArray(value)) {
      return value
        .map((v: any) => {
          if (typeof v === 'string') return sources.find(s => s.id === v)?.name || v
          if (typeof v === 'object' && v.name) return v.name
          return v
        })
        .join(', ')
    }
    if (typeof value === 'string') return sources.find(s => s.id === value)?.name || value
    if (typeof value === 'object' && value.name) return value.name
    return value
  }
  const options = param.ui_component_properties?.options || []
  const option = options.find((opt: any) => opt.value === value)
  return option?.label || value
}

function resolveParamValue(param: SidebarParameter, componentDefinition: any): SidebarParameter {
  if (param.parameter_group_id) return param
  let defParam: ComponentParameter | null = null
  if (componentDefinition?.parameters) {
    defParam = componentDefinition.parameters.find((p: ComponentParameter) => p.name === param.name) ?? null
  }
  if (!defParam) return param

  const enriched: SidebarParameter = { ...param }
  if (defParam.parameter_order_within_group != null)
    enriched.parameter_order_within_group = defParam.parameter_order_within_group
  if (defParam.parameter_group_id) {
    enriched.parameter_group_id = defParam.parameter_group_id
    enriched.parameter_group_name = defParam.parameter_group_name
  }
  return enriched
}

function extractParamValue(param: SidebarParameter, paramWithMetadata: SidebarParameter, componentData: any): any {
  if (paramWithMetadata.type === 'data_source') {
    const resolveId = (val: any): string | null => {
      if (val && typeof val === 'string') return val
      if (val && typeof val === 'object' && 'id' in val) return val.id
      return null
    }

    if (Array.isArray(param.value)) return param.value.map(resolveId).filter(Boolean)
    if (param.value) {
      const id = resolveId(param.value)
      return id ? [id] : []
    }
    return []
  }

  if (param.ui_component === 'FileUpload') {
    if (param.value instanceof File || param.value instanceof FileList) return param.value
    if (typeof param.value === 'string' && param.value.length > 0) return param.value
    if (param.value != null) return param.value
    return null
  }

  if (
    isUiComponentType(paramWithMetadata, 'CONDITIONBUILDER') ||
    isUiComponentType(paramWithMetadata, 'ROUTEBUILDER')
  ) {
    return extractConditionValue(paramWithMetadata, componentData)
  }

  if (isUiComponentType(paramWithMetadata, 'JSON_TEXTAREA') || isUiComponentType(paramWithMetadata, 'JSONTEXTAREA')) {
    return extractJsonTextareaValue(param, paramWithMetadata, componentData)
  }

  if (paramWithMetadata.type === 'json') {
    return extractJsonValue(param, paramWithMetadata)
  }

  let finalValue = param.value
  if (finalValue == null && param.default != null) finalValue = param.default
  else if (param.type === 'boolean' && finalValue == null) finalValue = param.default ?? false
  if ((param.type === 'number' || param.type === 'integer') && finalValue != null) finalValue = Number(finalValue)
  return finalValue
}

function extractConditionValue(param: SidebarParameter, componentData: any): any[] {
  if (param.value === '[JSON_BUILD]' && Array.isArray(componentData.field_expressions)) {
    const fieldExpr = componentData.field_expressions.find(
      (expr: { field_name: string; expression_json?: any }) => expr.field_name === param.name
    )

    if (fieldExpr?.expression_json) return transformJsonBuildToConditions(fieldExpr.expression_json)
    return []
  }
  if (Array.isArray(param.value)) return param.value
  if (param.value && typeof param.value === 'object' && param.value.type === 'json_build')
    return transformJsonBuildToConditions(param.value)
  return []
}

function extractJsonTextareaValue(
  param: SidebarParameter,
  paramWithMetadata: SidebarParameter,
  componentData: any
): any {
  if (paramWithMetadata.value === '[JSON_BUILD]' && Array.isArray(componentData.field_expressions)) {
    const fieldExpr = componentData.field_expressions.find(
      (expr: { field_name: string; expression_text?: string; expression_json?: any }) =>
        expr.field_name === paramWithMetadata.name
    )

    if (fieldExpr?.expression_text) return fieldExpr.expression_text
    if (fieldExpr?.expression_json) {
      const astNode = fieldExpr.expression_json

      const restored =
        astNode && typeof astNode === 'object' && astNode.type === 'json_build'
          ? transformJsonBuildToJsonObject(astNode)
          : astNode

      return JSON.stringify(restored, null, 2)
    }
    return ''
  }
  if (param.value && typeof param.value === 'object' && param.value.type === 'json_build')
    return JSON.stringify(transformJsonBuildToJsonObject(param.value), null, 2)
  if (param.value && typeof param.value === 'object' && 'expression_text' in param.value)
    return param.value.expression_text ?? ''
  if (param.value && typeof param.value === 'object' && 'expression_json' in param.value) {
    const astNode = param.value.expression_json

    const restored =
      astNode && typeof astNode === 'object' && astNode.type === 'json_build'
        ? transformJsonBuildToJsonObject(astNode)
        : astNode

    return JSON.stringify(restored, null, 2)
  }
  if (
    param.value &&
    typeof param.value === 'object' &&
    !Array.isArray(param.value) &&
    'template' in param.value &&
    'refs' in param.value
  )
    return JSON.stringify(transformJsonBuildToJsonObject(param.value as any), null, 2)
  return param.value ?? ''
}

function extractJsonValue(param: SidebarParameter, paramWithMetadata: SidebarParameter): any {
  if (param.value && typeof param.value === 'string') {
    try {
      return JSON.parse(param.value)
    } catch {
      return param.value
    }
  }
  if (param.value && typeof param.value === 'object' && param.value.type === 'json_build')
    return transformJsonBuildToJsonObject(param.value)
  if (param.value && typeof param.value === 'object') return param.value
  return isUiComponentType(paramWithMetadata, 'MULTISELECT') ? [] : {}
}

export function buildFormDataFromExistingComponent(
  componentData: any,
  componentDefinition: any,
  componentDefinitions: any[],
  currentComponentId: string | null,
  isReadOnlyMode: boolean,
  sources: Source[]
): { formData: FormDataShape; portConfigurations: any[] } {
  const paramValues: Record<string, any> = {}

  if (Array.isArray(componentData.parameters)) {
    ;(componentData.parameters as SidebarParameter[]).forEach((param: SidebarParameter) => {
      const paramDef = componentDefinition?.parameters?.find((p: ComponentParameter) => p.name === param.name)
      const paramWithMetadata: SidebarParameter = paramDef ? { ...param, ui_component: paramDef.ui_component } : param

      paramValues[param.name] = extractParamValue(param, paramWithMetadata, componentData)
    })

    loadFieldExpressions(componentData, componentDefinition, paramValues)

    if (isReadOnlyMode) {
      ;(componentData.parameters as SidebarParameter[]).forEach((param: SidebarParameter) => {
        if (isUiComponentType(param, 'SELECT') && paramValues[param.name] !== undefined)
          paramValues[param.name] = getSelectDisplayValue(param, paramValues[param.name], sources)
      })
    }
  } else {
    Object.assign(paramValues, componentData.parameters || {})
  }

  return {
    formData: {
      label: componentData.ref || '',
      name: componentData.name || '',
      parameters: paramValues,
      description: componentData.description || '',
      toolDescription: {
        name: componentData.tool_description?.name || '',
        description: componentData.tool_description?.description || '',
      },
    },
    portConfigurations: componentData.port_configurations || [],
  }
}

function loadFieldExpressions(componentData: any, componentDefinition: any, paramValues: Record<string, any>): void {
  if (!Array.isArray(componentData.field_expressions)) return

  const validParamNames = new Set(componentData.parameters?.map((p: { name: string }) => p.name) || [])

  componentData.field_expressions.forEach(
    (expr: { field_name: string; expression_text?: string; expression_json?: any }) => {
      if (!validParamNames.has(expr.field_name)) return

      if (expr.expression_text) {
        const currentValue = paramValues[expr.field_name]
        if (!currentValue || currentValue === expr.expression_text) paramValues[expr.field_name] = expr.expression_text
      } else if (expr.expression_json) {
        const exprParamDef = componentDefinition?.parameters?.find((p: { name: string }) => p.name === expr.field_name)
        if (isUiComponentType(exprParamDef, 'JSON_TEXTAREA') || isUiComponentType(exprParamDef, 'JSONTEXTAREA')) {
          const astNode = expr.expression_json

          const restored =
            astNode && typeof astNode === 'object' && astNode.type === 'json_build'
              ? transformJsonBuildToJsonObject(astNode)
              : astNode

          const text = JSON.stringify(restored, null, 2)
          const currentValue = paramValues[expr.field_name]
          if (!currentValue || currentValue === text) paramValues[expr.field_name] = text
        }
      }
    }
  )
}

export function buildFormDataFromDefinition(componentDefinition: any): {
  formData: FormDataShape
  portConfigurations: any[]
} {
  const paramValues: Record<string, any> = {}
  if (componentDefinition.parameters) {
    componentDefinition.parameters.forEach((param: ComponentParameter) => {
      if (isUiComponentType(param, 'CONDITIONBUILDER') || isUiComponentType(param, 'ROUTEBUILDER')) {
        paramValues[param.name] = param.default ?? []
      } else if (param.type === 'json') {
        if (param.default && typeof param.default === 'string') {
          try {
            paramValues[param.name] = JSON.parse(param.default)
          } catch {
            paramValues[param.name] = param.default
          }
        } else if (param.default && typeof param.default === 'object' && param.default.type === 'json_build') {
          paramValues[param.name] = transformJsonBuildToJsonObject(param.default)
        } else if (param.default && typeof param.default === 'object') {
          paramValues[param.name] = param.default
        } else {
          paramValues[param.name] = {}
        }
      } else if (param.type === 'boolean') {
        paramValues[param.name] = param.default ?? false
      } else if (param.type === 'number' || param.type === 'integer') {
        paramValues[param.name] = param.default != null ? Number(param.default) : null
      } else {
        paramValues[param.name] = param.default ?? null
      }
    })
  }

  return {
    formData: {
      label: componentDefinition.name || '',
      name: componentDefinition.name || '',
      parameters: paramValues,
      description: componentDefinition.description || '',
      toolDescription: {
        name: componentDefinition.tool_description?.name || '',
        description: componentDefinition.tool_description?.description || '',
      },
    },
    portConfigurations: [],
  }
}
