<script setup lang="ts">
import { format } from 'date-fns'
import { computed, ref, watch } from 'vue'
import { logger } from '@/utils/logger'
import {
  type DocumentReadingMode,
  type Source,
  useCreateIngestionTaskMutation,
} from '@/composables/queries/useDataSourcesQuery'
import { getErrorMessage } from '@/composables/useDataSources'
import { scopeoApi } from '@/api'

const props = defineProps<{
  modelValue: boolean
  orgId: string | undefined
  source?: Source | null
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  created: []
  closed: []
}>()

const createIngestionTaskMutation = useCreateIngestionTaskMutation()

const isAddFilesMode = computed(() => !!props.source)

const MAX_FILES = 100

const documentReadingModeOptions = [
  { value: 'standard', title: 'Standard', description: 'Fast and free - best for standard documents with clear text' },
  { value: 'llamaparse', title: 'LlamaParse', description: 'AI-powered parsing - handles complex layouts and tables' },
  {
    value: 'mistral_ocr',
    title: 'Mistral OCR',
    description:
      'Mistral-powered OCR — delivers high-accuracy text extraction from scanned documents and images within PDF and DOCX files',
  },
]

const isUploading = ref(false)
const files = ref<File[]>([])
const errors = ref<string[]>([])
const progress = ref({ current: 0, total: 0 })
const documentReadingMode = ref<DocumentReadingMode>('standard')
const sourceName = ref('')
const sourceNameError = ref('')

const toDocumentReadingMode = (value: unknown): DocumentReadingMode => {
  if (value === 'llamaparse' || value === 'mistral_ocr' || value === 'standard') return value
  return 'standard'
}

const getFileExtensionsByMode = (mode: DocumentReadingMode) => {
  if (mode === 'llamaparse') return ['.pdf', '.docx', '.xls', '.xlsx', '.xlsm']
  return ['.pdf', '.docx']
}

const allowedExtensions = computed(() => getFileExtensionsByMode(documentReadingMode.value))
const supportedTypesText = computed(() => allowedExtensions.value.map(ext => ext.slice(1).toUpperCase()).join(', '))

const reset = () => {
  files.value = []
  errors.value = []
  progress.value = { current: 0, total: 0 }
  sourceName.value = ''
  sourceNameError.value = ''
  documentReadingMode.value = 'standard'
}

watch(
  () => props.modelValue,
  open => {
    if (open) {
      reset()
      if (props.source) {
        documentReadingMode.value = toDocumentReadingMode(props.source.source_attributes?.document_reading_mode)
      }
    }
  }
)

const close = () => {
  emit('update:modelValue', false)
  emit('closed')
}

const onReadingModeChange = (newMode: DocumentReadingMode) => {
  documentReadingMode.value = newMode
  if (newMode !== 'llamaparse' && files.value.length > 0) {
    const allowed = getFileExtensionsByMode(newMode)

    const valid = files.value.filter(f => {
      const ext = `.${f.name.split('.').pop()?.toLowerCase()}`
      return allowed.includes(ext)
    })

    if (valid.length !== files.value.length) {
      files.value = valid
      errors.value = ['Unsupported files removed for the selected reading mode']
    }
  } else if (errors.value.length > 0) {
    errors.value = []
  }
}

const onFilesSelected = (selected: File | File[] | null) => {
  errors.value = []
  if (!selected) {
    files.value = []
    return
  }

  const arr = Array.isArray(selected) ? selected : [selected]
  if (arr.length > MAX_FILES) {
    errors.value = [`You can only upload up to ${MAX_FILES} files at once. Please select fewer files.`]
    files.value = []
    return
  }

  const invalid = arr.filter(f => {
    const dotIdx = f.name.lastIndexOf('.')
    if (dotIdx === -1 || dotIdx === f.name.length - 1) return true
    return !allowedExtensions.value.includes(`.${f.name.substring(dotIdx + 1).toLowerCase()}`)
  })

  if (invalid.length > 0) {
    const valid = arr.filter(f => !invalid.includes(f))

    files.value = valid
    errors.value = [
      `Removed ${invalid.length} unsupported file(s): ${invalid.map(f => f.name).join(', ')}. Only ${supportedTypesText.value} files are supported.`,
    ]
    return
  }
  files.value = arr
}

