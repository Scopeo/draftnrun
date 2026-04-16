import type { ComponentDefinition } from '../data/component-definitions'

/**
 * Create a lookup map for component definitions.
 * Uses component_version_id as primary key, with id and component_id as fallbacks.
 */
export function createComponentDefinitionMap(
  componentDefinitions?: ComponentDefinition[]
): Map<string, ComponentDefinition> {
  const map = new Map<string, ComponentDefinition>()

  if (!componentDefinitions) return map

  componentDefinitions.forEach(def => {
    if (def.component_version_id) {
      map.set(def.component_version_id, def)
    }
    if (def.id) {
      map.set(def.id, def)
    }
    if (def.component_id) {
      map.set(def.component_id, def)
    }
  })

  return map
}

/**
 * Find a component definition by any of its identifiers.
 * Checks component_version_id first, then id, then component_id.
 */
export function findComponentDefinition(
  componentDefinitions: ComponentDefinition[] | undefined,
  versionId: string,
  componentId?: string,
  id?: string
): ComponentDefinition | undefined {
  if (!componentDefinitions) return undefined

  return componentDefinitions.find(
    comp =>
      comp.component_version_id === versionId ||
      (id && comp.id === id) ||
      (componentId && comp.component_id === componentId)
  )
}
