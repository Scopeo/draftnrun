<script setup lang="ts">
// 1. Vue/core imports
import { ref, watch } from 'vue'

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
  create: [name: string]
}>()

// Local state
const columnName = ref('')

// Methods
const handleCreate = () => {
  if (!columnName.value.trim()) return
  emit('create', columnName.value.trim())
  columnName.value = ''
}

const handleClose = () => {
  emit('update:modelValue', false)
  columnName.value = ''
}

// Reset on open
watch(
  () => props.modelValue,
  isOpen => {
    if (isOpen) {
      columnName.value = ''
    }
  }
)
</script>

<template>
  <VDialog
    :model-value="modelValue"
    max-width="var(--dnr-dialog-sm)"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <VCard>
      <VCardTitle>Create Custom Column</VCardTitle>
      <VCardText>
        <VTextField
          v-model="columnName"
          label="Column Name"
          variant="outlined"
          :rules="[v => !!v || 'Name is required']"
          validate-on="blur"
          autofocus
          @keyup.enter="handleCreate"
        />
      </VCardText>
      <VCardActions>
        <VSpacer />
        <VBtn variant="text" @click="handleClose"> Cancel </VBtn>
        <VBtn color="primary" :loading="loading" :disabled="!columnName.trim()" @click="handleCreate"> Create </VBtn>
      </VCardActions>
    </VCard>
  </VDialog>
</template>
