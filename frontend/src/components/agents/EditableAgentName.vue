<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { logger } from '@/utils/logger'
import { useCurrentAgent, useUpdateAgentMutation } from '@/composables/queries/useAgentsQuery'

interface Props {
  agentId: string
  agentName: string
  variant?: 'inline' | 'dialog'
  textClass?: string
}

const props = withDefaults(defineProps<Props>(), {
  variant: 'inline',
  textClass: 'text-h6',
})

const emit = defineEmits<{
  updated: [newName: string]
}>()

const { currentGraphRunner } = useCurrentAgent()
const updateAgentMutation = useUpdateAgentMutation()

const isEditing = ref(false)
const editedName = ref('')
const nameError = ref('')

// Computed: is this agent currently saving
const isSaving = computed(() => updateAgentMutation.isPending.value)

// Watch for prop changes
watch(
  () => props.agentName,
  newName => {
    editedName.value = newName
  },
  { immediate: true }
)

// Start editing
const startEditing = () => {
  isEditing.value = true
  editedName.value = props.agentName
  nameError.value = ''
}

// Cancel editing
const cancelEditing = () => {
  isEditing.value = false
  editedName.value = props.agentName
  nameError.value = ''
}

// Save changes
const saveName = async () => {
  if (!editedName.value.trim()) {
    nameError.value = 'Agent name cannot be empty'
    return
  }

  if (editedName.value.trim() === props.agentName) {
    cancelEditing()
    return
  }

  // Get versionId from currentGraphRunner
  const versionId = currentGraphRunner.value?.graph_runner_id
  if (!versionId) {
    nameError.value = 'No version selected'
    return
  }

  nameError.value = ''

  try {
    await updateAgentMutation.mutateAsync({
      agentId: props.agentId,
      versionId,
      data: {
        name: editedName.value.trim(),
      },
    })

    isEditing.value = false
    emit('updated', editedName.value.trim())
  } catch (error) {
    logger.error('Error updating agent name', { error })
    nameError.value = 'Failed to update agent name'
  }
}

// Handle keydown events
const handleKeydown = (event: KeyboardEvent) => {
  if (event.key === 'Enter') {
    event.preventDefault()
    saveName()
  } else if (event.key === 'Escape') {
    event.preventDefault()
    cancelEditing()
  }
}
</script>

<template>
  <div class="editable-agent-name">
    <!-- Inline editing mode -->
    <template v-if="variant === 'inline'">
      <div v-if="!isEditing" class="d-flex align-center gap-2">
        <span class="cursor-pointer editable-text" :class="[textClass]" title="Click to edit" @click="startEditing">
          {{ agentName }}
        </span>
        <VBtn v-if="!isSaving" icon variant="text" size="small" class="edit-button" @click="startEditing">
          <VIcon icon="tabler-edit" size="16" />
        </VBtn>
        <VProgressCircular v-else indeterminate size="16" width="2" />
      </div>

      <div v-else class="d-flex align-center gap-2">
        <VTextField
          v-model="editedName"
          variant="outlined"
          density="compact"
          :error-messages="nameError"
          :loading="isSaving"
          autofocus
          class="name-input"
          @keydown="handleKeydown"
          @blur="saveName"
        />
        <VBtn icon variant="text" size="small" color="success" :loading="isSaving" @click="saveName">
          <VIcon icon="tabler-check" size="16" />
        </VBtn>
        <VBtn icon variant="text" size="small" color="error" :disabled="isSaving" @click="cancelEditing">
          <VIcon icon="tabler-x" size="16" />
        </VBtn>
      </div>
    </template>

    <!-- Dialog mode -->
    <template v-else>
      <VBtn variant="text" :class="textClass" :loading="isSaving" @click="startEditing">
        {{ agentName }}
        <VIcon icon="tabler-edit" size="16" class="ms-1" />
      </VBtn>

      <VDialog v-model="isEditing" max-width="var(--dnr-dialog-sm)" persistent>
        <VCard>
          <VCardTitle class="text-h6"> Edit Agent Name </VCardTitle>

          <VCardText>
            <VTextField
              v-model="editedName"
              label="Agent Name"
              variant="outlined"
              :error-messages="nameError"
              :loading="isSaving"
              autofocus
              @keydown.enter="saveName"
            />
          </VCardText>

          <VCardActions class="justify-end pa-4">
            <VBtn variant="text" :disabled="isSaving" @click="cancelEditing"> Cancel </VBtn>
            <VBtn color="primary" :loading="isSaving" @click="saveName"> Save </VBtn>
          </VCardActions>
        </VCard>
      </VDialog>
    </template>
  </div>
</template>

<style lang="scss" scoped>
.editable-agent-name {
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

  .name-input {
    min-width: 200px;
  }
}
</style>
