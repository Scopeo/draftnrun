<script setup lang="ts">
// 1. Vue/core imports (none needed - template only)

// 2. Third-party libraries (none here)

// 3. Local components (none here)

// 4. Composables (none here)

// 5. Utils/helpers (none here)

// 6. Types (none here)

// Props & Emits
interface Props {
  modelValue: boolean
  loading?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  loading: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  confirm: []
}>()

// Methods
const handleClose = () => {
  emit('update:modelValue', false)
}

const handleConfirm = () => {
  emit('confirm')
}
</script>

<template>
  <VDialog
    :model-value="modelValue"
    max-width="var(--dnr-dialog-sm)"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <VCard>
      <VCardTitle>Delete Test Case</VCardTitle>
      <VCardText> Are you sure you want to delete this test case? This action cannot be undone. </VCardText>
      <VCardActions>
        <VSpacer />
        <VBtn variant="text" :disabled="loading" @click="handleClose"> Cancel </VBtn>
        <VBtn color="error" :loading="loading" @click="handleConfirm"> Delete </VBtn>
      </VCardActions>
    </VCard>
  </VDialog>
</template>
