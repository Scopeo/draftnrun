<script setup lang="ts">
import { ref, watch } from 'vue'
import { logger } from '@/utils/logger'
import { useCreateIngestionTaskMutation } from '@/composables/queries/useDataSourcesQuery'
import { getErrorMessage } from '@/composables/useDataSources'
import { useNotifications } from '@/composables/useNotifications'
import { useTracking } from '@/composables/useTracking'

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

const form = ref({
  source_name: '',
  source_db_url: '',
  source_table_name: '',
  id_column_name: '',
  text_column_names: [] as string[],
  source_schema_name: '',
  metadata_column_names: [] as string[],
  timestamp_column_name: '',
  url_pattern: '',
  chunk_size: 1024,
  chunk_overlap: 0,
  update_existing: false,
  query_filter: '',
  timestamp_filter: '',
})

const formErrors = ref<Record<string, string>>({})

const reset = () => {
  form.value = {
    source_name: '',
    source_db_url: '',
    source_table_name: '',
    id_column_name: '',
    text_column_names: [],
    source_schema_name: '',
    metadata_column_names: [],
    timestamp_column_name: '',
    url_pattern: '',
    chunk_size: 1024,
    chunk_overlap: 0,
    update_existing: false,
    query_filter: '',
    timestamp_filter: '',
  }
  formErrors.value = {}
}

watch(
  () => props.modelValue,
  open => {
    if (open) {
      reset()
      trackModalOpen('database-connection-dialog', 'data-sources-header')
    }
  }
)

const validate = () => {
  const errors: Record<string, string> = {}
  if (!form.value.source_name.trim()) errors.source_name = 'Source name is required'
  if (!form.value.source_db_url.trim()) errors.source_db_url = 'Database URL is required'
  if (!form.value.source_table_name.trim()) errors.source_table_name = 'Table name is required'
  if (!form.value.id_column_name.trim()) errors.id_column_name = 'ID column name is required'
  if (form.value.text_column_names.length === 0) errors.text_column_names = 'At least one text column is required'
  formErrors.value = errors
  return Object.keys(errors).length === 0
}

const close = () => emit('update:modelValue', false)

const submit = async () => {
  if (!validate() || !props.orgId) return
  try {
    isConnecting.value = true

    const payload = {
      source_name: form.value.source_name,
      source_type: 'database',
      status: 'pending',
      source_attributes: {
        source_db_url: form.value.source_db_url,
        source_table_name: form.value.source_table_name,
        id_column_name: form.value.id_column_name,
        text_column_names: form.value.text_column_names,
        source_schema_name: form.value.source_schema_name || null,
        metadata_column_names: form.value.metadata_column_names.length > 0 ? form.value.metadata_column_names : null,
        timestamp_column_name: form.value.timestamp_column_name || null,
        url_pattern: form.value.url_pattern || null,
        chunk_size: form.value.chunk_size,
        chunk_overlap: form.value.chunk_overlap,
        update_existing: form.value.update_existing,
        query_filter: form.value.query_filter || null,
        timestamp_filter: form.value.timestamp_filter || null,
      },
    }

    await createIngestionTaskMutation.mutateAsync({ orgId: props.orgId, payload })
    trackButtonClick('database-source-created', 'database-form', {
      source_type: 'database',
      table_name: form.value.source_table_name,
      chunk_size: form.value.chunk_size,
      text_columns_count: form.value.text_column_names.length,
    })
    close()
    trackModalClose('database-connection-dialog')
    emit('created')
  } catch (error: unknown) {
    logger.error('Error connecting database', { error })
    notify.error(getErrorMessage(error, 'Failed to connect database. Please try again.'))
  } finally {
    isConnecting.value = false
  }
}
</script>

