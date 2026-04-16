<script setup lang="ts">
// 1. Vue/core imports
import { computed } from 'vue'

// 2. Third-party libraries (none here)

// 3. Local components (none here)

// 4. Composables (none here)

// 5. Utils/helpers (none here)

// 6. Types (none here)

// Props & Emits
interface Props {
  modelValue: boolean
  title: string
  isError: boolean
  text: string
  data: Record<string, unknown> | null
}

const props = defineProps<Props>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
}>()

const formattedJson = computed(() => {
  if (!props.data) return ''
  try {
    return JSON.stringify(props.data, null, 2)
  } catch (error: unknown) {
    return String(props.data)
  }
})

const close = () => {
  emit('update:modelValue', false)
}
</script>

<template>
  <VDialog
    :model-value="modelValue"
    max-width="70vw"
    @update:model-value="emit('update:modelValue', $event)"
    @click:outside="close"
    @keydown.esc="close"
  >
    <VCard style="max-block-size: 90vh">
      <VCardTitle class="d-flex align-center">
        <VIcon
          :icon="isError ? 'tabler-alert-circle' : 'tabler-file-text'"
          :color="isError ? 'error' : undefined"
          class="me-2"
        />
        {{ isError ? 'Evaluation Error' : 'Justification' }} - {{ title }}
      </VCardTitle>
      <VDivider />
      <VCardText style="overflow: auto; max-block-size: 82vh">
        <div class="evaluation-dialog-content">
          <VAlert v-if="isError" type="error" variant="tonal" class="mb-2">
            <strong>Error Details:</strong>
            <div class="mt-2">{{ text }}</div>
          </VAlert>
          <pre v-else-if="data" class="json-content">{{ formattedJson }}</pre>
          <pre v-else class="text-pre-wrap">{{ text }}</pre>
        </div>
      </VCardText>
      <VCardActions>
        <VSpacer />
        <VBtn variant="text" @click="close"> Close </VBtn>
      </VCardActions>
    </VCard>
  </VDialog>
</template>

<style lang="scss" scoped>
.evaluation-dialog-content {
  overflow: auto;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace;
  font-size: 0.9rem;
  line-height: 1.5;
  max-block-size: 60vh;
}

.evaluation-dialog-content pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  word-wrap: break-word;
}

.evaluation-dialog-content pre.json-content {
  overflow-x: auto;
  white-space: pre;
}
</style>
