<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { logger } from '@/utils/logger'
import { useCurrentAgent, useUpdateAgentMutation } from '@/composables/queries/useAgentsQuery'

interface Props {
  agentId: string
  agentDescription: string
  variant?: 'inline' | 'dialog'
  textClass?: string
}

const props = withDefaults(defineProps<Props>(), {
  variant: 'inline',
  textClass: 'text-body-1',
})

const emit = defineEmits<{
  updated: [newDescription: string]
}>()

const { currentGraphRunner } = useCurrentAgent()
const updateAgentMutation = useUpdateAgentMutation()

const isEditing = ref(false)
const editedDescription = ref('')
const descriptionError = ref('')

// Computed: is this agent currently saving
const isSaving = computed(() => updateAgentMutation.isPending.value)

// Watch for prop changes
watch(
  () => props.agentDescription,
  newDescription => {
    editedDescription.value = newDescription
  },
  { immediate: true }
)

// Start editing
const startEditing = () => {
  isEditing.value = true
  editedDescription.value = props.agentDescription
  descriptionError.value = ''
}

// Cancel editing
const cancelEditing = () => {
  isEditing.value = false
  editedDescription.value = props.agentDescription
  descriptionError.value = ''
}

// Save changes
const saveDescription = async () => {
  if (editedDescription.value.trim() === props.agentDescription) {
    cancelEditing()
    return
  }

  // Get versionId from currentGraphRunner
  const versionId = currentGraphRunner.value?.graph_runner_id
  if (!versionId) {
    descriptionError.value = 'No version selected'
    return
  }

  descriptionError.value = ''

  try {
    await updateAgentMutation.mutateAsync({
      agentId: props.agentId,
      versionId,
      data: {
        description: editedDescription.value.trim(),
      },
    })

    isEditing.value = false
    emit('updated', editedDescription.value.trim())
  } catch (error) {
    logger.error('Error updating agent description', { error })
    descriptionError.value = 'Failed to update agent description'
  }
}

// Handle keydown events
const handleKeydown = (event: KeyboardEvent) => {
  if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
    event.preventDefault()
    saveDescription()
  } else if (event.key === 'Escape') {
    event.preventDefault()
    cancelEditing()
  }
}
</script>

<template>
  <div class="editable-agent-description">
    <!-- Inline editing mode -->
    <template v-if="variant === 'inline'">
      <div v-if="!isEditing" class="d-flex align-center gap-2">
        <span
          v-if="agentDescription"
          class="cursor-pointer editable-text"
          :class="[textClass]"
          title="Click to edit description"
          @click="startEditing"
        >
          {{ agentDescription }}
        </span>
        <span
          v-else
          class="text-medium-emphasis cursor-pointer editable-text"
          title="Click to add description"
          @click="startEditing"
        >
          Add description...
        </span>
        <VBtn v-if="!isSaving" icon variant="text" size="small" class="edit-button" @click="startEditing">
          <VIcon icon="tabler-edit" size="16" />
        </VBtn>
        <VProgressCircular v-else indeterminate size="16" width="2" />
      </div>

      <div v-else class="d-flex flex-column gap-2">
        <VTextarea
          v-model="editedDescription"
          variant="outlined"
          density="compact"
          :error-messages="descriptionError"
          :loading="isSaving"
          autofocus
          rows="3"
          placeholder="Brief description of what this agent does..."
          class="description-input"
          @keydown="handleKeydown"
          @blur="saveDescription"
        />
        <div class="d-flex align-center gap-2">
          <VBtn variant="text" size="small" color="success" :loading="isSaving" @click="saveDescription">
            <VIcon icon="tabler-check" size="16" class="me-1" />
            Save
          </VBtn>
          <VBtn variant="text" size="small" color="error" :disabled="isSaving" @click="cancelEditing">
            <VIcon icon="tabler-x" size="16" class="me-1" />
            Cancel
          </VBtn>
          <span class="text-caption text-medium-emphasis"> Ctrl+Enter to save, Esc to cancel </span>
        </div>
      </div>
    </template>

    <!-- Dialog mode -->
    <template v-else>
      <VBtn variant="text" :class="textClass" :loading="isSaving" @click="startEditing">
        {{ agentDescription || 'Add description...' }}
        <VIcon icon="tabler-edit" size="16" class="ms-1" />
      </VBtn>

      <VDialog v-model="isEditing" max-width="var(--dnr-dialog-sm)" persistent>
        <VCard>
          <VCardTitle class="text-h6"> Edit Agent Description </VCardTitle>

          <VCardText>
            <VTextarea
              v-model="editedDescription"
              label="Agent Description"
              variant="outlined"
              :error-messages="descriptionError"
              :loading="isSaving"
              autofocus
              rows="4"
              placeholder="Brief description of what this agent does..."
              @keydown.ctrl.enter="saveDescription"
            />
          </VCardText>

          <VCardActions class="justify-end pa-4">
            <VBtn variant="text" :disabled="isSaving" @click="cancelEditing"> Cancel </VBtn>
            <VBtn color="primary" :loading="isSaving" @click="saveDescription"> Save </VBtn>
          </VCardActions>
        </VCard>
      </VDialog>
    </template>
  </div>
</template>

<style lang="scss" scoped>
.editable-agent-description {
  .edit-button {
    opacity: 0;
    transition: opacity 0.2s ease;
  }

  &:hover .edit-button {
    opacity: 1;
  }

  .editable-text {
    transition: all 0.2s ease;
    border-radius: 4px;
    padding: 4px 8px;
    margin: -4px -8px;

    &:hover {
      background-color: rgba(var(--v-theme-on-surface), 0.04);
    }
  }

  .description-input {
    min-width: 400px;
  }
}
</style>
