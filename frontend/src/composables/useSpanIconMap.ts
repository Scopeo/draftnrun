import { type Ref, computed } from 'vue'
import { useCurrentProject } from '@/composables/queries/useProjectsQuery'
import { useGraphQuery } from '@/composables/queries/useGraphQuery'

/**
 * Builds a reactive map from component instance name → icon string
 * by reading the current project's graph (uses TanStack Query cache).
 */
export function useSpanIconMap(projectId: Ref<string | undefined>) {
  const { currentGraphRunner } = useCurrentProject()

  const graphRunnerId = computed(() => currentGraphRunner.value?.graph_runner_id)
  const { data: graphData } = useGraphQuery(projectId, graphRunnerId)

  return computed<Record<string, string>>(() => {
    const instances = graphData.value?.component_instances
    if (!Array.isArray(instances)) return {}

    const map: Record<string, string> = {}
    for (const instance of instances) {
      if (instance.name && instance.icon) {
        map[instance.name] = instance.icon
      }
    }
    return map
  })
}
