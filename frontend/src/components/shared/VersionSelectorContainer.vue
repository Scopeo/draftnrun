<script setup lang="ts">
import { computed, toRef, watch } from 'vue'
import VersionSelector from './VersionSelector.vue'
import { logger } from '@/utils/logger'
import { useVersionRefresh } from '@/composables/useVersionRefresh'
import { useCurrentAgent } from '@/composables/queries/useAgentsQuery'
import { useCurrentProject } from '@/composables/queries/useProjectsQuery'
import type { GraphRunner } from '@/types/version'

interface AgentEntity {
  id: string
  name: string
  graph_runners: GraphRunner[]
}

interface ProjectEntity {
  project_id: string
  project_name: string
  graph_runners: GraphRunner[]
}

interface Props {
  entity: AgentEntity | ProjectEntity
  entityType: 'agent' | 'project'
}

const props = defineProps<Props>()

const emit = defineEmits<{
  'update-graph-runners': [graphRunners: GraphRunner[]]
  'refresh-project': []
}>()

// Get entity ID (normalized for both agent and project)
const entityId = computed(() => {
  return props.entityType === 'agent' ? (props.entity as AgentEntity).id : (props.entity as ProjectEntity).project_id
})

// Get appropriate state management composable based on entity type
const { currentGraphRunner, setCurrentGraphRunner } =
  props.entityType === 'agent' ? useCurrentAgent() : useCurrentProject()

// Use unified refresh composable
const { isRefreshing, refreshAfterDeployment } = useVersionRefresh(
  entityId,
  toRef(() => props.entityType)
)

const graphRunners = computed(() => props.entity.graph_runners || [])

// Auto-select draft version for agents (keep existing behavior from AgentVersionSelector)
const draftVersion = computed(() =>
  props.entityType === 'agent' ? graphRunners.value.find(runner => runner.env === 'draft') : null
)

watch(
  () => props.entity,
  newEntity => {
    // Early return if not agent context
    if (props.entityType !== 'agent') return

    if (newEntity && graphRunners.value.length > 0) {
      const runnerToSelect = draftVersion.value || graphRunners.value[0]

      if (
        !currentGraphRunner.value ||
        !graphRunners.value.some(gr => gr.graph_runner_id === currentGraphRunner.value?.graph_runner_id)
      ) {
        if (runnerToSelect) {
          setCurrentGraphRunner(runnerToSelect)
        }
      }
    }
  },
  { immediate: true }
)

const handleChange = (selectedGraphRunnerId: string) => {
  const selectedGraphRunner = graphRunners.value.find(gr => gr.graph_runner_id === selectedGraphRunnerId)

  if (selectedGraphRunner) {
    setCurrentGraphRunner(selectedGraphRunner)
  }
}

const handleDeployed = async (graphRunnerId: string, env: 'production' | 'draft') => {
  if (isRefreshing.value) return

  try {
    const updatedGraphRunners = await refreshAfterDeployment(graphRunnerId, env)

    if (updatedGraphRunners) {
      // For agents: emit update-graph-runners event
      if (props.entityType === 'agent') {
        emit('update-graph-runners', updatedGraphRunners)
      }
      // For projects: emit refresh-project event
      else {
        emit('refresh-project')
      }

      // Handle case where current graph runner no longer exists (for both agents and projects)
      if (currentGraphRunner.value) {
        const runnerStillExists = updatedGraphRunners.some(
          r => r.graph_runner_id === currentGraphRunner.value?.graph_runner_id
        )

        if (!runnerStillExists) {
          // Select the new draft if available, otherwise the first runner
          const newDraftRunner = updatedGraphRunners.find(r => r.env === 'draft')
          const replacementRunner = newDraftRunner || updatedGraphRunners[0]
          if (replacementRunner) {
            setCurrentGraphRunner(replacementRunner)
          }
        }
      }
    }
  } catch (error) {
    logger.error('[VersionSelectorContainer] Failed to refresh after deployment', { error })
    // Error is already shown by the composables (useVersionDeployment/useVersionDraftLoading)
    // This catch prevents unhandled promise rejection
  }
}
</script>

<template>
  <VersionSelector
    :graph-runners="graphRunners"
    :current-graph-runner-id="currentGraphRunner?.graph_runner_id"
    :project-id="entityId"
    @change="handleChange"
    @deployed="handleDeployed"
  />
</template>
