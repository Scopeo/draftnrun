<script setup lang="ts">
import { useAbility } from '@casl/vue'
import type { NodeProps } from '@vue-flow/core'
import { Handle, Position, useVueFlow } from '@vue-flow/core'
import { computed, inject, onMounted, ref, watch } from 'vue'
import { Icon } from '@iconify/vue'
import { isProviderLogo } from '../utils/node-factory.utils'
import type { Parameter } from '../types/node.types'
import { logger } from '@/utils/logger'
import type { NodeExecutionState } from '@/types/graphExecutionStream'
import { GRAPH_EXECUTION_KEY } from '@/composables/useGraphExecutionStream'

interface SpecialNodeProps extends NodeProps {
  isDraftMode: boolean
  isZoomedIn?: boolean
  activeComponentId?: string | null
  hasChildren?: boolean
}

const props = defineProps<SpecialNodeProps>()
const emit = defineEmits(['delete', 'add-tool'])
const ability = useAbility()
const { edges } = useVueFlow()

const graphExecution = inject(GRAPH_EXECUTION_KEY, null)
const executionState = computed<NodeExecutionState>(() => {
  return graphExecution?.nodeStates.value.get(props.id) ?? 'idle'
})

const data = computed(() => props.data || {})
const isWorker = computed(() => props.type === 'worker')
const canDelete = computed(() => props.isDraftMode)

// Show confirmation dialog for delete
const showDeleteConfirmation = ref(false)

const isDeletable = computed(() => {
  // Cannot delete if it's the Start component
  const startComponentId = import.meta.env.VITE_START_COMPONENT_ID
  if (props.data?.component_id === startComponentId) return false

  return true
})

// Determine if this node is a child (has parent through top handle)
const isChild = computed(() => {
  return edges.value.some(
    edge => edge.target === props.id && edge.targetHandle === 'top' && edge.sourceHandle === 'bottom'
  )
})

// Determine if this is the active (parent) component when zoomed in
const isActiveParent = computed(() => {
  return props.isZoomedIn && props.activeComponentId === props.id
})

// Determine if this is a last child (has no children of its own)
const isLastChild = computed(() => {
  return !props.hasChildren && isChild.value
})

// Handle visibility logic
const showLeftRightHandles = computed(() => {
  // Show left/right handles when:
  // 1. Not zoomed in (overview mode) for all components
  // 2. Never for workers/children
  return !props.isZoomedIn && !isWorker.value
})

const showTopHandle = computed(() => {
  // Show top handle when:
  // 1. It's a worker/child (always)
  // 2. When zoomed in and it's a child component
  return isWorker.value || (props.isZoomedIn && isChild.value)
})

const showBottomHandle = computed(() => {
  // Show bottom handle when:
  // 1. It's a worker/child that can have its own children
  // 2. When zoomed in and it's the active parent component
  // 3. When zoomed in and it's a child that can have children
  // 4. When it's a last child (so it can potentially have children added)
  return (
    (isWorker.value && props.hasChildren) ||
    (props.isZoomedIn && (isActiveParent.value || (isChild.value && props.hasChildren))) ||
    (props.isZoomedIn && isLastChild.value)
  )
})

// Show + button for adding tools - only if can use function calling and has update permissions
const showAddToolButton = computed(() => {
  return props.isDraftMode && data.value.can_use_function_calling && ability.can('update', 'Project')
})

// Handle delete request with confirmation
const handleDeleteRequest = (event: MouseEvent) => {
  if (!canDelete.value) return
  event.stopPropagation()
  showDeleteConfirmation.value = true
}

// Confirm node deletion
const confirmDelete = () => {
  emit('delete', {
    id: props.id,
  })
  showDeleteConfirmation.value = false
}

// Cancel deletion
const cancelDelete = () => {
  showDeleteConfirmation.value = false
}

// Handle add tool button click
const handleAddTool = (event: MouseEvent) => {
  event.stopPropagation()
  emit('add-tool', { nodeId: props.id })
}

