export interface Edge {
  id: string
  source: string
  target: string
  order?: number | null
  parameter_name?: string
  data?: {
    parameter?: string
    parameter_name?: string
  }
  hidden?: boolean
  sourcePosition?: string
  targetPosition?: string
  sourceHandle?: string
  targetHandle?: string
  type?: string
  animated?: boolean
  selectable?: boolean
  deletable?: boolean
  style?: Record<string, any>
}
