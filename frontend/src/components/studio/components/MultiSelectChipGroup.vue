<script setup lang="ts">
import { computed } from 'vue'
import { VCheckbox } from 'vuetify/components/VCheckbox'

const props = withDefaults(
  defineProps<{
    modelValue?: string[]
    items: string[]
    label?: string
    disabled?: boolean
  }>(),
  { modelValue: () => [] }
)

const emit = defineEmits<{
  'update:modelValue': [value: string[]]
}>()

const allSelected = computed(
  () => props.items.length > 0 && props.items.every(item => (props.modelValue ?? []).includes(item))
)

function toggleAll() {
  if (!props.disabled) emit('update:modelValue', allSelected.value ? [] : [...props.items])
}

function toggle(item: string) {
  if (props.disabled) return
  const current = [...props.modelValue]
  const idx = current.indexOf(item)
  if (idx >= 0) current.splice(idx, 1)
  else current.push(item)
  emit('update:modelValue', current)
}
</script>

<template>
  <div class="multiselect-grid">
    <div v-if="label" class="text-body-2 mb-2">
      {{ label }}
    </div>

    <div class="grid-container">
      <VCheckbox
        v-for="item in items"
        :key="item"
        :model-value="(modelValue ?? []).includes(item)"
        :label="item"
        :disabled="disabled"
        density="compact"
        hide-details
        class="grid-item"
        @update:model-value="toggle(item)"
      />
    </div>

    <div class="d-flex justify-end mt-1">
      <span
        class="text-caption toggle-all-link"
        :class="disabled ? 'text-disabled' : 'text-primary'"
        @click="toggleAll"
      >
        {{ allSelected ? 'Clear all' : 'Select all' }}
      </span>
    </div>
  </div>
</template>

<style scoped>
.multiselect-grid {
  width: 100%;
}

.grid-container {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 2px 12px;
}

.toggle-all-link {
  cursor: pointer;
  user-select: none;
}

.toggle-all-link:hover:not(.text-disabled) {
  text-decoration: underline;
}
</style>
