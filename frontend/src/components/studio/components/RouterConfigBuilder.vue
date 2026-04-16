<script setup lang="ts">
import { toRef } from 'vue'
import FieldExpressionInput from '../inputs/FieldExpressionInput.vue'
import type { ComponentDefinition, GraphEdge, GraphNodeData } from '@/types/fieldExpressions'
import { useCollectionWithIds } from '@/composables/useCollectionWithIds'
import { getRouteLabel } from '@/utils/routeHelpers'
import type { Route } from '@/types/router'

interface Props {
  modelValue?: Route[]
  readonly?: boolean
  color?: string
  graphNodes: GraphNodeData[]
  graphEdges?: GraphEdge[]
  currentNodeId?: string
  componentDefinitions?: ComponentDefinition[]
  targetInstanceId?: string
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: () => [],
  readonly: false,
  color: 'info',
})

const emit = defineEmits<{
  'update:modelValue': [value: Route[]]
}>()

// Track the next available route order number
const nextRouteOrder = ref(0)

// Use composable for collection management
const {
  items: localRoutes,
  add: addRouteInternal,
  remove,
  update,
} = useCollectionWithIds<Route>({
  modelValue: toRef(props, 'modelValue'),
  createDefault: () => {
    const order = nextRouteOrder.value++
    return {
      value_a: '',
      operator: 'equals',
      value_b: '',
      routeOrder: order,
    }
  },
  onChange: routes => emit('update:modelValue', routes),
})

// Initialize nextRouteOrder and migrate existing routes
watch(
  localRoutes,
  routes => {
    // Migrate routes without routeOrder
    let needsEmit = false
    routes.forEach((route, index) => {
      if (route.routeOrder === undefined || route.routeOrder === null) {
        route.routeOrder = index
        needsEmit = true
      }
    })

    if (routes.length > 0) {
      const maxOrder = Math.max(...routes.map(r => r.routeOrder ?? 0))

      nextRouteOrder.value = maxOrder + 1
    }

    // Emit changes if we migrated any routes
    if (needsEmit) {
      emit(
        'update:modelValue',
        routes.map(r => ({ ...r }))
      )
    }
  },
  { immediate: true, deep: true }
)

// Wrapper to assign routeOrder when adding
const addRoute = () => {
  addRouteInternal()
}

// Remove route by index
const removeRoute = (index: number) => {
  const route = localRoutes.value[index]
  if (route) {
    remove(route._id)
  }
}

// Update route field (value_a or value_b)
const updateRouteField = (index: number, field: 'value_a' | 'value_b', value: string) => {
  const route = localRoutes.value[index]
  if (route) {
    update(route._id, field, value)
  }
}
</script>

<template>
  <div class="router-config-builder">
    <!-- Add Route Button -->
    <VBtn
      v-if="!readonly"
      :color="color"
      variant="tonal"
      size="small"
      prepend-icon="tabler-plus"
      class="mb-4"
      @click="addRoute"
    >
      Add Route
    </VBtn>

    <!-- Routes List -->
    <div v-if="localRoutes.length > 0" class="routes-list">
      <VCard
        v-for="(route, index) in localRoutes"
        :key="route._id"
        variant="outlined"
        class="mb-3 route-card"
        data-route-card
      >
        <VCardText class="py-2">
          <!-- Single Line: Route Label + Input Field = Value + Delete -->
          <div class="d-flex align-center gap-2">
            <!-- Route Label (compact) -->
            <div class="d-flex align-center gap-1 flex-shrink-0">
              <VIcon icon="tabler-route" size="14" :color="color" />
              <span class="text-caption font-weight-medium route-label">{{ getRouteLabel(index) }}</span>
            </div>

            <!-- Input Field (value_a) - compact -->
            <div class="route-field">
              <FieldExpressionInput
                :model-value="route.value_a || ''"
                placeholder="Field..."
                :graph-nodes="graphNodes"
                :graph-edges="graphEdges"
                :current-node-id="currentNodeId"
                :component-definitions="componentDefinitions"
                :readonly="readonly"
                :is-textarea="false"
                :enable-autocomplete="true"
                :target-instance-id="targetInstanceId"
                density="compact"
                hide-details
                @update:model-value="(value: string) => updateRouteField(index, 'value_a', value)"
              />
            </div>

            <!-- Equals Sign -->
            <span class="text-caption text-medium-emphasis flex-shrink-0">=</span>

            <!-- Value (value_b) - compact -->
            <div class="route-field">
              <FieldExpressionInput
                :model-value="route.value_b || ''"
                placeholder="Value..."
                :graph-nodes="graphNodes"
                :graph-edges="graphEdges"
                :current-node-id="currentNodeId"
                :component-definitions="componentDefinitions"
                :readonly="readonly"
                :is-textarea="false"
                :enable-autocomplete="true"
                :target-instance-id="targetInstanceId"
                density="compact"
                hide-details
                @update:model-value="(value: string) => updateRouteField(index, 'value_b', value)"
              />
            </div>

            <!-- Delete Button (compact) -->
            <VBtn
              v-if="!readonly"
              color="error"
              variant="text"
              size="x-small"
              icon="tabler-trash"
              class="flex-shrink-0"
              @click="removeRoute(index)"
            />
          </div>
        </VCardText>
      </VCard>
    </div>

    <!-- Empty State -->
    <EmptyState
      v-else
      icon="tabler-git-branch"
      title="No routes configured"
      description='Click "Add Route" to create output paths for your router'
      size="sm"
    />

    <!-- Info Box -->
    <VAlert v-if="localRoutes.length > 0" type="info" variant="tonal" class="mt-4" density="compact">
      <div class="text-caption">
        <strong>{{ localRoutes.length }}</strong> route{{ localRoutes.length !== 1 ? 's' : '' }} configured. Each route
        creates an output port that can connect to different components.
      </div>
    </VAlert>
  </div>
</template>

<style lang="scss" scoped>
.router-config-builder {
  .routes-list {
    .route-card {
      border-inline-start: 3px solid rgb(var(--v-theme-info));
      transition: all 0.2s ease;

      &:hover {
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
      }
    }

    .route-value-input {
      margin-block-start: 8px;
    }
  }

  .route-label {
    min-width: 48px;
  }

  .route-field {
    flex: 1;
    min-width: 120px;
  }
}
</style>
