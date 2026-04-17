<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { logger } from '@/utils/logger'
import { tagColor } from '@/utils/tagColor'

interface Props {
  entityId: string
  entityName: string
  entityDescription?: string
  entityTags?: string[]
  availableTags?: string[]
  modelValue: boolean
  entityType: 'agent' | 'project'
  saveFunction: (id: string, data: any) => Promise<void>
}

const props = withDefaults(defineProps<Props>(), {
  entityTags: () => [],
  availableTags: () => [],
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  updated: [data: { name: string; description: string; tags: string[] }]
}>()

const editedName = ref('')
const editedDescription = ref('')
const editedTags = ref<string[]>([])
const nameError = ref('')
const isSaving = ref(false)

watch(
  () => props.modelValue,
  isOpen => {
    if (isOpen) {
      editedName.value = props.entityName
      editedDescription.value = props.entityDescription || ''
      editedTags.value = [...(props.entityTags || [])]
      nameError.value = ''
    }
  },
  { immediate: true }
)

const closeDialog = () => {
  emit('update:modelValue', false)
}

const saveEntity = async () => {
  if (!editedName.value.trim()) {
    nameError.value = `${props.entityType === 'agent' ? 'Agent' : 'Project'} name cannot be empty`
    return
  }

  isSaving.value = true
  nameError.value = ''

  try {
    const normalizedTags = [...new Set(editedTags.value.map(t => t.toLowerCase().trim()).filter(Boolean))]

    await props.saveFunction(props.entityId, {
      name: editedName.value.trim(),
      description: editedDescription.value.trim(),
      tags: normalizedTags,
    })

    emit('updated', {
      name: editedName.value.trim(),
      description: editedDescription.value.trim(),
      tags: normalizedTags,
    })
    closeDialog()
  } catch (error) {
    logger.error(`Error updating ${props.entityType}`, { error })
    nameError.value = `Failed to update ${props.entityType}`
  } finally {
    isSaving.value = false
  }
}

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
          class="mb-4"
        />

        <VCombobox
          v-model="editedTags"
          :items="availableTags"
          label="Tags"
          variant="outlined"
          multiple
          chips
          closable-chips
          :disabled="isSaving"
          placeholder="Type to add a tag…"
          hide-details
        >
          <template #chip="{ props: chipProps, item }">
            <VChip v-bind="chipProps" size="small" variant="tonal" :color="tagColor(item.raw)" label closable>
              {{ item.raw }}
            </VChip>
          </template>
        </VCombobox>
      </VCardText>

      <VDivider />

      <VCardActions class="justify-end pa-6">
        <VBtn variant="text" :disabled="isSaving" @click="closeDialog"> Cancel </VBtn>
        <VBtn color="primary" :loading="isSaving" @click="saveEntity"> Save </VBtn>
      </VCardActions>
    </VCard>
  </VDialog>
</template>
