<script setup lang="ts">
import { computed } from 'vue'
import FieldExpressionInput from '../inputs/FieldExpressionInput.vue'
import type { Condition } from '@/types/conditions'
import { AVAILABLE_OPERATORS } from '@/types/conditions'
import type { ComponentDefinition, GraphEdge, GraphNodeData } from '@/types/fieldExpressions'
import { useCollectionWithIds } from '@/composables/useCollectionWithIds'

interface Props {
  modelValue?: Condition[]
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
  color: 'primary',
})

const emit = defineEmits<{
  'update:modelValue': [value: Condition[]]
}>()

// Use composable for collection management
const {
  items: localConditions,
  add: addCondition,
  remove,
  update,
} = useCollectionWithIds<Condition>({
  modelValue: toRef(props, 'modelValue'),
  createDefault: () => ({
    value_a: '',
    operator: '',
    value_b: '',
    logical_operator: 'AND',
  }),
  onChange: conditions => emit('update:modelValue', conditions),
})

// Operator items for dropdown
const operatorItems = computed(() => {
  return AVAILABLE_OPERATORS.map(op => ({
    title: op.label,
    value: op.value,
  }))
})

// Check if operator requires value_b
const requiresValueB = (operator: string): boolean => {
  const op = AVAILABLE_OPERATORS.find(o => o.value === operator)
  return op?.requires_value_b ?? true
}

// Remove condition by index
const removeCondition = (index: number) => {
  const condition = localConditions.value[index]
  if (condition) {
    remove(condition._id)
  }
}

// Update condition field
const updateCondition = (index: number, field: keyof Condition, value: string | 'AND' | 'OR') => {
  const condition = localConditions.value[index]
  if (condition) {
    update(condition._id, field, value)
  }
}

// Logical operator options
const logicalOperatorItems = [
  { title: 'AND', value: 'AND' },
  { title: 'OR', value: 'OR' },
]
</script>

<template>
  <div class="condition-builder">
    <!-- Add Condition Button -->
    <VBtn
      v-if="!readonly"
      :color="color"
      variant="tonal"
      size="small"
      prepend-icon="tabler-plus"
      class="mb-4"
      @click="addCondition"
    >
      Add Condition
    </VBtn>

    <!-- Conditions List -->
    <div v-if="localConditions.length > 0" class="conditions-list">
      <VCard
        v-for="(condition, index) in localConditions"
        :key="condition._id"
        variant="outlined"
        class="mb-3 condition-card"
      >
        <VCardText>
          <!-- Field, Operator, Value in one row -->
          <div class="d-flex gap-2 mb-3 align-end condition-row">
            <!-- Field -->
            <div class="flex-grow-1" style="flex-basis: 0">
              <FieldExpressionInput
                :model-value="condition.value_a || ''"
                label="Field"
                placeholder="@{{...}}"
                :graph-nodes="graphNodes"
                :graph-edges="graphEdges"
                :current-node-id="currentNodeId"
                :component-definitions="componentDefinitions"
                :readonly="readonly"
                :is-textarea="false"
                :enable-autocomplete="true"
                :target-instance-id="targetInstanceId"
                @update:model-value="(value: string) => updateCondition(index, 'value_a', value)"
              />
            </div>

            <!-- Operator (always in the middle, fixed width) -->
            <div style="width: 220px; flex-shrink: 0">
              <VSelect
                :model-value="condition.operator || ''"
                :items="operatorItems"
                label="Operator"
                variant="outlined"
                :color="color"
                item-title="title"
                item-value="value"
                :disabled="readonly"
                hide-details="auto"
                @update:model-value="(value: string) => updateCondition(index, 'operator', value)"
              />
            </div>

            <!-- Value (always present but disabled when not needed) -->
            <div class="flex-grow-1" style="flex-basis: 0">
              <FieldExpressionInput
                :model-value="condition.value_b || ''"
                label="Value"
                placeholder="value"
                :graph-nodes="graphNodes"
                :graph-edges="graphEdges"
                :current-node-id="currentNodeId"
                :component-definitions="componentDefinitions"
                :readonly="readonly || !condition.operator || !requiresValueB(condition.operator)"
                :is-textarea="false"
                :enable-autocomplete="true"
                :target-instance-id="targetInstanceId"
                @update:model-value="(value: string) => updateCondition(index, 'value_b', value)"
              />
            </div>
          </div>

          <!-- Logical Operator and Remove Button Row -->
          <div class="d-flex align-center justify-space-between">
            <!-- Logical Operator (if not last condition) -->
            <div v-if="index < localConditions.length - 1" style="min-width: 150px">
              <VSelect
                :model-value="condition.logical_operator || 'AND'"
                :items="logicalOperatorItems"
                label="Then"
                variant="outlined"
                :color="color"
                item-title="title"
                item-value="value"
                :disabled="readonly"
                hide-details="auto"
                density="compact"
                @update:model-value="(value: 'AND' | 'OR') => updateCondition(index, 'logical_operator', value)"
              />
            </div>
            <VSpacer v-else />

            <!-- Remove Button -->
            <VBtn
              v-if="!readonly"
              color="error"
              variant="text"
              size="small"
              icon="tabler-trash"
              @click="removeCondition(index)"
            />
          </div>
        </VCardText>
      </VCard>
    </div>

    <!-- Empty State -->
    <EmptyState
      v-else
      icon="tabler-filter"
      title="No conditions defined"
      description='Click "Add Condition" to create one.'
      size="sm"
    />
  </div>
</template>

<style lang="scss" scoped>
.condition-builder {
  .conditions-list {
    .condition-card {
      border-inline-start: 3px solid rgb(var(--v-theme-primary));
      transition: all 0.2s ease;

      &:hover {
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
      }
    }

    .condition-row {
      align-items: flex-start;
      gap: 0.5rem;
    }
  }
}
</style>
