import type { Condition } from './conditions'

/**
 * Route condition interface for Router components
 */
export interface Route extends Omit<Condition, 'next_logic'> {
  routeOrder?: number // Stable order number that persists across deletions
}

/**
 * Router outputs generation result
 */
export interface RouterOutputsResult {
  outputs: string[]
  routesCount: number
}