const removeFile = (index: number) => {
  files.value = files.value.filter((_, i) => i !== index)
}

const getFileIcon = (fileName: string) => {
  const ext = fileName.split('.').pop()?.toLowerCase()
  switch (ext) {
    case 'pdf':
      return 'tabler-file-type-pdf'
    case 'doc':
    case 'docx':
      return 'tabler-file-type-doc'
    case 'xlsx':
      return 'tabler-file-type-xls'
    case 'ppt':
    case 'pptx':
      return 'tabler-file-type-ppt'
    default:
      return 'tabler-file'
  }
}

const formatFileSize = (bytes: number) => {
  if (bytes === 0) return '0 Bytes'
  const k = 1024
  const sizes = ['Bytes', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${Number.parseFloat((bytes / k ** i).toFixed(2))} ${sizes[i]}`
}

const validateSourceName = () => {
  if (isAddFilesMode.value) return true
  sourceNameError.value = ''
  if (!sourceName.value.trim()) {
    sourceNameError.value = 'Source name is required'
    return false
  }
  if (sourceName.value.trim().length > 30) {
    sourceNameError.value = 'Source name must not exceed 30 characters'
    return false
  }
  return true
}

const submit = async () => {
  if (files.value.length === 0) {
    errors.value = ['Please select at least one file to upload']
    return
  }
  if (!isAddFilesMode.value && !validateSourceName()) return
  if (!props.orgId) {
    errors.value = ['Missing organization ID']
    return
  }

  try {
    isUploading.value = true
    errors.value = []
    progress.value = { current: 0, total: files.value.length }

    const presignedList: Array<{ filename: string; presigned_url: string; key: string; content_type: string }> =
      await scopeoApi.files.getPresignedUploadUrls(props.orgId, files.value)

    if (!presignedList || !Array.isArray(presignedList) || presignedList.length !== files.value.length) {
      logger.error('Invalid presigned URL response', { error: presignedList })
      errors.value = ['Failed to get upload URLs for all files']
      return
    }

    const CONCURRENCY_LIMIT = 10
    const batch: Promise<void>[] = []
    let completedCount = 0

    for (let i = 0; i < files.value.length; i++) {
      const file = files.value[i]
      const info = presignedList[i]
      if (!info?.presigned_url || !info?.key) {
        throw new Error(`Invalid presigned URL response for file ${file?.name || i + 1}`)
      }

      const p = fetch(info.presigned_url, {
        method: 'PUT',
        headers: { 'Content-Type': file.type || info.content_type || 'application/octet-stream' },
        body: file,
      }).then(res => {
        if (!res.ok) throw new Error(`Upload failed for ${file.name} (status ${res.status})`)
        completedCount++
        progress.value.current = completedCount
      })

      batch.push(p)
      if (batch.length >= CONCURRENCY_LIMIT || i === files.value.length - 1) {
        await Promise.all(batch)
        batch.length = 0
      }
    }

    const filesList = files.value.map((file, idx) => ({
      path: presignedList[idx].key,
      name: file.name,
      s3_path: presignedList[idx].key,
      last_edited_ts: format(new Date(), 'yyyy-MM-dd HH:mm:ss'),
      metadata: {},
    }))

    const sourceAttributes: any = {
      list_of_files_from_local_folder: filesList,
      document_reading_mode: documentReadingMode.value,
    }

    const payload = isAddFilesMode.value
      ? {
          source_id: props.source!.id,
          source_name: props.source!.source_name,
          source_type: props.source!.source_type,
          status: 'pending',
          source_attributes: sourceAttributes,
        }
      : {
          source_name: sourceName.value.trim(),
          source_type: 'local',
          status: 'pending',
          source_attributes: sourceAttributes,
        }

    await createIngestionTaskMutation.mutateAsync({ orgId: props.orgId, payload })

    close()
    emit('created')
  } catch (error: unknown) {
    logger.error('Error uploading files', { error })
    errors.value = [getErrorMessage(error, 'Failed to upload files. Please try again.')]
  } finally {
    isUploading.value = false
  }
}
</script>

<template>
  <VDialog
    :model-value="modelValue"
    max-width="var(--dnr-dialog-md)"
    :persistent="isUploading"
    @update:model-value="!isUploading && close()"
  >
    <VCard>
      <VCardTitle class="text-h6 pa-4 d-flex align-center">
        <VIcon :icon="isAddFilesMode ? 'tabler-file-plus' : 'tabler-upload'" class="me-2" />
        {{ isAddFilesMode ? `Add Files to ${source?.source_name || 'Source'}` : 'Upload Files' }}
      </VCardTitle>

      <VCardText class="pa-4 dnr-form-compact">
        <VTextField
          v-if="!isAddFilesMode"
          v-model="sourceName"
          label="Source Name *"
          placeholder="Enter a name for your data source"
          :error-messages="sourceNameError"
          :disabled="isUploading"
          maxlength="30"
          counter="30"
          class="mb-4"
        />

        <VSelect
          :model-value="documentReadingMode"
          label="Reading Mode"
          :items="documentReadingModeOptions"
          item-title="title"
          item-value="value"
          :disabled="isUploading"
          class="mb-4"
          @update:model-value="onReadingModeChange"
        >
          <template #item="{ props: itemProps, item }">
            <VListItem v-bind="itemProps">
              <template #subtitle>{{ item.raw.description }}</template>
            </VListItem>
          </template>
        </VSelect>

        <VFileInput
          v-model="files"
          multiple
          show-size
          counter
          chips
          :label="isAddFilesMode ? 'Select Files to Add' : 'Select Files to Upload'"
          placeholder="Choose files or drag and drop"
          prepend-icon="tabler-paperclip"
          variant="outlined"
          :accept="allowedExtensions.join(',')"
          class="mb-4"
          :disabled="isUploading"
          @update:model-value="onFilesSelected"
        />

        <VAlert type="info" variant="tonal" class="mb-4">
          <template v-if="isAddFilesMode">
            You can upload up to {{ MAX_FILES }} files at once. Supported file types: {{ supportedTypesText }}. These
            files will be added to the existing source.
          </template>
          <template v-else>
            Choose a descriptive name for your data source (max 30 characters). You can upload up to
            {{ MAX_FILES }} files at once. Supported file types: {{ supportedTypesText }}.
          </template>
        </VAlert>

        <VAlert v-if="errors.length > 0" type="warning" variant="tonal" class="mb-4">
          <ul class="mb-0">
            <li v-for="err in errors" :key="err">{{ err }}</li>
          </ul>
        </VAlert>

        <div v-if="isUploading" class="mb-4">
          <div class="d-flex align-center justify-space-between mb-2">
            <span class="text-body-1">Uploading files...</span>
            <span class="text-body-2 text-medium-emphasis">{{ progress.current }}/{{ progress.total }}</span>
          </div>
          <VProgressLinear
            :model-value="progress.total > 0 ? (progress.current / progress.total) * 100 : 0"
            color="primary"
            height="6"
            rounded
          />
        </div>

        <div v-if="files.length > 0" class="selected-files">
          <h6 class="text-h6 mb-3">Selected Files ({{ files.length }})</h6>
          <div class="d-flex flex-column gap-2">
            <div
              v-for="(file, index) in files"
              :key="`${file.name}-${file.lastModified}`"
              class="d-flex align-center justify-space-between pa-3 bg-surface rounded border"
            >
              <div class="d-flex align-center">
                <VIcon :icon="getFileIcon(file.name)" size="20" class="me-3" />
                <div>
                  <div class="text-body-1">{{ file.name }}</div>
                  <div class="text-caption text-medium-emphasis">{{ formatFileSize(file.size) }}</div>
                </div>
              </div>
              <VBtn icon size="small" variant="text" :disabled="isUploading" @click="removeFile(index)">
                <VIcon icon="tabler-x" size="16" />
              </VBtn>
            </div>
          </div>
        </div>
      </VCardText>

      <VCardActions class="pa-4">
        <VSpacer />
        <VBtn variant="tonal" :disabled="isUploading" @click="close">Cancel</VBtn>
        <VBtn
          color="primary"
          :loading="isUploading"
          :disabled="files.length === 0 || (!isAddFilesMode && !sourceName.trim()) || isUploading"
          @click="submit"
        >
          <span v-if="isUploading">Uploading... ({{ progress.current }}/{{ progress.total }})</span>
          <span v-else>{{ isAddFilesMode ? 'Add Files' : 'Upload & Process Files' }}</span>
        </VBtn>
      </VCardActions>
    </VCard>
  </VDialog>
</template>
