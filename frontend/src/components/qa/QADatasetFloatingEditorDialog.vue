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
  value: string
  field: 'input' | 'groundtruth' | `custom-${string}` | ''
}

const props = defineProps<Props>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  'update:value': [value: string]
  blur: []
}>()

const fieldTitle = computed(() => {
  if (props.field === 'input') return 'Input'
  if (props.field === 'groundtruth') return 'Expected Output'
  return ''
})

const close = () => {
  emit('blur')
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
        <VIcon icon="tabler-edit" class="me-2" />
        {{ fieldTitle }}
      </VCardTitle>
      <VDivider />
      <VCardText style="overflow: auto; max-block-size: 82vh">
        <VTextarea
          :model-value="value"
          variant="outlined"
          rows="20"
          class="floating-editor-textarea"
          @update:model-value="emit('update:value', $event)"
          @blur="close"
        />
      </VCardText>
      <VCardActions>
        <VSpacer />
        <VBtn variant="text" @click="close"> Close </VBtn>
      </VCardActions>
    </VCard>
  </VDialog>
</template>

<style lang="scss" scoped>
.floating-editor-textarea {
  max-block-size: 56vh;
}
</style>
