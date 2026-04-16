import type { Integration } from '../data/component-definitions'

export interface ToolDescription {
  name: string
  description: string
  tool_properties: Record<string, any>
  required_tool_properties: string[]
}

export interface Parameter {
  name: string
  value: any
  display_order: number | null
  type: string
  nullable: boolean
  default: any | null
  ui_component: string | null
  ui_component_properties: any | null
  is_advanced: boolean
  parameter_group_id: string | null
  parameter_order_within_group: number | null
  parameter_group_name: string | null
  kind?: 'parameter' | 'input'
  is_tool_input?: boolean
}

export interface NodeData {
  ref: string
  name: string
  component_id: string
  component_version_id: string
  is_agent: boolean
  parameters: Parameter[]
  tool_description: ToolDescription | null
  inputs?: string[]
  outputs?: string[]
  positionedByUser?: boolean
  can_use_function_calling?: boolean
  function_callable?: boolean
  tools?: any[]
  component_name?: string
  component_description?: string
  is_start_node?: boolean
  subcomponents_info?: any[]
  tool_parameter_name?: string | null
  parent_info?: {
    parent_id: string
    is_optional: boolean
    parameter_name: string
  } | null
  is_required_tool?: boolean
  is_optional?: boolean
  parameter_name?: string
  integration?: Integration
  icon?: string
}

export interface Node {
  id: string
  type: string
  data: NodeData
  position?: { x: number; y: number }
  hidden?: boolean
  selected?: boolean
  dragging?: boolean
}
