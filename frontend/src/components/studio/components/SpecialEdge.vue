<script setup lang="ts">
import type { EdgeProps } from '@vue-flow/core'
import { BaseEdge, EdgeLabelRenderer, getBezierPath, getSmoothStepPath } from '@vue-flow/core'
import { logger } from '@/utils/logger'

const props = defineProps<
  EdgeProps & {
    isDraftMode?: boolean
    isRootLevel?: boolean
  }
>()

const emit = defineEmits<{
  delete: [edgeId: string]
}>()

// Reactive variables for delete confirmation
const showDeleteConfirmation = ref(false)

// Calculate the appropriate path based on edge type
const pathData = computed(() => {
  const pathOptions = {
    sourceX: props.sourceX,
    sourceY: props.sourceY,
    sourcePosition: props.sourcePosition,
    targetX: props.targetX,
    targetY: props.targetY,
    targetPosition: props.targetPosition,
  }

  if (props.type === 'smoothstep') {
    return getSmoothStepPath(pathOptions)
  } else {
    return getBezierPath({ ...pathOptions, curvature: 0.25 })
  }
})

const edgePath = computed(() => pathData.value[0])
const labelX = computed(() => pathData.value[1])
const labelY = computed(() => pathData.value[2])

const data = computed(() => props.data || {})

// Get edge color based on connection type and selection state
const edgeColor = computed(() => {
  if (props.selected && props.isRootLevel && props.isDraftMode) {
    return `rgb(var(--v-theme-info))` // Highlight selected edges in blue/info color
  }
  return `rgb(var(--v-theme-primary))`
})

// Determine if this is a component-to-component connection
const isComponentConnection = computed(() => {
  return props.sourceNode?.type === 'component' && props.targetNode?.type === 'component'
})

// Determine stroke width based on connection type and selection
const strokeWidth = computed(() => {
  const baseWidth = isComponentConnection.value ? 2.5 : 2
  if (props.selected && props.isRootLevel && props.isDraftMode) {
    return baseWidth + 1 // Make selected edges thicker
  }
  return baseWidth
})

// Show delete button only when edge is selected at root level in draft mode
const showDeleteButton = computed(() => {
  return props.selected && props.isRootLevel && props.isDraftMode
})

const handleDelete = (event: Event) => {
  event.stopPropagation()
  confirmDelete()
}

// Cancel delete operation
const cancelDelete = () => {
  showDeleteConfirmation.value = false
}

// Confirm delete operation
const confirmDelete = () => {
  showDeleteConfirmation.value = false
  emit('delete', props.id)
}

// Log for debugging
watch(
  () => props.selected,
  selected => {
    if (props.isRootLevel && props.isDraftMode) {
      logger.info(`Edge ${props.id} (${props.type}) selected`, selected, 'showDeleteButton:', showDeleteButton.value)
    }
  },
  { immediate: true }
)
</script>

<template>
  <BaseEdge
    :id="id"
    :path="edgePath"
    :style="{
      stroke: edgeColor,
      strokeWidth,
    }"
    :class="{
      'component-connection': isComponentConnection,
      'selectable-edge': isRootLevel && isDraftMode,
      'selected-edge': selected && isRootLevel && isDraftMode,
    }"
    :interaction-width="isRootLevel && isDraftMode ? 40 : 8"
  />

  <EdgeLabelRenderer>
    <div
      v-if="data.hello"
      :style="{
        position: 'absolute',
        transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
        pointerEvents: 'all',
      }"
      class="nodrag nopan"
    >
      <VChip size="small" color="primary" variant="flat">
        {{ data.hello }}
      </VChip>
    </div>

    <div
      v-if="showDeleteButton"
      :style="{
        position: 'absolute',
        transform: `translate(-50%, -50%) translate(${labelX}px,${labelY - 30}px)`,
        pointerEvents: 'all',
      }"
      class="nodrag nopan edge-delete-button"
    >
      <div class="edge-controls">
        <VBtn
          size="small"
          color="error"
          variant="elevated"
          icon="tabler-trash"
          class="delete-btn"
          @click="handleDelete"
        />
      </div>
    </div>
  </EdgeLabelRenderer>

  <VDialog v-model="showDeleteConfirmation" max-width="var(--dnr-dialog-sm)">
    <VCard>
      <VCardTitle class="text-h6">Confirm Delete</VCardTitle>
      <VCardText> Are you sure you want to delete this connection? This action cannot be undone. </VCardText>
      <VCardActions>
        <VSpacer></VSpacer>
        <VBtn color="grey" @click="cancelDelete">Cancel</VBtn>
        <VBtn color="error" @click="confirmDelete">Delete</VBtn>
      </VCardActions>
    </VCard>
  </VDialog>
</template>

<style scoped>
.special-edge-label {
  border: 1px solid rgb(var(--v-theme-primary));
  border-radius: 4px;
  background: rgb(var(--v-theme-surface));
  color: rgb(var(--v-theme-on-surface));
  font-size: 12px;
  padding-block: 4px;
  padding-inline: 8px;
}

/* Add styles for component connections */
.component-connection {
  stroke-dasharray: none; /* Solid line for component connections */
}

/* Selectable edge styles */
.selectable-edge {
  cursor: pointer;
}

.selected-edge {
  filter: drop-shadow(0 0 8px rgba(var(--v-theme-info), 0.8));
}

/* Delete button styles */
.edge-delete-button {
  z-index: 1000;
}

/* Edge controls styling */
.edge-controls {
  display: flex;
  align-items: center;
  gap: 4px;
}

.delete-btn {
  block-size: 24px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 20%) !important;
  inline-size: 24px;
  min-inline-size: 24px !important;
}

.delete-btn:hover {
  transform: scale(1.1);
  transition: transform 0.2s ease;
}

.vue-flow__edge.animated path {
  animation: dashdraw 0.5s linear infinite;
  stroke-dasharray: 5;
}

@keyframes dashdraw {
  from {
    stroke-dashoffset: 10;
  }
}
</style>
