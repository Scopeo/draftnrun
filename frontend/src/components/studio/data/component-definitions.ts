import type { CreditFields } from '@/types/credits'

export interface PortDefinition {
  id: string
  name: string
  port_type: 'INPUT' | 'OUTPUT'
  is_canonical: boolean
  description: string
  parameter_type: string
  nullable: boolean
}

export interface ComponentParameter {
  id?: string
  name: string
  order: number | null
  type: string
  nullable: boolean
  default: any
  description?: string
  ui_component: string | null
  ui_component_properties: Record<string, any> | null
  is_advanced: boolean
  parameter_group_id: string | null
  parameter_order_within_group: number | null
  parameter_group_name: string | null
  kind?: 'parameter' | 'input'
  is_tool_input?: boolean
}

export interface ToolProperty {
  type: string
  description: string
  enum?: string[]
  items?: {
    type: string
  }
}

export interface ToolDescription {
  name: string
  description: string
  tool_properties: Record<string, ToolProperty>
  required_tool_properties: string[]
}

export interface RequiredTool {
  name: string
  optional: boolean
}

export interface Integration {
  id: string
  name: string
  service: string
  secret_id?: string
}

export interface SubcomponentInfo {
  component_version_id: string
  parameter_name: string
  is_optional: boolean
}

export interface ParameterGroup {
  id: string
  name: string
  group_order_within_component_version: number
}

export interface ComponentDefinition extends CreditFields {
  id?: string
  name: string
  component_id: string
  component_version_id: string
  version_tag?: string // Display version from backend
  description?: string
  function_callable: boolean // Can be a worker (vertical child)
  can_use_function_calling: boolean // Can have children
  release_stage?: string
  parameters: ComponentParameter[]
  parameter_groups?: ParameterGroup[]
  tool_description: ToolDescription | null
  tools?: RequiredTool[] // Required tools for this component
  is_agent?: boolean
  inputs?: any[]
  outputs?: any[]
  subcomponents_info?: SubcomponentInfo[]
  integration?: Integration
  icon: string
  category_ids?: string[] // Category UUIDs from component
  port_definitions?: PortDefinition[]
}
