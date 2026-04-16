/**
 * Authoritative router detection logic.
 * Priority: RouteBuilder UI component > routes parameter
 *
 * @param instance - Component instance with name and parameters
 * @returns true if the component should be treated as a router
 */
export function isRouterComponent(instance: {
  name?: string
  parameters?: Array<{ name: string; ui_component?: string | null }>
}): boolean {
  // Primary check: RouteBuilder UI component (most reliable)
  const hasRouteBuilder = instance.parameters?.some(p => p.ui_component === 'RouteBuilder')

  if (hasRouteBuilder) return true

  // Secondary check: routes parameter exists
  const hasRoutesParam = instance.parameters?.some(p => p.name === 'routes')

  return hasRoutesParam ?? false
}
