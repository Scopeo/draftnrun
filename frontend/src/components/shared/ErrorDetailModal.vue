<script setup lang="ts">
import { onUnmounted, ref } from 'vue'
import { logger } from '@/utils/logger'

interface Props {
  modelValue: boolean
  errors: string[]
  title?: string
}

const props = withDefaults(defineProps<Props>(), {
  title: 'Issue Details',
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
}>()

const copySuccess = ref(false)
let copySuccessTimeout: ReturnType<typeof setTimeout> | null = null

// Clean up timeout on unmount
onUnmounted(() => {
  if (copySuccessTimeout) clearTimeout(copySuccessTimeout)
})

const closeDialog = () => {
  emit('update:modelValue', false)
}

const showCopySuccess = () => {
  if (copySuccessTimeout) clearTimeout(copySuccessTimeout)
  copySuccess.value = true
  copySuccessTimeout = setTimeout(() => {
    copySuccess.value = false
  }, 2000)
}

const copyError = async (error: string) => {
  try {
    await navigator.clipboard.writeText(error)
    showCopySuccess()
  } catch (err) {
    logger.error('Failed to copy error', { error: err })
  }
}

const copyAllErrors = async () => {
  try {
    const allErrors = props.errors.join('\n\n')

    await navigator.clipboard.writeText(allErrors)
    showCopySuccess()
  } catch (err) {
    logger.error('Failed to copy errors', { error: err })
  }
}
</script>

<template>
  <VDialog
    :model-value="modelValue"
    max-width="var(--dnr-dialog-md)"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <VCard>
      <VCardTitle class="d-flex align-center justify-space-between pa-4">
        <div class="d-flex align-center gap-2">
          <VIcon icon="tabler-alert-triangle" color="warning" size="24" />
          <span class="text-h6">{{ title }}</span>
        </div>
        <VBtn icon variant="text" size="small" @click="closeDialog">
          <VIcon icon="tabler-x" />
        </VBtn>
      </VCardTitle>

      <VDivider />

      <VCardText class="pa-4">
        <div class="errors-list">
          <div v-for="(error, index) in errors" :key="index" class="error-item">
            <div class="error-content">
              <span class="error-text">{{ error }}</span>
            </div>
            <VBtn icon variant="text" size="x-small" color="default" class="copy-btn" @click="copyError(error)">
              <VIcon icon="tabler-copy" size="16" />
              <VTooltip activator="parent" location="top">Copy</VTooltip>
            </VBtn>
          </div>
        </div>
      </VCardText>

      <VDivider />

      <VCardActions class="pa-4 justify-space-between">
        <VBtn v-if="errors.length > 1" variant="outlined" size="small" @click="copyAllErrors">
          <VIcon icon="tabler-copy" size="16" class="me-1" />
          Copy All
        </VBtn>
        <VSpacer />
        <VBtn variant="tonal" @click="closeDialog">Close</VBtn>
      </VCardActions>
    </VCard>
  </VDialog>

  <!-- Copy success snackbar -->
  <VSnackbar v-model="copySuccess" :timeout="2000" color="success" location="bottom">
    <VIcon icon="tabler-check" class="me-2" />
    Copied to clipboard
  </VSnackbar>
</template>

<style lang="scss" scoped>
.errors-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.error-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 12px;
  background-color: rgba(var(--v-theme-warning), 0.08);
  border-radius: 8px;
  border-inline-start: 3px solid rgb(var(--v-theme-warning));
}

.error-content {
  flex: 1;
  min-width: 0;
}

.error-text {
  font-size: 13px;
  line-height: 1.5;
  color: rgba(var(--v-theme-on-surface), 0.87);
  word-break: break-word;
  white-space: pre-wrap;
}

.copy-btn {
  flex-shrink: 0;
  opacity: 0.6;
  transition: opacity 0.2s;

  &:hover {
    opacity: 1;
  }
}
</style>
