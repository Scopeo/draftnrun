import type { ComputedRef } from 'vue'

interface HasProjectIds {
  id: string
  project_ids?: string[]
}

export function useProjectAssociation<T extends HasProjectIds>(opts: {
  projectId: ComputedRef<string>
  allItems: ComputedRef<T[]>
}) {
  const { projectId, allItems } = opts

  const linkedItems = (items: T[]) =>
    items.filter(i => i.project_ids?.includes(projectId.value))

  const unlinkedItems = (items: T[]) =>
    items.filter(i => !i.project_ids?.includes(projectId.value))

  const buildAddProjectIds = (itemId: string): string[] | null => {
    const item = allItems.value.find(i => i.id === itemId)
    if (!item) return null
    return [...(item.project_ids || []), projectId.value]
  }

  const buildRemoveProjectIds = (itemId: string): string[] | null => {
    const item = allItems.value.find(i => i.id === itemId)
    if (!item) return null
    return (item.project_ids || []).filter(pid => pid !== projectId.value)
  }

  return { linkedItems, unlinkedItems, buildAddProjectIds, buildRemoveProjectIds }
}
