export const DEFAULT_PROJECT_ICON = 'ph-briefcase'

export const DEFAULT_PROJECT_COLOR = 'grey-500'

export function getProjectIcon(icon?: string | null): string {
  return icon || DEFAULT_PROJECT_ICON
}

export function getProjectColor(color?: string | null): string {
  return color || DEFAULT_PROJECT_COLOR
}
