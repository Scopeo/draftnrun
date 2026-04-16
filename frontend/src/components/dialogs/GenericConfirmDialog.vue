<script setup lang="ts">
import { computed } from 'vue'

interface Props {
  isDialogVisible: boolean
  title?: string
  message: string // Main confirmation message/question
  confirmText?: string
  cancelText?: string
  confirmColor?: string
  loading?: boolean
}

interface Emit {
  (e: 'update:isDialogVisible', value: boolean): void
  (e: 'confirm'): void
  (e: 'cancel'): void
}

const props = withDefaults(defineProps<Props>(), {
  title: 'Confirm Action', // Default title
  confirmText: 'Confirm', // Default confirm button text
  cancelText: 'Cancel', // Default cancel button text
  confirmColor: 'primary', // Default confirm button color
  loading: false, // Default loading state
})

const emit = defineEmits<Emit>()

const plainMessage = computed(() => {
  return props.message
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/<\/li>/gi, '\n')
    .replace(/<li[^>]*>/gi, '- ')
    .replace(/<[^>]*>/g, '')
    .trim()
})

const updateModelValue = (val: boolean) => {
  emit('update:isDialogVisible', val)
}

const onConfirm = () => {
  if (props.loading) return // Prevent confirming while loading
  emit('confirm')
  updateModelValue(false) // Close dialog on confirm
}

const onCancel = () => {
  if (props.loading) return // Prevent closing while loading
  emit('cancel')
  updateModelValue(false) // Close dialog on cancel
}
</script>

<template>
  <VDialog
    :model-value="props.isDialogVisible"
    max-width="var(--dnr-dialog-md)"
    persistent
    @update:model-value="updateModelValue"
  >
    <VCard>
      <VCardTitle class="text-h6">
        {{ props.title }}
      </VCardTitle>

      <VCardText class="pb-0">
        <div v-if="props.loading" class="d-flex align-center justify-center pa-4">
          <VProgressCircular indeterminate color="primary" size="24" class="me-3" />
          <span>Checking source usage...</span>
        </div>
        <span v-else class="confirm-message">{{ plainMessage }}</span>
      </VCardText>

      <VCardActions class="pa-4">
        <VSpacer />
        <VBtn variant="text" :disabled="props.loading" @click="onCancel">
          {{ props.cancelText }}
        </VBtn>
        <VBtn
          :color="props.confirmColor"
          variant="flat"
          :disabled="props.loading"
          :loading="props.loading"
          @click="onConfirm"
        >
          {{ props.confirmText }}
        </VBtn>
      </VCardActions>
    </VCard>
  </VDialog>
</template>

<style scoped>
.confirm-message {
  white-space: pre-line;
}
</style>
