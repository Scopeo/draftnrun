<script setup lang="ts">
import { computed } from 'vue'
import { useCollectionWithIds } from '@/composables/useCollectionWithIds'

type AttachmentValue = string | AttachmentObject

interface AttachmentObject {
  url: string
  filename: string
}

interface Props {
  label?: string
  description?: string
  readonly?: boolean
  color?: string
}

withDefaults(defineProps<Props>(), {
  label: 'Attachments',
  description: '',
  readonly: false,
  color: 'primary',
})

const model = defineModel<AttachmentValue[] | undefined>({ default: () => [] })

const normalizedModel = computed<AttachmentObject[]>({
  get: () => (Array.isArray(model.value) ? model.value.map(normalizeAttachment) : []),
  set: value => {
    model.value = value.filter(attachment => attachment.url || attachment.filename)
  },
})

const { items, add, remove, update } = useCollectionWithIds<AttachmentObject>({
  modelValue: normalizedModel,
  createDefault: () => ({ url: '', filename: '' }),
  onChange: value => {
    normalizedModel.value = value
  },
})

function normalizeAttachment(value: AttachmentValue): AttachmentObject {
  if (typeof value === 'string') {
    return { url: value, filename: inferFilename(value) }
  }

  return {
    url: value.url || '',
    filename: value.filename || inferFilename(value.url || ''),
  }
}

function inferFilename(value: string): string {
  if (!value) return ''

  try {
    const parsedUrl = new URL(value)
    const filename = parsedUrl.pathname.split('/').filter(Boolean).pop()

    return filename ? decodeURIComponent(filename) : ''
  } catch {
    const pathWithoutQuery = value.split(/[?#]/)[0]

    return pathWithoutQuery.split('/').filter(Boolean).pop() || ''
  }
}
</script>

<template>
  <div class="attachment-list-input flex-grow-1">
    <div v-if="items.length === 0" class="text-caption text-medium-emphasis mb-2">No attachments added.</div>

    <VCard v-for="item in items" :key="item._id" variant="outlined" class="attachment-row mb-3">
      <VCardText class="pa-3">
        <div class="d-flex gap-3 align-start">
          <VTextField
            :model-value="item.url"
            label="URL"
            placeholder="https://example.com/file.pdf"
            variant="outlined"
            density="comfortable"
            hide-details="auto"
            class="flex-grow-1"
            :readonly="readonly"
            :color="color"
            @update:model-value="value => update(item._id, 'url', String(value))"
          />
          <VTextField
            :model-value="item.filename"
            label="Filename"
            placeholder="file.pdf"
            variant="outlined"
            density="comfortable"
            hide-details="auto"
            class="flex-grow-1"
            :readonly="readonly"
            :color="color"
            @update:model-value="value => update(item._id, 'filename', String(value))"
          />
          <VBtn icon variant="text" color="error" class="mt-1" :disabled="readonly" @click="remove(item._id)">
            <VIcon icon="tabler-trash" size="18" />
          </VBtn>
        </div>
      </VCardText>
    </VCard>

    <VBtn variant="tonal" size="small" :color="color" :disabled="readonly" @click="add">
      <VIcon icon="tabler-plus" size="18" class="me-1" />
      Add attachment
    </VBtn>

    <div v-if="description" class="text-caption text-medium-emphasis mt-2">
      {{ description }}
    </div>
  </div>
</template>

<style scoped>
.attachment-row {
  background: rgba(var(--v-theme-surface), 0.6);
}
</style>