// Validate connection based on handle positions
const isValidConnection = (connection: any) => {
  // Only allow horizontal connections (left to right)
  // For component-to-component connections, ensure it's right-to-left
  if (connection.sourceHandle === 'right' && connection.targetHandle === 'left') {
    // Valid left-to-right connection
    return true
  }

  // For worker connections, allow top-to-bottom
  if (connection.sourceHandle === 'bottom' && connection.targetHandle === 'top') {
    // Valid top-to-bottom connection
    return true
  }

  return false
}

// Check if this is a ProjectReference component
const isProjectReference = computed(() => {
  return data.value.component_id === '4c8f9e2d-1a3b-4567-8901-234567890abc'
})

// Lazy-loaded project/agent name cache for ProjectReference nodes
const projectNameCache = ref<string | null>(null)

// Get display name for the node
const getDisplayName = computed(() => {
  // For ProjectReference nodes, show cached project name or fallback to component name
  if (isProjectReference.value && projectNameCache.value) {
    return projectNameCache.value
  }
  return data.value.name
})

// Determine the appropriate icon based on component type
const getComponentIcon = computed(() => {
  // If an icon was defined, it is the string we want.
  if (data.value.icon != null) {
    return data.value.icon
  }
  // Check if this is a special component
  else if (data.value.name === 'Input') {
    return 'tabler-square-rounded-arrow-right'
  }
  // Default icons for worker vs non-worker
  return isWorker.value ? 'tabler-tools' : 'tabler-user-bolt'
})

const iconColor = computed(() => {
  return isWorker.value ? 'secondary' : 'primary'
})

// Lazy fetch project/agent name for ProjectReference nodes only when needed
async function fetchProjectName(projectId: string) {
  try {
    // Lazy import to avoid initializing queries for non-ProjectReference nodes
    const { useProjectsQuery } = await import('@/composables/queries/useProjectsQuery')
    const { useAgentsQuery } = await import('@/composables/queries/useAgentsQuery')
    const { useSelectedOrg } = await import('@/composables/useSelectedOrg')

    const { selectedOrgId } = useSelectedOrg()
    const { data: projects, refetch: fetchProjects } = useProjectsQuery(selectedOrgId)
    const { data: agents, refetch: fetchAgents } = useAgentsQuery(selectedOrgId)

    // Fetch fresh data
    await Promise.all([fetchProjects(), fetchAgents()])

    // Try to find in projects first
    const project = projects.value?.find(p => p.project_id === projectId)
    if (project) {
      projectNameCache.value = project.project_name
      return
    }

    // Then try agents
    const agent = agents.value?.find(a => a.id === projectId)
    if (agent) {
      projectNameCache.value = agent.name
    }
  } catch (error) {
    logger.error('[SpecialNode] Error fetching project name', { error })
  }
}

// Fetch project name when ProjectReference node mounts (if needed)
onMounted(async () => {
  if (isProjectReference.value) {
    const parameters = (data.value.parameters ?? []) as Parameter[]
    const projectIdParam = parameters.find((p: Parameter) => p.name === 'project_id')
    if (projectIdParam?.value && !projectNameCache.value) {
      await fetchProjectName(projectIdParam.value)
    }
  }
})

// Watch for project reference parameter changes
watch(
  () => data.value.parameters,
  async (params: Parameter[] | undefined) => {
    if (isProjectReference.value) {
      const projectIdParam = params?.find((p: Parameter) => p.name === 'project_id')
      if (projectIdParam?.value && !projectNameCache.value) {
        await fetchProjectName(projectIdParam.value)
      }
    }
  },
  { immediate: true }
)
</script>

