<script setup lang="ts">
// 1. Vue/core imports
import { ref } from 'vue'

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
const datasetName = ref('')
const formRef = ref<{ validate: () => Promise<{ valid: boolean }>; resetValidation: () => void }>()

// Methods
const handleCreate = async () => {
  // Validate form if field is empty
  if (!datasetName.value.trim()) {
    await formRef.value?.validate()
    return
  }
  emit('create', datasetName.value.trim())
  datasetName.value = ''
}

const handleClose = () => {
  emit('update:modelValue', false)
  datasetName.value = ''
  formRef.value?.resetValidation()
}
</script>

<template>
  <VDialog
    :model-value="modelValue"
    max-width="var(--dnr-dialog-sm)"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <VCard>
      <VCardTitle>Create New QA Dataset</VCardTitle>
      <VCardText>
        <VForm ref="formRef" @submit.prevent="handleCreate">
          <VTextField
            v-model="datasetName"
            label="Dataset Name"
            variant="outlined"
            :rules="[v => !!v || 'Name is required']"
            validate-on="blur"
            autofocus
          />
        </VForm>
      </VCardText>
      <VCardActions>
        <VSpacer />
        <VBtn variant="text" @click="handleClose"> Cancel </VBtn>
        <VBtn color="primary" :loading="loading" :disabled="!datasetName.trim()" @click="handleCreate"> Create </VBtn>
      </VCardActions>
    </VCard>
  </VDialog>
</template>