<template>
  <VDialog :model-value="modelValue" max-width="var(--dnr-dialog-md)" persistent @update:model-value="close">
    <VCard>
      <VCardTitle class="text-h6 pa-4 d-flex align-center">
        <VIcon icon="tabler-database" class="me-2" />
        Connect Database
      </VCardTitle>

      <VCardText class="pa-4 dnr-form-compact">
        <VForm @submit.prevent="submit">
          <VRow>
            <VCol cols="12">
              <VTextField
                v-model="form.source_name"
                label="Source Name *"
                placeholder="e.g. Customer Database"
                :error-messages="formErrors.source_name"
              />
            </VCol>
            <VCol cols="12">
              <VTextField
                v-model="form.source_db_url"
                label="Database URL *"
                placeholder="postgresql://user:password@host:port/database"
                :error-messages="formErrors.source_db_url"
              />
            </VCol>
            <VCol cols="12" md="6">
              <VTextField v-model="form.source_schema_name" label="Schema Name" placeholder="public" />
            </VCol>
            <VCol cols="12" md="6">
              <VTextField
                v-model="form.source_table_name"
                label="Table Name *"
                placeholder="users"
                :error-messages="formErrors.source_table_name"
              />
            </VCol>
            <VCol cols="12" md="6">
              <VTextField
                v-model="form.id_column_name"
                label="ID Column Name *"
                placeholder="id"
                :error-messages="formErrors.id_column_name"
              />
            </VCol>
            <VCol cols="12" md="6">
              <VTextField v-model="form.timestamp_column_name" label="Timestamp Column" placeholder="created_at" />
            </VCol>
            <VCol cols="12">
              <VCombobox
                v-model="form.text_column_names"
                label="Text Columns *"
                placeholder="Enter column names (e.g. title, description)"
                multiple
                chips
                clearable
                :error-messages="formErrors.text_column_names"
              />
              <VCardText class="text-caption text-medium-emphasis pa-0 mt-1">
                These columns contain the text content to be indexed. Press <kbd>Enter</kbd> to add each column name.
              </VCardText>
            </VCol>
            <VCol cols="12">
              <VCombobox
                v-model="form.metadata_column_names"
                label="Metadata Columns"
                placeholder="Enter metadata column names (e.g. category, tags)"
                multiple
                chips
                clearable
              />
              <VCardText class="text-caption text-medium-emphasis pa-0 mt-1">
                Additional columns to include as metadata (optional). Press <kbd>Enter</kbd> to add each column name.
              </VCardText>
            </VCol>
            <VCol cols="12">
              <VTextField
                v-model="form.url_pattern"
                label="URL Pattern"
                placeholder="https://shop.example.com/products/{category}/{product_id}-details.html"
                hint="Enter the URL pattern that will be used to build links. Enter a URL pattern with placeholders wrapped in { }. Each placeholder must match a column name in your data. You can add any text, prefixes, or suffixes around the placeholders. Example: https://shop.example.com/products/{category}/{product_id}-details.html → If category=books and product_id=456, the final URL becomes https://shop.example.com/products/books/456-details.html"
                persistent-hint
              />
            </VCol>
            <VCol cols="12" md="6">
              <VTextField v-model.number="form.chunk_size" label="Chunk Size" type="number" placeholder="1024" />
            </VCol>
            <VCol cols="12" md="6">
              <VTextField v-model.number="form.chunk_overlap" label="Chunk Overlap" type="number" placeholder="0" />
            </VCol>
            <VCol cols="12">
              <VTextField v-model="form.query_filter" label="Query Filter" placeholder="status = 'active'" />
              <VCardText class="text-caption text-medium-emphasis pa-0 mt-1">
                Optional SQL WHERE clause to filter data (e.g., "status = 'active'"). Do not include the WHERE keyword.
              </VCardText>
            </VCol>
            <VCol cols="12">
              <VCheckbox v-model="form.update_existing" label="Update existing data" color="primary" />
              <VCardText class="text-caption text-medium-emphasis pa-0 mt-n2">
                If enabled, this will update existing data with new information when re-ingesting.
              </VCardText>
            </VCol>
            <VCol cols="12">
              <VTextField v-model="form.timestamp_filter" label="Timestamp Filter" placeholder="> '2023-01-01'" />
              <VCardText class="text-caption text-medium-emphasis pa-0 mt-1">
                Optional SQL WHERE clause to filter data by timestamp (e.g., "> '2023-01-01'"). Do not include the WHERE
                keyword.
              </VCardText>
            </VCol>
          </VRow>
        </VForm>
      </VCardText>

      <VCardActions class="pa-4">
        <VSpacer />
        <VBtn variant="tonal" @click="close">Cancel</VBtn>
        <VBtn color="primary" :loading="isConnecting" @click="submit">Connect Database</VBtn>
      </VCardActions>
    </VCard>
  </VDialog>
</template>
