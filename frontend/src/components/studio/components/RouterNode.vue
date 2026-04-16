<script setup lang="ts">
import { useAbility } from '@casl/vue'
import type { NodeProps } from '@vue-flow/core'
import { Handle, Position, useVueFlow } from '@vue-flow/core'
import { computed, ref } from 'vue'
import { Icon } from '@iconify/vue'
import { isProviderLogo } from '../utils/node-factory.utils'
import { isValidRouterConnection } from '../utils/connectionValidation'
import type { Parameter } from '../types/node.types'
import { parseRoutes } from '@/utils/routeHelpers'
import { truncateString } from '@/utils/formatters'
import type { Route } from '@/types/router'

interface RouterNodeProps extends NodeProps {
  isDraftMode: boolean
  isZoomedIn?: boolean
  activeComponentId?: string | null
  executionState?: {
    activeRoute: number | null
    inputValue: any
  }
}

const props = defineProps<RouterNodeProps>()
const emit = defineEmits(['delete'])
const ability = useAbility()
const { edges } = useVueFlow()

const data = computed(() => props.data || {})
const canDelete = computed(() => props.isDraftMode)

// Show confirmation dialog for delete
const showDeleteConfirmation = ref(false)

const isDeletable = computed(() => {
  // Cannot delete if it's the Start component
  const startComponentId = import.meta.env.VITE_START_COMPONENT_ID
  if (props.data?.component_id === startComponentId) return false

  return true
})

// Get routes from parameters using utility
const routes = computed(() => {
  const parameters = (data.value.parameters ?? []) as Parameter[]
  const routesParam = parameters.find((p: Parameter) => p.name === 'routes')
  return parseRoutes(routesParam?.value)
})

// Determine if a route is active (for execution visualization)
const isRouteActive = (index: number): boolean => {
  return props.executionState?.activeRoute === index
}

// Get display value for a route condition - show the target value (value_b)
const getRouteDisplayValue = (route: Route | null | undefined): string => {
  if (!route) return 'Empty'

  // Show value_b (the target value to match)
  if (route.value_b !== undefined && route.value_b !== null && route.value_b !== '') {
    return truncateString(String(route.value_b))
  }

  return 'Empty'
}

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

// Get icon for the router component
const getComponentIcon = computed(() => {
  if (data.value.icon != null) {
    return data.value.icon
  }
  return 'tabler-route'
})

// Determine if this node is a child (has parent through top handle)
const isChild = computed(() => {
  return edges.value.some(
    edge => edge.target === props.id && edge.targetHandle === 'top' && edge.sourceHandle === 'bottom'
  )
})

// Show left/right handles - Router doesn't use these in zoomed mode
const showLeftRightHandles = computed(() => {
  return !props.isZoomedIn
})

// Route clicks no longer need special handling since router has single output
// Clicking anywhere on the router will open the edit sidebar
</script>

<template>
  <div class="router-node">
    <!-- Input handle (left) - always visible when not zoomed -->
    <Handle
      v-if="showLeftRightHandles"
      id="left"
      type="target"
      :position="Position.Left"
      class="handle input-handle"
      :is-valid-connection="isValidRouterConnection"
    />

    <VCard :elevation="1" color="surface" class="router-card">
      <!-- Header -->
      <div class="router-header">
        <div class="router-icon-wrapper">
          <Icon v-if="isProviderLogo(data.icon)" :icon="data.icon" :width="20" :height="20" />
          <VIcon v-else :icon="getComponentIcon" size="20" color="primary" class="flex-shrink-0" />
        </div>
        <div class="router-title-section">
          <div class="router-title text-body-2 font-weight-bold">
            {{ data.name || 'Router' }}
          </div>
          <VIcon
            v-if="isDeletable && props.isDraftMode && ability.can('update', 'Project')"
            icon="tabler-circle-x"
            size="18"
            color="white"
            class="delete-icon cursor-pointer"
            aria-label="Delete router"
            role="button"
            tabindex="0"
            @click.stop="handleDeleteRequest"
            @keydown.enter="handleDeleteRequest"
            @keydown.space.prevent="handleDeleteRequest"
          />
        </div>
      </div>

      <!-- Routes Section -->
      <div class="router-body">
        <div v-if="routes.length > 0" class="routes-list">
          <div v-for="(route, index) in routes" :key="route.routeOrder ?? index" class="route-item-wrapper">
            <div
              class="route-mini-block"
              :class="{
                'route-active': isRouteActive(index),
                'route-inactive': executionState && !isRouteActive(index),
              }"
            >
              <div class="route-value">{{ getRouteDisplayValue(route) }}</div>

              <!-- Output handle integrated into mini block -->
              <Handle
                v-if="showLeftRightHandles"
                :id="String(route.routeOrder ?? index)"
                type="source"
                :position="Position.Right"
                class="handle route-mini-handle"
                :class="{ 'route-handle-active': isRouteActive(index) }"
                :is-valid-connection="isValidRouterConnection"
              />
            </div>
          </div>
        </div>
        <div v-else class="empty-routes">
          <VIcon icon="tabler-route-off" size="24" class="text-disabled mb-1" />
          <div class="text-caption text-disabled">No routes configured</div>
        </div>
      </div>
    </VCard>

    <!-- Delete confirmation dialog -->
    <VDialog v-model="showDeleteConfirmation" max-width="var(--dnr-dialog-sm)">
      <VCard>
        <VCardTitle class="text-h6">Confirm Delete</VCardTitle>
        <VCardText> Are you sure you want to delete this Router component? This action cannot be undone. </VCardText>
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
.router-node {
  position: relative;
  background: transparent;
  max-inline-size: 240px;
  min-inline-size: 220px;
}

