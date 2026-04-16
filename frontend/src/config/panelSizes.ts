/**
 * Central configuration for panel sizes across agents and workflows
 * All playground and run history drawer sizes are defined here
 */

export const PANEL_SIZES = {
  // Default widths for all panels (playground and run history)
  DEFAULT_WIDTH: 440,

  // Minimum widths
  MIN_PLAYGROUND_WIDTH: 240,
  MIN_OBSERVABILITY_WIDTH: 240,

  // Expanded mode multiplier for run history
  EXPANDED_MULTIPLIER: 2.5,
} as const

export type PanelSizes = typeof PANEL_SIZES
