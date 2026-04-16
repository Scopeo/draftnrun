/**
 * Utility functions for router route handling
 */

import type { Route } from '@/types/router'

/**
 * Get human-readable route label
 *
 * @param index - Zero-based route index
 * @returns Route label (e.g., "Route 1")
 */
export function getRouteLabel(index: number): string {
  return `Route ${index + 1}`
}

/**
 * Get route port name for connections
 *
 * @param index - Zero-based route index
 * @returns Port name (e.g., "route_0")
 */
export function getRoutePortName(index: number): string {
  return `route_${index}`
}

/**
 * Parse routes from various formats (array or json_build)
 *
 * @param routesValue - Routes value from parameter
 * @returns Parsed array of routes
 */
export function parseRoutes(routesValue: unknown): Route[] {
  // Handle array format
  if (Array.isArray(routesValue)) {
    return routesValue
  }

  // Handle json_build format
  if (
    routesValue &&
    typeof routesValue === 'object' &&
    'type' in routesValue &&
    routesValue.type === 'json_build' &&
    'template' in routesValue &&
    Array.isArray(routesValue.template)
  ) {
    return routesValue.template
  }

  return []
}
