<script setup lang="ts">
import { ref, watch } from 'vue'
import { logger } from '@/utils/logger'
import { useUpdateAgentMutation } from '@/composables/queries/useAgentsQuery'

interface Props {
  agentId: string
  versionId: string
  agentName: string
  agentDescription?: string
  modelValue: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  updated: [data: { name: string; description: string }]
}>()

const updateAgentMutation = useUpdateAgentMutation()

const editedName = ref('')
const editedDescription = ref('')
const nameError = ref('')
const isSaving = ref(false)

// Watch for prop changes
watch(
  () => props.modelValue,
  isOpen => {
    if (isOpen) {
      editedName.value = props.agentName
      editedDescription.value = props.agentDescription || ''
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
const saveAgent = async () => {
  if (!editedName.value.trim()) {
    nameError.value = 'Agent name cannot be empty'
    return
  }

  isSaving.value = true
  nameError.value = ''

  try {
    await updateAgentMutation.mutateAsync({
      agentId: props.agentId,
      versionId: props.versionId,
      data: {
        name: editedName.value.trim(),
        description: editedDescription.value.trim(),
      },
    })

    emit('updated', {
      name: editedName.value.trim(),
      description: editedDescription.value.trim(),
    })
    closeDialog()
  } catch (error) {
    logger.error('Error updating agent', { error })
    nameError.value = 'Failed to update agent'
  } finally {
    isSaving.value = false
  }
}
</script>

<template>
  <VDialog
    :model-value="modelValue"
    max-width="600px"
    persistent
    @update:model-value="emit('update:modelValue', $event)"
  >
    <VCard>
      <VCardTitle class="d-flex align-center justify-space-between pa-6">
        <span class="text-h5">Edit Agent</span>
        <VBtn icon variant="text" size="small" :disabled="isSaving" @click="closeDialog">
          <VIcon icon="tabler-x" />
        </VBtn>
      </VCardTitle>

      <VDivider />

      <VCardText class="pa-6">
        <VTextField
          v-model="editedName"
          label="Agent Name"
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
          placeholder="Brief description of what this agent does..."
        />
      </VCardText>

      <VDivider />

      <VCardActions class="justify-end pa-6">
        <VBtn variant="text" :disabled="isSaving" @click="closeDialog"> Cancel </VBtn>
        <VBtn color="primary" :loading="isSaving" @click="saveAgent"> Save </VBtn>
      </VCardActions>
    </VCard>
  </VDialog>
</template>
