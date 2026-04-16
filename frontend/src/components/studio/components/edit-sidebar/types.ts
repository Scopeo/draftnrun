import type { ComponentParameter } from '../../data/component-definitions'

export interface Source {
  id: string
  name: string
}

export interface SidebarParameter {
  name: string
  value: any
  type?: string
  nullable?: boolean
  default?: any
  ui_component?: string | null
  ui_component_properties?: Record<string, any> | null
  is_advanced?: boolean
  kind?: 'parameter' | 'input'
  is_tool_input?: boolean
  parameter_group_id?: string | null
  parameter_group_name?: string | null
  parameter_order_within_group?: number | null
  display_order?: number | null
  order?: number | null
}

export interface SidebarParameterGroup {
  id: string
  name: string
  group_order_within_component_version?: number | null
}

export interface GroupedParameterBucket {
  group: SidebarParameterGroup | null
  parameters: SidebarParameter[]
  hasAdvanced: boolean
  hasBasic: boolean
}

export interface ComponentConfig {
  component: any
  props: Record<string, any>
}

export interface PortDefinition {
  name: string
  port_type?: 'INPUT' | 'OUTPUT' | string
  is_canonical?: boolean
}

export function normalizeUiComponent(uiComponent: string | undefined | null): string {
  return uiComponent?.toUpperCase().replace(/\s+/g, '_') || ''
}

export function isUiComponentType(
  param: Pick<ComponentParameter, 'ui_component'> | Pick<SidebarParameter, 'ui_component'> | undefined,
  expectedType: string
): boolean {
  return normalizeUiComponent(param?.ui_component) === expectedType
}

export function isInlineLabelComponent(param: Pick<SidebarParameter, 'ui_component'>): boolean {
  return normalizeUiComponent(param.ui_component) === 'CHECKBOX'
}

export const EXCLUDED_FROM_INJECTION = [
  'output_format',
  'payload_schema',
  'file_content_key',
  'file_url_key',
  'static_message',
  'engine_url',
  'database_name',
  'role_to_use',
  'warehouse',
  'db_service',
  'include_tables',
  'additional_db_description',
  'synthesize',
  'method',
  'timeout',
  'project_id',
  'split_char',
  'join_char',
  'css_formatting',
  'template_base64',
  'additional_instructions',
  'completion_model',
  'api_key',
  'temperature',
  'prompt',
]

export const EXCLUDED_PARAM_NAMES = [...EXCLUDED_FROM_INJECTION, 'endpoint']

export function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()

    reader.onload = e => resolve(e.target?.result as string)
    reader.onerror = () => reject(new Error('Failed to read file'))
    reader.readAsDataURL(file)
  })
}

export function isFileObject(value: unknown): value is File {
  return typeof File !== 'undefined' && value instanceof File
}

export const MAX_FILE_SIZE = 512000 // 500KB

export function validateFileSize(file: File | File[] | null): boolean | string {
  if (!file) return true
  const files = Array.isArray(file) ? file : [file]
  for (const f of files) {
    if (f.size > MAX_FILE_SIZE)
      return `File size must be less than 500KB. Current size: ${(f.size / 1024).toFixed(2)}KB`
  }
  return true
}
