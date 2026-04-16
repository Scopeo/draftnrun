<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { logger } from '@/utils/logger'

interface Props {
  entityId: string
  entityName: string
  entityDescription?: string
  modelValue: boolean
  entityType: 'agent' | 'project' // For display purposes
  saveFunction: (id: string, data: any) => Promise<void>
}

const props = defineProps<Props>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  updated: [data: { name: string; description: string }]
}>()

const editedName = ref('')
const editedDescription = ref('')
const nameError = ref('')
const isSaving = ref(false)

// Watch for prop changes
watch(
  () => props.modelValue,
  isOpen => {
    if (isOpen) {
      editedName.value = props.entityName
      editedDescription.value = props.entityDescription || ''
      nameError.value = ''
    }
  },
  { immediate: true }
)

// Close dialog
const closeDialog = () => {
  emit('update:modelValue', false)
}

// Save changes
const saveEntity = async () => {
  if (!editedName.value.trim()) {
    nameError.value = `${props.entityType === 'agent' ? 'Agent' : 'Project'} name cannot be empty`
    return
  }

  isSaving.value = true
  nameError.value = ''

  try {
    await props.saveFunction(props.entityId, {
      name: editedName.value.trim(),
      description: editedDescription.value.trim(),
    })

    emit('updated', {
      name: editedName.value.trim(),
      description: editedDescription.value.trim(),
    })
    closeDialog()
  } catch (error) {
    logger.error(`Error updating ${props.entityType}`, { error })
    nameError.value = `Failed to update ${props.entityType}`
  } finally {
    isSaving.value = false
  }
}

// Entity type display
const entityTypeDisplay = computed(() => (props.entityType === 'agent' ? 'Agent' : 'Project'))
</script>

<template>
  <VDialog
    :model-value="modelValue"
    max-width="var(--dnr-dialog-md)"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <VCard>
      <VCardTitle class="d-flex align-center justify-space-between pa-6">
        <span class="text-h5">Edit {{ entityTypeDisplay }}</span>
        <VBtn icon variant="text" size="small" :disabled="isSaving" @click="closeDialog">
          <VIcon icon="tabler-x" />
        </VBtn>
      </VCardTitle>

      <VDivider />

      <VCardText class="pa-6">
        <VTextField
          v-model="editedName"
          :label="`${entityTypeDisplay} Name`"
          variant="outlined"
          :error-messages="nameError"
          :disabled="isSaving"
          autofocus
          class="mb-4"
        />

        <VTextarea
          v-model="editedDescription"
          label="Description"
          variant="outlined"
          rows="4"
          :disabled="isSaving"
          :placeholder="`Brief description of what this ${entityType} does...`"
        />
      </VCardText>

      <VDivider />

      <VCardActions class="justify-end pa-6">
        <VBtn variant="text" :disabled="isSaving" @click="closeDialog"> Cancel </VBtn>
        <VBtn color="primary" :loading="isSaving" @click="saveEntity"> Save </VBtn>
      </VCardActions>
    </VCard>
  </VDialog>
</template>
