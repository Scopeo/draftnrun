<script setup lang="ts">
// 1. Vue/core imports

// 2. Third-party libraries (none here)

// 3. Local components (none here)

// 4. Composables (none here)

// 5. Utils/helpers (none here)

// 6. Types (none here)

// Props & Emits
interface Props {
  column: { column_id: string; column_name: string }
  isEditing: boolean
  editingName: string
}

const props = defineProps<Props>()

const emit = defineEmits<{
  'start-edit': []
  'update-name': [name: string]
  save: []
  cancel: []
  delete: []
}>()

// Methods
const handleNameUpdate = (name: string) => {
  emit('update-name', name)
}

const handleKeydown = (event: KeyboardEvent) => {
  if (event.key === 'Enter') {
    emit('save')
  } else if (event.key === 'Escape') {
    emit('cancel')
  }
}
</script>

<template>
  <div class="d-flex align-center gap-1 custom-column-header">
    <div
      v-if="!isEditing"
      class="flex-grow-1 d-flex align-center"
      style="cursor: pointer; min-height: 24px"
      @click="emit('start-edit')"
    >
      <span class="text-body-2">{{ column.column_name }}</span>
    </div>
    <VTextField
      v-else
      :model-value="editingName"
      variant="plain"
      density="compact"
      hide-details
      autofocus
      class="flex-grow-1"
      style="min-width: 100px"
      @update:model-value="handleNameUpdate"
      @keydown="handleKeydown"
      @blur="emit('save')"
    />
    <VBtn icon size="x-small" variant="text" density="compact" color="error" @click.stop="emit('delete')">
      <VIcon icon="tabler-trash" size="16" />
      <VTooltip activator="parent">Delete column</VTooltip>
    </VBtn>
  </div>
</template>

<style lang="scss" scoped>
.custom-column-header {
  padding: 4px 8px;
  min-height: 32px;

  &:hover {
    background-color: rgba(var(--v-theme-primary), 0.05);
    border-radius: 4px;
  }

  :deep(.v-field) {
    padding: 0;
  }

  :deep(.v-field__input) {
    padding: 4px 8px;
    min-height: 24px;
    font-size: 0.875rem;
  }
}
</style>
