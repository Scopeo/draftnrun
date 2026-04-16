<script setup lang="ts">
import { ref, watch } from 'vue'
import { logger } from '@/utils/logger'
import { useCreateIngestionTaskMutation } from '@/composables/queries/useDataSourcesQuery'
import { getErrorMessage } from '@/composables/useDataSources'
import { useNotifications } from '@/composables/useNotifications'
import { useTracking } from '@/composables/useTracking'
import { googleDriveService } from '@/services/googleDrive'

const props = defineProps<{
  modelValue: boolean
  orgId: string | undefined
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  created: []
}>()

const { notify } = useNotifications()
const { trackButtonClick, trackModalOpen, trackModalClose } = useTracking()
const createIngestionTaskMutation = useCreateIngestionTaskMutation()

const isConnecting = ref(false)
const showFormDialog = ref(false)
const pendingData = ref<{ folderInfo: { id: string; name: string } | null; accessToken: string } | null>(null)

const form = ref({ source_name: '', chunk_size: 1024 })
const formErrors = ref<Record<string, string>>({})

const resetForm = () => {
  form.value = { source_name: '', chunk_size: 1024 }
  formErrors.value = {}
}

watch(
  () => props.modelValue,
  open => {
    if (open) resetForm()
  }
)

const closeConnect = () => emit('update:modelValue', false)

const connectAndPickFolder = async () => {
  trackButtonClick('connect-google-drive', 'data-sources-header')
  try {
    isConnecting.value = true
    await googleDriveService.initialize()

    const response = await googleDriveService.authenticate()

    emit('update:modelValue', false)

    const selectedFolder = await googleDriveService.openFolderPicker(response.access_token)
    if (selectedFolder !== null) {
      pendingData.value = { folderInfo: selectedFolder, accessToken: response.access_token }

      const name = selectedFolder ? `Google Drive - ${selectedFolder.name}` : 'Google Drive - Root Folder'

      resetForm()
      form.value.source_name = name
      showFormDialog.value = true
      trackModalOpen('google-drive-form-dialog', 'folder-selected')
    }
  } catch (error: unknown) {
    logger.error('Error connecting to Google Drive', { error })
  } finally {
    isConnecting.value = false
  }
}

const validate = () => {
  const errors: Record<string, string> = {}
  if (!form.value.source_name.trim()) errors.source_name = 'Source name is required'
  formErrors.value = errors
  return Object.keys(errors).length === 0
}

const submitForm = async () => {
  if (!validate() || !pendingData.value || !props.orgId) return
  try {
    const payload = {
      source_name: form.value.source_name,
      source_type: 'google_drive',
      status: 'pending',
      source_attributes: {
        access_token: pendingData.value.accessToken,
        folder_id: pendingData.value.folderInfo?.id || 'root',
        folder_name: pendingData.value.folderInfo?.name || 'Root Folder',
        chunk_size: form.value.chunk_size,
      },
    }

    await createIngestionTaskMutation.mutateAsync({ orgId: props.orgId, payload })
    trackButtonClick('google-drive-source-created', 'google-drive-form', {
      folder_name: pendingData.value.folderInfo?.name,
      chunk_size: form.value.chunk_size,
    })
    showFormDialog.value = false
    trackModalClose('google-drive-form-dialog')
    pendingData.value = null
    resetForm()
    emit('created')
  } catch (error: unknown) {
    logger.error('Error submitting Google Drive form', { error })
    notify.error(getErrorMessage(error, 'Failed to connect Google Drive. Please try again.'))
  }
}
</script>

<template>
  <!-- Step 1: Connect Dialog -->
  <VDialog :model-value="modelValue" max-width="var(--dnr-dialog-sm)" @update:model-value="closeConnect">
    <VCard>
      <VCardTitle class="text-h6 pa-4">Connect Google Drive</VCardTitle>
      <VCardText>
        <p class="mb-4">Connect your Google Drive to access and manage your files directly from our application.</p>
        <VAlert type="info" variant="tonal" class="mb-4">
          We'll only request read access to your files and open the native Google Drive picker to select a folder.
        </VAlert>
      </VCardText>
      <VCardActions class="pa-4">
        <VSpacer />
        <VBtn variant="tonal" @click="closeConnect">Cancel</VBtn>
        <VBtn color="primary" :loading="isConnecting" @click="connectAndPickFolder">Connect & Select Folder</VBtn>
      </VCardActions>
    </VCard>
  </VDialog>

  <!-- Step 2: Configure Source Dialog -->
  <VDialog v-model="showFormDialog" max-width="var(--dnr-dialog-sm)" persistent>
    <VCard>
      <VCardTitle class="text-h6 pa-4 d-flex align-center">
        <VIcon icon="tabler-brand-google-drive" class="me-2" />
        Configure Google Drive Source
      </VCardTitle>
      <VCardText class="pa-4 dnr-form-compact">
        <VForm @submit.prevent="submitForm">
          <VRow>
            <VCol cols="12">
              <VTextField
                v-model="form.source_name"
                label="Source Name *"
                placeholder="e.g. Google Drive - Documents"
                :error-messages="formErrors.source_name"
              />
            </VCol>
            <VCol cols="12">
              <VTextField v-model.number="form.chunk_size" label="Chunk Size" type="number" placeholder="1024" />
              <VCardText class="text-caption text-medium-emphasis pa-0 mt-1">
                Size of text chunks for processing (optional, default: 1024)
              </VCardText>
            </VCol>
          </VRow>
        </VForm>
      </VCardText>
      <VCardActions class="pa-4">
        <VSpacer />
        <VBtn variant="tonal" @click="showFormDialog = false">Cancel</VBtn>
        <VBtn color="primary" @click="submitForm">Create Source</VBtn>
      </VCardActions>
    </VCard>
  </VDialog>
</template>

<style lang="scss">
/* stylelint-disable selector-pseudo-class-no-unknown */
:deep(.picker-dialog) {
  position: fixed !important;
  z-index: 99999 !important;
}

:deep(.picker-dialog-bg) {
  z-index: 99998 !important;
}

:deep(div[role='dialog']) {
  position: fixed !important;
  z-index: 99999 !important;
}

:deep(.picker-frame) {
  position: fixed !important;
  z-index: 99999 !important;
}

:deep(iframe[src*='picker']) {
  position: fixed !important;
  z-index: 99999 !important;
}

:deep(div[style*='z-index']) {
  &[style*='1000'] {
    position: fixed !important;
    z-index: 99999 !important;
  }
}

:deep(.v-navigation-drawer),
:deep(.layout-nav-drawer),
:deep(.sidebar),
:deep([class*='sidebar']) {
  z-index: 1000 !important;
}
/* stylelint-enable selector-pseudo-class-no-unknown */
</style>