<template>
  <div class="special-node" :class="{ 'worker-node': isWorker }">
    <!-- Left/Right handles - only show in overview mode for components -->
    <Handle
      v-if="showLeftRightHandles"
      id="left"
      type="target"
      :position="Position.Left"
      class="handle horizontal-handle"
      :is-valid-connection="isValidConnection"
    />
    <Handle
      v-if="showLeftRightHandles"
      id="right"
      type="source"
      :position="Position.Right"
      class="handle horizontal-handle"
      :is-valid-connection="isValidConnection"
    />

    <!-- Top handle - for workers and children when zoomed in -->
    <Handle
      v-if="showTopHandle"
      id="top"
      type="target"
      :position="Position.Top"
      class="handle vertical-handle"
      :is-valid-connection="isValidConnection"
    />

    <!-- Bottom handle - for active parent when zoomed in, workers with children, and last children -->
    <Handle
      v-if="showBottomHandle"
      id="bottom"
      type="source"
      :position="Position.Bottom"
      class="handle vertical-handle"
      :is-valid-connection="isValidConnection"
    />

    <VCard
      :elevation="1"
      color="surface"
      class="node-card"
      :class="{
        'worker-card': isWorker,
        'node-card--running': executionState === 'running',
        'node-card--completed': executionState === 'completed',
        'node-card--failed': executionState === 'failed',
      }"
    >
      <div class="node-content">
        <div class="node-icon-wrapper">
          <Icon v-if="isProviderLogo(data.icon)" :icon="data.icon" :width="20" :height="20" />
          <VIcon
            v-else
            :icon="data.icon || (isWorker ? 'tabler-tools' : 'tabler-user-bolt')"
            size="20"
            color="primary"
            class="flex-shrink-0"
          />
        </div>
        <div class="node-details" :class="{ 'worker-details': isWorker }">
          <div class="node-details-content">
            <div class="node-title text-body-2 font-weight-bold">
              {{ getDisplayName }}
            </div>
          </div>
          <VIcon
            v-if="isDeletable && props.isDraftMode && ability.can('update', 'Project')"
            icon="tabler-circle-x"
            size="18"
            color="white"
            class="delete-icon cursor-pointer"
            @click.stop="handleDeleteRequest"
          />
        </div>
      </div>
    </VCard>

    <!-- Add Tool Button - much more subtle styling -->
    <button
      v-if="showAddToolButton"
      class="add-tool-btn"
      :class="{ 'add-tool-btn--expanded': isZoomedIn }"
      :title="isZoomedIn ? 'Add Tool' : 'Add'"
      @click="handleAddTool"
    >
      <VIcon icon="tabler-plus" :size="isZoomedIn ? 12 : 10" color="grey-darken-1" />
      <span class="add-tool-text">Add Tool</span>
    </button>

    <!-- Delete confirmation dialog -->
    <VDialog v-model="showDeleteConfirmation" max-width="var(--dnr-dialog-sm)">
      <VCard>
        <VCardTitle class="text-h6">Confirm Delete</VCardTitle>
        <VCardText>
          Are you sure you want to delete this {{ isWorker ? 'worker' : 'component' }}? This action cannot be undone.
        </VCardText>
        <VCardActions>
          <VSpacer></VSpacer>
          <VBtn color="grey" @click="cancelDelete">Cancel</VBtn>
          <VBtn color="error" @click="confirmDelete">Delete</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>
  </div>
</template>

<style lang="scss" scoped>
.special-node {
  position: relative;
  background: transparent;
  max-inline-size: 240px;
  min-inline-size: 220px;
}

.worker-node {
  max-inline-size: 220px;
  min-inline-size: 200px;
}

.node-card {
  overflow: hidden;
  border-radius: 16px;
  border: 1px solid rgba(var(--v-theme-primary), 0.16);
  padding: 0;
  background: transparent;
}

.worker-card {
  border-color: rgba(var(--v-theme-secondary), 0.16);
}

.node-content {
  display: flex;
  align-items: stretch;
  background: transparent;
}

.node-icon-wrapper {
  flex: 0 0 33%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #fff;
  padding: 12px;
}

.node-details {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  padding-block: 12px;
  padding-inline: 16px;
  background: rgb(var(--v-theme-primary));
  color: #fff;
}

.node-details.worker-details {
  background: rgb(var(--v-theme-secondary));
}

.node-details-content {
  flex: 1;
  min-inline-size: 0;
  text-align: center;
}

