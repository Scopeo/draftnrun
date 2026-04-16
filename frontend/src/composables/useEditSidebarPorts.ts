import { type ComputedRef, computed } from 'vue'
import { useVueFlow } from '@vue-flow/core'

export function useEditSidebarPorts(componentData: ComputedRef<any>) {
  const { nodes, edges } = useVueFlow()

  const upstreamNodes = computed(() => {
    if (!componentData.value?.id) return []
    const incoming = edges.value.filter(e => e.target === componentData.value.id && e.targetHandle === 'left')
    const ids = new Set(incoming.map(e => e.source))
    return nodes.value.filter(n => ids.has(n.id))
  })

  return { upstreamNodes }
}
