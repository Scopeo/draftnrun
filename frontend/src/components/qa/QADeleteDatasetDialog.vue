<script setup lang="ts">
// 1. Vue/core imports
import { computed, ref, watch } from 'vue'

// 2. Third-party libraries (none here)

// 3. Local components (none here)

// 4. Composables (none here)

// 5. Utils/helpers (none here)

// 6. Types (none here)

// Props & Emits
interface Props {
  modelValue: boolean
  datasetName?: string
  loading?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  datasetName: '',
  loading: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  confirm: []
}>()

// Local state
const confirmInput = ref('')

// Computed
const canConfirm = computed(() => {
  return confirmInput.value.trim() === props.datasetName.trim()
})

// Methods
const handleClose = () => {
  emit('update:modelValue', false)
  confirmInput.value = ''
}

const handleConfirm = () => {
  if (!canConfirm.value) return
  emit('confirm')
}

// Reset on open
watch(
  () => props.modelValue,
  isOpen => {
    if (isOpen) {
      confirmInput.value = ''
    }
  }
)
</script>

<template>
  <VDialog
    :model-value="modelValue"
    max-width="var(--dnr-dialog-md)"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <VCard>
      <VCardTitle class="d-flex align-center">
        <VIcon icon="tabler-alert-triangle" color="warning" class="me-2" />
        Confirm Delete Dataset
      </VCardTitle>
      <VDivider />
      <VCardText>
        <div class="mb-4">
          You are about to permanently delete dataset <strong>{{ datasetName }}</strong
          >. This action cannot be undone.
        </div>
        <VAlert type="warning" variant="tonal" class="mb-4"> Please type the dataset name exactly to confirm. </VAlert>
        <VTextField v-model="confirmInput" :label="`Type: ${datasetName || ''}`" :disabled="loading" autofocus />
      </VCardText>
      <VCardActions>
        <VSpacer />
        <VBtn variant="text" :disabled="loading" @click="handleClose"> Cancel </VBtn>
        <VBtn color="error" :loading="loading" :disabled="!canConfirm || loading" @click="handleConfirm"> Delete </VBtn>
      </VCardActions>
    </VCard>
  </VDialog>
</template>
