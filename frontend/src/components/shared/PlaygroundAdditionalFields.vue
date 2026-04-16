<script setup lang="ts">
import { ref } from 'vue'
import { logger } from '@/utils/logger'
import { useNotifications } from '@/composables/useNotifications'
import { MAX_FILE_SIZE, readFileContent } from '@/composables/usePlaygroundFiles'
import { getFileIcon } from '@/utils/fileUtils'

defineProps<{
  playgroundFieldTypes: Record<string, string>
  customFieldsData: Record<string, any>
  expandedFields: number[]
}>()

const emit = defineEmits<{
  'update:customFieldsData': [value: Record<string, any>]
  'update:expandedFields': [value: number[]]
}>()

const { notify } = useNotifications()
const customFileInputs = ref<Record<string, HTMLInputElement | null>>({})

const updateField = (fieldName: string, value: any, data: Record<string, any>) => {
  emit('update:customFieldsData', { ...data, [fieldName]: value })
}

const triggerCustomFileInput = (fieldName: string) => {
  customFileInputs.value[fieldName]?.click()
}

const handleCustomFileSelect = async (fieldName: string, event: Event, data: Record<string, any>) => {
  const target = event.target as HTMLInputElement
  const files = target.files
  if (!files?.length) return

  const file = files[0]
  if (file.size > MAX_FILE_SIZE) {
    notify.error(`File too large (max 10 MB). Your file: ${(file.size / 1024 / 1024).toFixed(1)} MB`)
    target.value = ''
    return
  }

  try {
    const fileInfo = await readFileContent(file)
    let base64Data = fileInfo.fileData
    if (base64Data.startsWith('data:')) {
      base64Data = base64Data.substring(base64Data.indexOf(',') + 1)
    } else {
      base64Data = btoa(base64Data)
    }
    updateField(fieldName, { type: 'file', file: { filename: file.name, file_data: base64Data } }, data)
  } catch (error) {
    logger.error(`Error reading file for field ${fieldName}`, { error })
  }
}

const removeCustomFieldFile = (fieldName: string, data: Record<string, any>) => {
  updateField(fieldName, {}, data)

  const input = customFileInputs.value[fieldName]
  if (input) input.value = ''
}
</script>

