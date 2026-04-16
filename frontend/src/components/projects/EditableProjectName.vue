<script setup lang="ts">
import { useAbility } from '@casl/vue'
import { ref, watch } from 'vue'
import { logger } from '@/utils/logger'
import { scopeoApi } from '@/api'

interface Props {
  projectId: string
  projectName: string
  variant?: 'inline' | 'modal'
  textClass?: string
}

interface Emits {
  (e: 'updated', newName: string): void
}

const props = withDefaults(defineProps<Props>(), {
  variant: 'inline',
  textClass: 'text-h4',
})

const emit = defineEmits<Emits>()

const ability = useAbility()

// State
const isEditing = ref(false)
const isUpdating = ref(false)
const editedName = ref(props.projectName)
const showModal = ref(false)
const error = ref<string | null>(null)

// Watch for prop changes
watch(
  () => props.projectName,
  newName => {
    editedName.value = newName
  }
)

// Start editing
const startEdit = (event?: Event) => {
  if (!ability.can('update', 'Project')) return

  // Prevent event propagation to avoid navigating when clicking edit
  if (event) {
    event.preventDefault()
    event.stopPropagation()
  }

  editedName.value = props.projectName
  error.value = null

  if (props.variant === 'modal') {
    showModal.value = true
  } else {
    isEditing.value = true
  }
}

// Save changes
const saveChanges = async () => {
  if (!editedName.value.trim()) {
    error.value = 'Project name cannot be empty'
    return
  }

  if (editedName.value === props.projectName) {
    cancelEdit()
    return
  }

  try {
    isUpdating.value = true
    await scopeoApi.projects.updateProject(props.projectId, {
      project_name: editedName.value.trim(),
    })

    emit('updated', editedName.value.trim())
    cancelEdit()
  } catch (err: unknown) {
    logger.error('Error updating project name', { error: err })
    error.value = err instanceof Error ? err.message : 'Failed to update project name'
  } finally {
    isUpdating.value = false
  }
}

// Cancel editing
const cancelEdit = () => {
  isEditing.value = false
  showModal.value = false
  editedName.value = props.projectName
  error.value = null
}

// Handle key events
const handleKeydown = (event: KeyboardEvent) => {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    saveChanges()
  } else if (event.key === 'Escape') {
    cancelEdit()
  }
}

// Format project name (capitalize first letter of each word)
const formatProjectName = (name: string) => {
  return name
    .split(' ')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
}
</script>

<template>
  <!-- Inline Editing Version -->
  <template v-if="variant === 'inline'">
    <!-- Display Mode -->
    <h4
      v-if="!isEditing"
      :class="[textClass, ability.can('update', 'Project') ? 'cursor-pointer editable-text' : '']"
      @click="startEdit"
    >
      {{ formatProjectName(projectName) }}
    </h4>

    <!-- Edit Mode -->
    <div v-else class="edit-mode-container">
      <input
        v-model="editedName"
        class="edit-input"
        :class="[textClass]"
        :disabled="isUpdating"
        autofocus
        @keydown="handleKeydown"
        @blur="saveChanges"
        @click.stop
      />

      <!-- Error Message -->
      <VAlert v-if="error" type="error" variant="tonal" density="compact" class="mt-2">
        {{ error }}
      </VAlert>
    </div>
  </template>

  <!-- Modal Version -->
  <template v-else>
    <!-- Display with Edit Button -->
    <div class="d-flex align-center gap-2">
      <h6 :class="textClass">
        {{ projectName }}
      </h6>
      <VBtn v-if="ability.can('update', 'Project')" icon size="x-small" variant="text" @click="startEdit">
        <VIcon icon="tabler-edit" size="14" />
      </VBtn>
    </div>

    <!-- Edit Modal -->
    <VDialog v-model="showModal" max-width="var(--dnr-dialog-sm)" persistent>
      <VCard>
        <VCardTitle class="text-h6"> Edit Project Name </VCardTitle>

        <VCardText>
          <VTextField
            v-model="editedName"
            label="Project Name"
            variant="outlined"
            :error-messages="error"
            autofocus
            @keydown="handleKeydown"
          />
        </VCardText>

        <VCardActions class="justify-end pa-4">
          <VBtn variant="text" @click="cancelEdit"> Cancel </VBtn>
          <VBtn color="primary" :loading="isUpdating" @click="saveChanges"> Save </VBtn>
        </VCardActions>
      </VCard>
    </VDialog>
  </template>
</template>

<style scoped>
.cursor-pointer {
  cursor: pointer;
}

.editable-text {
  transition: all 0.2s ease;
  border-radius: 4px;
  padding: 4px 8px;
  margin: -4px -8px;
}

.editable-text:hover {
  background-color: rgba(var(--v-theme-on-surface), 0.04);
}

.edit-mode-container {
  position: relative;
}

.edit-input {
  background: transparent;
  border: 2px solid rgb(var(--v-theme-primary));
  border-radius: 4px;
  padding: 4px 8px;
  outline: none;
  font-family: inherit;
  font-weight: inherit;
  font-size: inherit;
  line-height: inherit;
  color: inherit;
  width: auto;
  min-width: 200px;
}

.edit-input:focus {
  border-color: rgb(var(--v-theme-primary));
  box-shadow: 0 0 0 2px rgba(var(--v-theme-primary), 0.2);
}

.edit-input:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>