.router-card {
  overflow: hidden;
  border-radius: 16px;
  border: 1px solid rgba(var(--v-theme-primary), 0.16);
  padding: 0;
  background: transparent;
}

.router-header {
  display: flex;
  align-items: stretch;
  background: transparent;
  border-block-end: 1px solid rgba(var(--v-border-color), 0.2);
}

.router-icon-wrapper {
  flex: 0 0 33%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgb(var(--v-theme-surface));
  padding: 12px;
}

.router-title-section {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  padding-block: 12px;
  padding-inline: 16px;
  background: rgb(var(--v-theme-primary));
  color: rgb(var(--v-theme-on-primary));
}

.router-title {
  flex: 1;
  min-inline-size: 0;
  text-align: center;
  color: rgb(var(--v-theme-on-primary));
  font-weight: 700;
}

.delete-icon {
  position: absolute;
  inset-inline-end: 8px;
  inset-block-start: 8px;
  flex-shrink: 0;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.2s ease;

  &:hover {
    opacity: 1;
  }
}

.router-title-section:hover .delete-icon {
  opacity: 1;
  pointer-events: auto;
}

.router-body {
  padding: 10px;
  background: rgba(var(--v-theme-surface), 1);
  min-block-size: auto;
}

.routes-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.route-item-wrapper {
  position: relative;
}

.route-mini-block {
  position: relative;
  display: flex;
  align-items: center;
  padding: 10px 12px;
  padding-inline-end: 24px;
  background: rgba(var(--v-theme-surface-variant), 0.2);
  border: 1px solid rgba(var(--v-theme-outline), 0.3);
  border-radius: 8px;
  transition: all 0.2s ease;
}

.route-value {
  flex: 1;
  font-size: 0.8rem;
  font-weight: 500;
  color: rgba(var(--v-theme-on-surface), 0.87);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.route-inactive {
  opacity: 0.5;
}

.empty-routes {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 16px;
  text-align: center;
}

::v-deep .vue-flow__handle {
  position: absolute;
  border-radius: 50%;
  block-size: 8px;
  inline-size: 8px;
  border: none;
}

.handle {
  block-size: 8px;
  inline-size: 8px;
}

.input-handle {
  background: rgb(var(--v-theme-primary));
  inset-block-start: 50%;
  inset-inline-start: -6px;
  transform: translateY(-50%);
}

.route-mini-handle {
  position: absolute;
  background: rgb(var(--v-theme-primary));
  inset-inline-end: -4px;
  inset-block-start: 50%;
  transform: translateY(-50%);
  block-size: 8px;
  inline-size: 8px;
  border: none;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
  z-index: 10;

  &:hover {
    transform: translateY(-50%) scale(1.3);
    box-shadow: 0 3px 6px rgba(var(--v-theme-primary), 0.4);
  }
}

.route-handle-active .route-mini-handle {
  background: rgb(var(--v-theme-success));
  box-shadow: 0 0 12px rgba(var(--v-theme-success), 0.6);
}
</style>