.node-title {
  display: -webkit-box;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  line-height: 1.2;
  text-overflow: ellipsis;
  white-space: normal;
  word-break: break-word;
  color: #fff;
  font-weight: 700;
}

.delete-icon {
  position: absolute;
  inset-inline-end: 8px;
  inset-block-start: 8px;
  transform: none;
  flex-shrink: 0;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.2s ease;

  &:hover {
    opacity: 1;
  }
}

.node-details:hover .delete-icon {
  opacity: 1;
  pointer-events: auto;
}

.add-tool-btn {
  position: absolute;
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid rgba(var(--v-border-color), 0.3);
  border-radius: 12px;
  backdrop-filter: blur(4px);
  background: rgba(var(--v-theme-surface), 0.9);
  cursor: pointer;
  font-size: 0.7rem;
  gap: 4px;
  inset-block-end: -15px;
  inset-inline-start: 50%;
  padding-block: 2px;
  padding-inline: 6px;
  transform: translateX(-50%);
  transition: all 0.2s ease;
  user-select: none;

  &:hover {
    border-color: rgba(var(--v-border-color), 0.5);
    background: rgba(var(--v-theme-surface), 1);
    box-shadow: 0 2px 6px rgba(0, 0, 0, 10%);
    opacity: 1;
    transform: translateX(-50%) translateY(-1px);
  }

  // Expanded styling for zoomed in (with text)
  &--expanded {
    inset-block-end: -18px;
    padding-block: 4px;
    padding-inline: 8px;

    .add-tool-text {
      color: rgba(var(--v-theme-on-surface), 0.7);
      font-size: 0.65rem;
      font-weight: 400;
      white-space: nowrap;
    }
  }
}

::v-deep .vue-flow__handle {
  position: absolute;
  border-radius: 50%;
  block-size: 10px;
  inline-size: 10px;
}

::v-deep .vue-flow__handle-left {
  background: rgb(var(--v-theme-primary));
  inset-block-start: 50%;
  inset-inline-start: -5px;
  transform: translateY(-50%);
}

::v-deep .vue-flow__handle-right {
  background: rgb(var(--v-theme-primary));
  inset-block-start: 50%;
  inset-inline-end: -5px;
  transform: translateY(-50%);
}

::v-deep .vue-flow__handle-bottom {
  background: rgb(var(--v-theme-primary));
  inset-block-end: -5px;
  inset-inline-start: 50%;
  transform: translateX(-50%);
}

::v-deep .vue-flow__handle-top {
  background: rgb(var(--v-theme-secondary));
  inset-block-start: -5px;
  inset-inline-start: 50%;
  transform: translateX(-50%);
}

.worker-node ::v-deep .vue-flow__handle-bottom {
  background: rgb(var(--v-theme-secondary));
}

.handle {
  border: 2px solid white;
  block-size: 12px;
  inline-size: 12px;
}

.horizontal-handle {
  background: rgb(var(--v-theme-primary));
}

.vertical-handle {
  background: rgb(var(--v-theme-secondary));
}

.node-card--running {
  border-color: rgb(var(--v-theme-primary));
  box-shadow: 0 0 12px rgba(var(--v-theme-primary), 0.4);
  animation: execution-pulse 1.5s ease-in-out infinite;
}

.node-card--completed {
  border-color: rgb(var(--v-theme-success));
  box-shadow: 0 0 10px rgba(var(--v-theme-success), 0.35);
  transition:
    border-color 0.3s ease,
    box-shadow 0.3s ease;
}

.node-card--failed {
  border-color: rgb(var(--v-theme-error));
  box-shadow: 0 0 10px rgba(var(--v-theme-error), 0.35);
  transition:
    border-color 0.3s ease,
    box-shadow 0.3s ease;
}

@keyframes execution-pulse {
  0%,
  100% {
    box-shadow: 0 0 8px rgba(var(--v-theme-primary), 0.25);
  }

  50% {
    box-shadow: 0 0 18px rgba(var(--v-theme-primary), 0.55);
  }
}
</style>
