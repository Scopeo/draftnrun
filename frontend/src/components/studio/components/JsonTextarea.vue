<script setup lang="ts">
import { computed, ref, useAttrs, watch } from 'vue'
import FieldExpressionInput from '../inputs/FieldExpressionInput.vue'
import type { ComponentDefinition, GraphEdge, GraphNodeData } from '@/types/fieldExpressions'

defineOptions({ inheritAttrs: false })

const props = withDefaults(defineProps<Props>(), {
  modelValue: null,
  readonly: false,
  label: '',
  graphNodes: () => [],
  graphEdges: () => [],
  currentNodeId: undefined,
  componentDefinitions: () => [],
  enableAutocomplete: false,
  targetInstanceId: undefined,
})

const emit = defineEmits<{
  'update:modelValue': [value: string | Record<string, any> | null]
}>()

interface Props {
  modelValue?: string | Record<string, any> | null
  readonly?: boolean
  label?: string
  graphNodes?: GraphNodeData[]
  graphEdges?: GraphEdge[]
  currentNodeId?: string
  componentDefinitions?: ComponentDefinition[]
  enableAutocomplete?: boolean
  targetInstanceId?: string
}

const attrs = useAttrs()

const restAttrs = computed(() => {
  const { class: _, ...rest } = attrs
  return rest
})

const displayText = ref('')
const isInternalUpdate = ref(false)

function toDisplayText(value: string | Record<string, any> | null): string {
  if (value == null) return ''
  if (typeof value === 'string') return value
  try {
    return JSON.stringify(value, null, 2)
  } catch (error: unknown) {
    return ''
  }
}

function handleTextUpdate(value: string) {
  displayText.value = value
  isInternalUpdate.value = true
  emit('update:modelValue', value)
}

watch(
  () => props.modelValue,
  newVal => {
    if (isInternalUpdate.value) {
      isInternalUpdate.value = false
      return
    }
    displayText.value = toDisplayText(newVal)
  },
  { immediate: true }
)
</script>

<template>
  <div class="json-textarea-wrapper" :class="[attrs.class]">
    <FieldExpressionInput
      v-bind="restAttrs"
      :model-value="displayText"
      :label="label"
      :is-textarea="true"
      :graph-nodes="graphNodes"
      :graph-edges="graphEdges"
      :current-node-id="currentNodeId"
      :component-definitions="componentDefinitions"
      :readonly="readonly"
      :enable-autocomplete="enableAutocomplete"
      :target-instance-id="targetInstanceId"
      @update:model-value="handleTextUpdate"
    />
  </div>
</template>

<style scoped>
.json-textarea-wrapper {
  position: relative;
}
</style>