<template>
  <VExpansionPanels
    :model-value="expandedFields"
    class="mb-3"
    @update:model-value="emit('update:expandedFields', $event as number[])"
  >
    <VExpansionPanel>
      <VExpansionPanelTitle class="text-subtitle-1 font-weight-medium">
        <VIcon icon="tabler-adjustments" class="me-2" size="20" />
        Additional Fields
      </VExpansionPanelTitle>
      <VExpansionPanelText>
        <div class="additional-fields-container">
          <template v-for="(fieldType, fieldName) in playgroundFieldTypes" :key="fieldName">
            <VCard v-if="fieldName !== 'messages'" variant="outlined" class="field-card mb-3">
              <VCardText :class="fieldType === 'simple' ? 'pa-3' : 'pa-4'">
                <!-- JSON Field -->
                <template v-if="fieldType === 'json'">
                  <div class="d-flex justify-space-between align-center mb-3">
                    <label class="text-subtitle-1 font-weight-medium text-primary">
                      {{ fieldName }}
                    </label>
                    <VChip size="small" variant="tonal" color="primary">
                      {{ fieldType }}
                    </VChip>
                  </div>
                  <VTextarea
                    :model-value="
                      typeof customFieldsData[fieldName as string] === 'string'
                        ? customFieldsData[fieldName as string]
                        : JSON.stringify(customFieldsData[fieldName as string], null, 2)
                    "
                    :placeholder="`Enter ${fieldName} (JSON format)...`"
                    variant="outlined"
                    density="compact"
                    rows="4"
                    auto-grow
                    max-rows="8"
                    class="json-field"
                    @update:model-value="updateField(fieldName as string, $event, customFieldsData)"
                  />
                </template>

                <!-- Simple Field -->
                <div v-else-if="fieldType === 'simple'" class="simple-field-wrapper">
                  <label class="text-subtitle-1 font-weight-medium text-primary simple-field-label">
                    {{ fieldName }}
                  </label>
                  <VTextField
                    :model-value="customFieldsData[fieldName as string]"
                    :placeholder="`Enter ${fieldName}...`"
                    variant="outlined"
                    density="compact"
                    hide-details
                    class="simple-field-input"
                    @update:model-value="updateField(fieldName as string, $event, customFieldsData)"
                  />
                </div>

                <!-- File Field -->
                <template v-else-if="fieldType === 'file'">
                  <div class="d-flex justify-space-between align-center mb-3">
                    <label class="text-subtitle-1 font-weight-medium text-primary">
                      {{ fieldName }}
                    </label>
                    <VChip size="small" variant="tonal" color="primary">
                      {{ fieldType }}
                    </VChip>
                  </div>

                  <input
                    :ref="
                      (el: any) => {
                        customFileInputs[fieldName as string] = el as HTMLInputElement
                      }
                    "
                    type="file"
                    accept=".txt,.pdf,.doc,.docx,.md,.png,.jpg,.jpeg,.gif,.webp,.csv,.xls,.xlsx,.xlsm,.json,.xml"
                    style="display: none"
                    @change="(e: Event) => handleCustomFileSelect(fieldName as string, e, customFieldsData)"
                  />

                  <div v-if="!customFieldsData[fieldName as string]?.file?.filename" class="file-upload-area">
                    <VBtn
                      color="primary"
                      variant="outlined"
                      prepend-icon="tabler-upload"
                      @click="triggerCustomFileInput(fieldName as string)"
                    >
                      Upload File
                    </VBtn>
                    <p class="text-caption text-medium-emphasis mt-2 mb-0">
                      Supported formats: PDF, images, text, CSV, Excel, JSON, XML
                    </p>
                  </div>

                  <div v-else class="uploaded-file-preview">
                    <VCard variant="tonal" color="primary" class="file-preview-card">
                      <VCardText class="pa-3">
                        <div class="d-flex align-center gap-2">
                          <VIcon
                            :icon="getFileIcon('', customFieldsData[fieldName as string].file.filename)"
                            size="24"
                            color="primary"
                          />
                          <div>
                            <p class="text-body-2 font-weight-medium mb-0">
                              {{ customFieldsData[fieldName as string].file.filename }}
                            </p>
                            <p class="text-caption text-medium-emphasis mb-0">Ready to send</p>
                          </div>
                        </div>
                        <VBtn
                          icon
                          size="x-small"
                          variant="text"
                          color="error"
                          class="file-remove-btn"
                          @click="removeCustomFieldFile(fieldName as string, customFieldsData)"
                        >
                          <VIcon icon="tabler-x" size="16" />
                        </VBtn>
                      </VCardText>
                    </VCard>
                  </div>
                </template>
              </VCardText>
            </VCard>
          </template>
        </div>
      </VExpansionPanelText>
    </VExpansionPanel>
  </VExpansionPanels>
</template>

<style lang="scss" scoped>
.additional-fields-container .field-card:last-child {
  margin-bottom: 0 !important;
}

.field-card {
  transition: all 0.2s ease;

  &:hover {
    box-shadow: 0 2px 8px rgba(var(--v-theme-on-surface), 0.08);
  }
}

.json-field {
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', 'Consolas', 'source-code-pro', monospace;
  font-size: 13px;

  :deep(textarea) {
    font-family: inherit;
    font-size: 13px;
    line-height: 1.6;
  }
}

.simple-field-wrapper {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  width: 100%;
}

.simple-field-label {
  min-width: 100px;
  flex-shrink: 0;
  white-space: nowrap;
}

.simple-field-input {
  flex: 1 1 200px;
  min-width: 0;
  max-width: 100%;
}

.file-upload-area {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 1.5rem;
  border: 2px dashed rgba(var(--v-theme-primary), 0.3);
  border-radius: 8px;
  background: rgba(var(--v-theme-primary), 0.02);
  transition: all 0.2s ease;

  &:hover {
    border-color: rgba(var(--v-theme-primary), 0.5);
    background: rgba(var(--v-theme-primary), 0.05);
  }
}

.uploaded-file-preview {
  width: 100%;

  .file-preview-card {
    position: relative;
  }

  .file-remove-btn {
    position: absolute;
    top: 8px;
    right: 8px;
  }
}
</style>
