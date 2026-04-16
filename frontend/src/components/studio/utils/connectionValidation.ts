/**
 * Connection validation utilities for Vue Flow
 */

/**
 * Check if a handle is a numeric router output handle
 */
function isRouterOutputHandle(handle?: string | null): boolean {
  if (!handle) return false
  // Check if handle is a numeric string (0, 1, 2, etc.)
  return /^\d+$/.test(handle)
}

/**
 * Validates router node connections
 * Handles both input and output connections for router nodes
 *
 * @param connection - Vue Flow connection object with source/target handles
 * @returns true if the connection is valid for a router node
 */
export function isValidRouterConnection(connection: {
  sourceHandle?: string | null
  targetHandle?: string | null
}): boolean {
  // Router input: allow right-to-left connections
  if (connection.targetHandle === 'left' && connection.sourceHandle === 'right') {
    return true
  }

  // Router route outputs: allow numeric handle-to-left connections
  if (isRouterOutputHandle(connection.sourceHandle) && connection.targetHandle === 'left') {
    return true
  }

  return false
}
