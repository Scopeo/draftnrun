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
