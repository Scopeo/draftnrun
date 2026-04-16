<script setup lang="ts">
import { computed, ref } from 'vue'
import IconPicker from './IconPicker.vue'
import ProjectAvatar from './ProjectAvatar.vue'
import { logger } from '@/utils/logger'
import { useUpdateProjectMutation } from '@/composables/queries/useProjectsQuery'
import { DEFAULT_PROJECT_COLOR, DEFAULT_PROJECT_ICON } from '@/composables/useProjectDefaults'

interface Props {
  projectId: string
  currentIcon?: string
  currentColor?: string
  entityType: 'project' | 'agent'
  disabled?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  currentIcon: DEFAULT_PROJECT_ICON,
  currentColor: DEFAULT_PROJECT_COLOR,
  disabled: false,
})

const emit = defineEmits<{
  updated: [{ icon: string; iconColor: string }]
}>()

const updateProjectMutation = useUpdateProjectMutation()
const showDialog = ref(false)
const isHovered = ref(false)

// Computed values that fall back to defaults if current values are null/undefined
const displayIcon = computed(() => props.currentIcon || DEFAULT_PROJECT_ICON)
const displayColor = computed(() => props.currentColor || DEFAULT_PROJECT_COLOR)

// Local state for icon picker (only used in dialog)
const selectedIcon = ref('')
const selectedColor = ref('')

const iconValue = computed({
  get: () => ({ icon: selectedIcon.value, iconColor: selectedColor.value }),
  set: (value: { icon: string; iconColor: string }) => {
    selectedIcon.value = value.icon
    selectedColor.value = value.iconColor
  },
})

const openDialog = () => {
  if (props.disabled) return
  selectedIcon.value = displayIcon.value
  selectedColor.value = displayColor.value
  showDialog.value = true
}

const handleSave = async () => {
  await updateProjectMutation.mutateAsync(
    {
      projectId: props.projectId,
      data: {
        icon: selectedIcon.value,
        icon_color: selectedColor.value,
      },
    },
    {
      onSuccess: () => {
        emit('updated', {
          icon: selectedIcon.value,
          iconColor: selectedColor.value,
        })
        showDialog.value = false
      },
      onError: error => {
        logger.error('Failed to update icon', { error })
      },
    }
  )
}

const handleCancel = () => {
  showDialog.value = false
}
</script>

<template>
  <div
    class="editable-avatar"
    :class="{ 'is-disabled': disabled }"
    role="button"
    tabindex="0"
    :aria-label="`Click to change ${entityType} icon`"
    @mouseenter="isHovered = true"
    @mouseleave="isHovered = false"
    @click="openDialog"
    @keydown.enter="openDialog"
    @keydown.space.prevent="openDialog"
  >
    <div class="avatar-wrapper">
      <ProjectAvatar :icon="displayIcon" :icon-color="displayColor" size="small" />

      <!-- Edit indicator overlay -->
      <div v-if="isHovered && !disabled" class="edit-indicator">
        <VIcon icon="tabler-edit" size="12" />
      </div>
    </div>
  </div>

  <!-- Icon Picker Dialog -->
  <VDialog v-model="showDialog" max-width="var(--dnr-dialog-md)">
    <VCard>
      <VCardTitle class="d-flex align-center pa-4">
        <VIcon icon="tabler-palette" size="24" color="primary" class="me-2" />
        Change {{ entityType === 'project' ? 'Project' : 'Agent' }} Icon
      </VCardTitle>

      <VDivider />

      <VCardText class="pt-4 px-4">
        <IconPicker v-model="iconValue" />
      </VCardText>

      <VDivider />

      <VCardActions class="justify-end pa-4">
        <VBtn color="grey" variant="text" :disabled="updateProjectMutation.isPending.value" @click="handleCancel">
          Cancel
        </VBtn>
        <VBtn color="primary" variant="flat" :loading="updateProjectMutation.isPending.value" @click="handleSave">
          Save
        </VBtn>
      </VCardActions>
    </VCard>
  </VDialog>
</template>

<style lang="scss" scoped>
.editable-avatar {
  cursor: pointer;
  position: relative;
  transition: all 0.2s ease;
  overflow: visible;

  &:not(.is-disabled):hover {
    transform: scale(1.05);
  }

  &.is-disabled {
    cursor: not-allowed;
    opacity: 0.6;
  }

  &:focus-visible {
    outline: 2px solid rgb(var(--v-theme-primary));
    outline-offset: 2px;
  }
}

.avatar-wrapper {
  position: relative;
  transition: all 0.2s ease;
  overflow: visible;
  border-radius: 50%;

  .editable-avatar:not(.is-disabled):hover &::after {
    content: '';
    position: absolute;
    inset: 0;
    background: rgba(0, 0, 0, 0.05);
    border-radius: inherit;
  }
}

.edit-indicator {
  position: absolute;
  bottom: -4px;
  right: -4px;
  background: rgb(var(--v-theme-primary));
  border-radius: 50%;
  padding: 4px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
}
</style>
