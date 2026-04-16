<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { CreditFields } from '@/types/credits'
import { CREDIT_FIELD_LABELS, CREDIT_FIELD_TOOLTIPS } from '@/types/credits'
import { CREDIT_FIELD_CONFIG } from '@/utils/credits'

interface Props {
  modelValue: CreditFields
  disabled?: boolean
  variant?: 'outlined' | 'filled' | 'underlined' | 'plain' | 'solo' | 'solo-inverted' | 'solo-filled'
  density?: 'default' | 'comfortable' | 'compact'
}

const props = withDefaults(defineProps<Props>(), {
  disabled: false,
  variant: 'outlined',
  density: 'default',
})

const emit = defineEmits<{
  'update:modelValue': [value: CreditFields]
}>()

const creditFields = computed({
  get: () => props.modelValue,
  set: value => emit('update:modelValue', value),
})

// Handle credits_per as dict
const unitDictEntries = ref<Array<{ id: number; key: string; value: number | null }>>([])
const isUpdatingFromProps = ref(false)
const isInitialized = ref(false)
let nextEntryId = 0

// Initialize unit dict entries from modelValue
watch(
  () => props.modelValue.credits_per,
  newDict => {
    if (isUpdatingFromProps.value) return

    if (newDict && Object.keys(newDict).length > 0) {
      const newEntries = Object.entries(newDict).map(([key, value]) => ({
        id: nextEntryId++,
        key,
        value: typeof value === 'number' ? value : null,
      }))

      // Only update if different to avoid loops
      const currentStr = JSON.stringify(unitDictEntries.value.map(e => ({ k: e.key, v: e.value })))
      const newStr = JSON.stringify(newEntries.map(e => ({ k: e.key, v: e.value })))
      if (currentStr !== newStr) {
        unitDictEntries.value = newEntries
        isInitialized.value = true
      }
    } else if (newDict === null && isInitialized.value) {
      // If dict is null and we're already initialized, user deleted everything
      // Keep array empty - don't auto-add an entry
      unitDictEntries.value = []
    } else if (!isInitialized.value && !newDict) {
      // Only add empty entry on first initialization if there's no existing data
      unitDictEntries.value = [{ id: nextEntryId++, key: '', value: null }]
      isInitialized.value = true
    }
  },
  { immediate: true, deep: true }
)

// Update credits_per when dict entries change
watch(
  unitDictEntries,
  entries => {
    isUpdatingFromProps.value = true

    const dict: Record<string, number> = {}

    entries.forEach(({ key, value }) => {
      if (key.trim() && value !== null && value !== undefined) {
        dict[key.trim()] = value
      }
    })

    const newDict = Object.keys(dict).length > 0 ? dict : null

    // Only emit if changed to avoid loops
    const currentDict = props.modelValue.credits_per
    const dictsEqual = JSON.stringify(currentDict) === JSON.stringify(newDict)
    if (!dictsEqual) {
      creditFields.value = {
        ...creditFields.value,
        credits_per: newDict,
      }
    }
    isUpdatingFromProps.value = false
  },
  { deep: true }
)

const addUnitEntry = () => {
  unitDictEntries.value.push({ id: nextEntryId++, key: '', value: null })
}

const removeUnitEntry = (id: number) => {
  const index = unitDictEntries.value.findIndex(entry => entry.id === id)
  if (index !== -1) {
    unitDictEntries.value.splice(index, 1)
    // If all entries are deleted, set to empty array - the watch will handle setting credits_per to null
    if (unitDictEntries.value.length === 0) {
      unitDictEntries.value = []
    }
  }
}
</script>

<template>
  <div class="d-flex flex-column gap-3">
    <!-- Credits per Call -->
    <VTextField
      v-model.number="creditFields.credits_per_call"
      type="number"
      :step="CREDIT_FIELD_CONFIG.STEP"
      :min="CREDIT_FIELD_CONFIG.MIN"
      :variant="variant"
      :density="density"
      :disabled="disabled"
    >
      <template #label>
        <VTooltip location="top">
          <template #activator="{ props: tooltipProps }">
            <span v-bind="tooltipProps" class="credit-label-with-tooltip">{{
              CREDIT_FIELD_LABELS.credits_per_call
            }}</span>
          </template>
          <span>{{ CREDIT_FIELD_TOOLTIPS.credits_per_call }}</span>
        </VTooltip>
      </template>
    </VTextField>

    <!-- Credits per (Dict) -->
    <div>
      <VTooltip location="top">
        <template #activator="{ props: tooltipProps }">
          <div v-bind="tooltipProps" class="text-caption mb-2 d-flex align-center">
            <span class="credit-label-with-tooltip">{{ CREDIT_FIELD_LABELS.credits_per }}</span>
            <VIcon icon="tabler-info-circle" size="14" class="ms-1" />
          </div>
        </template>
        <span>{{ CREDIT_FIELD_TOOLTIPS.credits_per }}</span>
      </VTooltip>

      <div class="d-flex flex-column gap-2">
        <div v-for="entry in unitDictEntries" :key="entry.id" class="d-flex gap-2 align-center">
          <VTextField
            v-model="entry.key"
            label="Key"
            :variant="variant"
            :density="density"
            :disabled="disabled"
            class="flex-grow-1"
            placeholder="Unit name"
          />
          <VTextField
            v-model.number="entry.value"
            type="number"
            label="Value"
            :step="CREDIT_FIELD_CONFIG.STEP"
            :min="CREDIT_FIELD_CONFIG.MIN"
            :variant="variant"
            :density="density"
            :disabled="disabled"
            class="flex-grow-1"
            placeholder="Credits"
          />
          <VBtn
            icon="tabler-trash"
            size="small"
            variant="text"
            color="error"
            :disabled="disabled"
            @click.stop="removeUnitEntry(entry.id)"
          />
        </div>
        <VBtn
          prepend-icon="tabler-plus"
          size="small"
          variant="outlined"
          color="primary"
          :disabled="disabled"
          block
          @click="addUnitEntry"
        >
          Add
        </VBtn>
      </div>
    </div>
  </div>
</template>

<style scoped>
.credit-label-with-tooltip {
  cursor: help;
  pointer-events: auto;
}
</style>
