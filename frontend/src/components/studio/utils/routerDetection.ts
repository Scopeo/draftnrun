/**
 * Authoritative router detection logic.
 * Priority: RouteBuilder UI component > routes parameter
 *
 * @param instance - Component instance with name and parameters
 * @returns true if the component should be treated as a router
 */
export function isRouterComponent(instance: {
  name?: string
  component_name?: string
  parameters?: Array<{ name: string; ui_component?: string | null }>
}): boolean {
  // Primary check: RouteBuilder UI component (most reliable)
  const hasRouteBuilder = instance.parameters?.some(p => p.ui_component === 'RouteBuilder')

  if (hasRouteBuilder) return true

  // Secondary check: routes parameter exists
  const hasRoutesParam = instance.parameters?.some(p => p.name === 'routes')

  return hasRoutesParam ?? false
}

export function isIfElseComponent(instance: {
  name?: string
  component_name?: string
  parameters?: Array<{ name: string; ui_component?: string | null }>
}): boolean {
  const componentName = instance.component_name?.toLowerCase()
  if (componentName === 'if_else') return true

  const displayName = instance.name?.toLowerCase()
  if (displayName === 'if/else') return true

  return instance.parameters?.some(p => p.name === 'conditions' && p.ui_component === 'ConditionBuilder') ?? false
}

export function isBranchingComponent(instance: {
  name?: string
  component_name?: string
  parameters?: Array<{ name: string; ui_component?: string | null }>
}): boolean {
  return isRouterComponent(instance) || isIfElseComponent(instance)
}

export function isTruthyBooleanValue(value: unknown): boolean {
  if (typeof value === 'boolean') return value
  if (typeof value === 'string') return ['true', '1', 'yes', 'on'].includes(value.trim().toLowerCase())
  return Boolean(value)
}

export function hasIfElseFalsePath(instance: {
  parameters?: Array<{ name: string; value?: unknown; default?: unknown }>
}): boolean {
  const param = instance.parameters?.find(p => p.name === 'enable_false_path')
  return isTruthyBooleanValue(param?.value ?? param?.default ?? false)
}
