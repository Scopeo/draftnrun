import type { Parameter } from '../types/node.types'
import type { RouterOutputsResult } from '@/types/router'

/**
 * Generate router output handles from routes parameter
 *
 * @param parameters - Component parameters including routes
 * @param existingOutputs - Existing outputs to return if routes not found
 * @returns Router outputs and routes count
 */
export function generateRouterOutputs(parameters: Parameter[], existingOutputs: string[]): RouterOutputsResult {
  const routesParam = parameters.find(p => p.name === 'routes')

  if (!routesParam?.value) {
    return { outputs: existingOutputs, routesCount: 0 }
  }

  let routesCount = 0

  // Handle array format
  if (Array.isArray(routesParam.value)) {
    routesCount = routesParam.value.length
  }
  // Handle json_build format
  else if (
    typeof routesParam.value === 'object' &&
    routesParam.value.type === 'json_build' &&
    Array.isArray(routesParam.value.template)
  ) {
    routesCount = routesParam.value.template.length
  }

  if (routesCount === 0) {
    return { outputs: existingOutputs, routesCount: 0 }
  }

  const outputs = Array.from({ length: routesCount }, (_, i) => String(i))
  return { outputs, routesCount }
}
