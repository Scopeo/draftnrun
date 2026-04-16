<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { logger } from '@/utils/logger'
import { useCreateCronJobMutation, useCronJobsQuery } from '@/composables/queries/useCronJobsQuery'
import { useSelectedOrg } from '@/composables/useSelectedOrg'
import CronFrequencySelector from '@/components/cron/CronFrequencySelector.vue'
import CronJobCard from '@/components/cron/CronJobCard.vue'
import InfoPopover from '@/components/shared/InfoPopover.vue'
import {
  CronEntrypoint,
  type CronJobCreate,
  type EndpointPollingPayload,
  EnvType,
  type FrequencyConfig,
} from '@/types/cron'

interface Props {
  isDialogVisible: boolean
  projectId: string
}

interface Emit {
  (e: 'update:isDialogVisible', value: boolean): void
  (e: 'created', cronJob: any): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emit>()

const { selectedOrgId } = useSelectedOrg()

// TanStack Query hooks
const { data: cronJobs, isLoading: loading, refetch: fetchCronJobs } = useCronJobsQuery(selectedOrgId)
const createCronJobMutation = useCreateCronJobMutation()

// Modal state
const activeTab = ref<'create' | 'existing'>('create')
const errorMessage = ref<string | null>(null)

// Form state
const name = ref('')
const cronExpression = ref('')
const cronDescription = ref('')
const frequencyConfig = ref<FrequencyConfig>()
const timezone = ref(Intl.DateTimeFormat().resolvedOptions().timeZone)

// Endpoint polling specific fields
const endpointUrl = ref('')
const idFieldPath = ref('')
const filterFields = ref<Record<string, string>>({})
const headers = ref<Record<string, string>>({})
const timeout = ref(30)
const workflowInputTemplate = ref('')
const trackHistory = ref(true)

// Filter fields management
interface FilterFieldEntry {
  id: string
  fieldPath: string
  value: string
}

interface HeaderEntry {
  id: string
  name: string
  value: string
}

const filterFieldsList = ref<FilterFieldEntry[]>([])
const headersList = ref<HeaderEntry[]>([])

// Add filter field
const addFilterField = () => {
  filterFieldsList.value.push({
    id: `filter_${Date.now()}`,
    fieldPath: '',
    value: '',
  })
}

// Remove filter field
const removeFilterField = (id: string) => {
  filterFieldsList.value = filterFieldsList.value.filter(f => f.id !== id)
}

// Update filter fields object
watch(
  filterFieldsList,
  () => {
    filterFields.value = {}
    filterFieldsList.value.forEach(entry => {
      if (entry.fieldPath.trim() && entry.value.trim()) {
        filterFields.value[entry.fieldPath.trim()] = entry.value.trim()
      }
    })
  },
  { deep: true }
)

// Add header
const addHeader = () => {
  headersList.value.push({
    id: `header_${Date.now()}`,
    name: '',
    value: '',
  })
}

// Remove header
const removeHeader = (id: string) => {
  headersList.value = headersList.value.filter(h => h.id !== id)
}

// Update headers object
watch(
  headersList,
  () => {
    headers.value = {}
    headersList.value.forEach(entry => {
      if (entry.name.trim() && entry.value.trim()) {
        headers.value[entry.name.trim()] = entry.value.trim()
      }
    })
  },
  { deep: true }
)

// Validation
const isFormValid = computed(() => {
  return (
    name.value.trim() !== '' &&
    cronExpression.value !== '' &&
    endpointUrl.value.trim() !== '' &&
    idFieldPath.value.trim() !== ''
  )
})

// Handle frequency change
const onFrequencyChange = (expr: string, description: string) => {
  cronExpression.value = expr
  cronDescription.value = description
}

// Reset form
const resetForm = () => {
  name.value = ''
  cronExpression.value = ''
  cronDescription.value = ''
  endpointUrl.value = ''
  headers.value = {}
  headersList.value = []
  idFieldPath.value = ''
  filterFields.value = {}
  filterFieldsList.value = []
  timeout.value = 30
  workflowInputTemplate.value = ''
  trackHistory.value = true
  activeTab.value = 'create'
  errorMessage.value = null
}

// Create cron job
const onSubmit = async () => {
  if (!isFormValid.value || !selectedOrgId.value) {
    return
  }

  // Clear any previous errors
  errorMessage.value = null

  try {
    // Build payload object according to EndpointPollingPayload interface
    const payload: EndpointPollingPayload = {
      endpoint_url: endpointUrl.value.trim(),
      tracking_field_path: idFieldPath.value.trim(),
      timeout: timeout.value,
      track_history: trackHistory.value,
      workflow_input: {
        project_id: props.projectId,
        env: EnvType.PRODUCTION,
        input_data: {},
      },
    }

    // Only include workflow_input_template if it's provided, otherwise backend will use the item as-is
    if (workflowInputTemplate.value.trim()) {
      payload.workflow_input_template = workflowInputTemplate.value.trim()
    }

    // Only include filter_fields if it has values
    if (Object.keys(filterFields.value).length > 0) {
      payload.filter_fields = filterFields.value
    }

    // Only include headers if it has values
    if (Object.keys(headers.value).length > 0) {
      payload.headers = headers.value
    }

    const cronJobData: CronJobCreate = {
      name: name.value,
      cron_expr: cronExpression.value,
      tz: timezone.value,
      entrypoint: CronEntrypoint.ENDPOINT_POLLING,
      payload,
    }

    logger.info('[EndpointPollingModal] Submitting cron job', { data: cronJobData })

    const newCronJob = await createCronJobMutation.mutateAsync({
      orgId: selectedOrgId.value,
      cronJobData,
    })

    // Success - emit event and switch to existing tab
    emit('created', newCronJob)
    resetForm()
    activeTab.value = 'existing'
  } catch (err: unknown) {
    logger.error('[EndpointPollingModal] Error creating cron job', { error: err })

    let message = 'Failed to create trigger. Please try again.'

    if (err instanceof Error) {
      message = err.message.replace(/^FetchError:\s*/i, '')
    } else if (typeof err === 'string') {
      message = err
    }

    errorMessage.value = message

    // Scroll to show error message (which is above submit button)
    setTimeout(() => {
      // Find the error alert element
      const errorAlert = document.querySelector('.v-window-item[value="create"] .v-alert[type="error"]')
      if (errorAlert) {
        errorAlert.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
      } else {
        // Fallback: scroll the card actions (submit button) into view
        const cardActions = document.querySelector('.v-window-item[value="create"] .v-card-actions')
        if (cardActions) {
          cardActions.scrollIntoView({ behavior: 'smooth', block: 'end' })
        }
      }
    }, 100)
  }
}

// Close modal
const close = () => {
  emit('update:isDialogVisible', false)
  resetForm()
}

// Filter cron jobs for current project and entrypoint (only show endpoint polling jobs)
const projectCronJobs = computed(() => {
  if (!cronJobs.value) return []
  return cronJobs.value.filter(cron => {
    const payload = cron.payload as any
    // Only show endpoint polling jobs for this project
    // For endpoint polling, project_id is nested in workflow_input
    const projectId = payload?.workflow_input?.project_id || payload?.project_id
    return projectId === props.projectId && cron.entrypoint === CronEntrypoint.ENDPOINT_POLLING
  })
})

// Fetch cron jobs when modal opens
watch(
  () => props.isDialogVisible,
  visible => {
    if (visible && selectedOrgId.value) {
      fetchCronJobs()
      // Clear any error messages when modal opens
      errorMessage.value = null
    }
  }
)
</script>

<template>
  <VDialog
    :model-value="props.isDialogVisible"
    max-width="900px"
    persistent
    scrollable
    @update:model-value="val => emit('update:isDialogVisible', val)"
  >
    <VCard>
      <VCardTitle class="d-flex justify-space-between align-center">
        <span class="text-h6">Trigger on Event</span>
        <VBtn icon="tabler-x" variant="text" size="small" @click="close" />
      </VCardTitle>

      <VDivider />

      <!-- Tabs -->
      <VTabs v-model="activeTab" class="v-tabs-pill ms-2">
        <VTab value="create">
          <VIcon icon="tabler-plus" start />
          Create New
        </VTab>
        <VTab value="existing">
          <VIcon icon="tabler-list" start />
          Existing Triggers
          <VChip v-if="projectCronJobs.length > 0" size="small" color="primary" class="ms-2">
            {{ projectCronJobs.length }}
          </VChip>
        </VTab>
      </VTabs>

      <VDivider />

      <VWindow v-model="activeTab">
        <!-- Create New Trigger -->
        <VWindowItem value="create">
          <VCardText class="scrollable-content">
            <!-- Explanatory text -->
            <VAlert type="info" variant="tonal" class="mb-6">
              <template #text>
                <div class="text-body-2">
                  <strong>What is a Trigger on Event?</strong>
                  <br />
                  This trigger monitors an API endpoint at regular intervals and automatically runs your workflow when
                  new items are detected. It polls the endpoint, tracks which items have already been processed, and
                  triggers your workflow for any new items that appear.
                </div>
              </template>
            </VAlert>

            <VForm @submit.prevent="onSubmit">
              <!-- Name -->
              <div class="mb-6">
                <VTextField
                  v-model="name"
                  label="Trigger Name *"
                  placeholder="e.g., Track API Items Daily"
                  variant="outlined"
                  density="compact"
                  :rules="[v => !!v || 'Name is required']"
                />
              </div>

              <!-- Frequency Selector -->
              <div class="mb-6">
                <CronFrequencySelector v-model="frequencyConfig" @cron-expression="onFrequencyChange" />
              </div>

              <!-- Endpoint URL -->
              <div class="mb-6">
                <VTextField
                  v-model="endpointUrl"
                  label="Endpoint URL *"
                  placeholder="https://api.example.com/items"
                  variant="outlined"
                  density="compact"
                  :rules="[v => !!v || 'Endpoint URL is required']"
                  hint="The API endpoint URL to check for new items"
                  persistent-hint
                />
              </div>

              <!-- Track History Toggle -->
              <div class="mb-6">
                <div class="d-flex align-center mb-1">
                  <span class="text-body-2 text-high-emphasis"> Track History </span>
                  <InfoPopover class="ms-2">
                    When enabled (default), the trigger automatically tracks which items are new and processes only
                    those it hasn't seen before. Disable this option if you don't want the trigger to track new items—in
                    that case, it will process all items every time it runs. This is especially useful for endpoints
                    that are already filtered (for example, by tags or lists). If your API returns only items with
                    status="pending" and your workflow updates them to completed, additional history tracking isn't
                    necessary. Disabling it also allows items to be retriggered if they later move back to a pending
                    state.
                  </InfoPopover>
                </div>
                <VSwitch v-model="trackHistory" color="primary" density="compact" hide-details />
              </div>

              <!-- ID Field Path -->
              <div class="mb-6">
                <VTextField
                  v-model="idFieldPath"
                  label="ID Field Path *"
                  placeholder="e.g., id or [].id or data[].id"
                  variant="outlined"
                  density="compact"
                  :rules="[v => !!v || 'ID field path is required']"
                  hint="Path to the unique identifier field in your API response"
                  persistent-hint
                />
                <VAlert type="info" variant="tonal" density="compact" class="mt-2">
                  <template #text>
                    <div class="text-caption">
                      <strong>How to use this:</strong> You can use either simple paths or array notation. The system
                      auto-converts simple paths for root-level arrays.<br /><br />
                      <strong>For root-level arrays:</strong> If your response is directly an array like:
                      <pre class="mt-2 mb-2 pa-2 code-example">
[
  { "id": "123", "name": "Item 1" },
  { "id": "456", "name": "Item 2" }
]</pre
                      >
                      Use: <code>id</code> or <code>[].id</code> (both work)<br /><br />
                      <strong>For nested arrays:</strong> If your response has a nested structure like:
                      <pre class="mt-2 mb-2 pa-2 code-example">
{
  "data": [
    { "id": "123", "name": "Item 1" },
    { "id": "456", "name": "Item 2" }
  ]
}</pre
                      >
                      Use: <code>data[].id</code><br /><br />
                      <strong>Note:</strong> Simple paths like <code>id</code> are automatically converted to
                      <code>[].id</code> for root-level arrays.
                    </div>
                  </template>
                </VAlert>
              </div>

              <!-- Filter Fields -->
              <div class="mb-6">
                <div class="d-flex justify-space-between align-center mb-2">
                  <div>
                    <label class="text-sm font-weight-medium">Filter Fields</label>
                    <div class="text-caption text-medium-emphasis">
                      Optional - Only track items that match these conditions
                    </div>
                  </div>
                  <VBtn variant="outlined" prepend-icon="tabler-plus" size="small" @click="addFilterField">
                    Add Filter
                  </VBtn>
                </div>
                <VCard v-for="entry in filterFieldsList" :key="entry.id" variant="outlined" class="mb-2">
                  <VCardText>
                    <div class="d-flex gap-2 align-center">
                      <VTextField
                        v-model="entry.fieldPath"
                        label="Field Path"
                        placeholder="e.g., status or [].status or data[].status"
                        variant="outlined"
                        density="compact"
                        class="flex-grow-1"
                        hint="Use simple paths (e.g., 'status') or array notation (e.g., '[].status')"
                        persistent-hint
                      />
                      <VTextField
                        v-model="entry.value"
                        label="Value to Match"
                        placeholder="e.g., processing"
                        variant="outlined"
                        density="compact"
                        class="flex-grow-1"
                        hint="The value this field must have"
                        persistent-hint
                      />
                      <VBtn
                        icon="tabler-trash"
                        size="small"
                        variant="text"
                        color="error"
                        @click="removeFilterField(entry.id)"
                      />
                    </div>
                  </VCardText>
                </VCard>
                <VAlert v-if="filterFieldsList.length === 0" type="info" variant="tonal" density="compact">
                  <template #text>
                    <div class="text-caption">
                      <strong>Example:</strong> If you only want to track items with status "processing", add a filter
                      with: <br />• Field Path: <code>status</code> or <code>[].status</code> (for root-level arrays)
                      <br />• Field Path: <code>data[].status</code> (for nested arrays) <br />• Value:
                      <code>processing</code><br /><br />
                      <strong>Note:</strong> Simple paths like <code>status</code> are automatically converted to
                      <code>[].status</code> for root-level arrays, just like the ID Field Path.
                    </div>
                  </template>
                </VAlert>
              </div>

              <!-- Headers -->
              <div class="mb-6">
                <div class="d-flex justify-space-between align-center mb-2">
                  <div>
                    <label class="text-sm font-weight-medium">HTTP Headers</label>
                    <div class="text-caption text-medium-emphasis">Optional - For API authentication</div>
                  </div>
                  <VBtn variant="outlined" prepend-icon="tabler-plus" size="small" @click="addHeader">
                    Add Header
                  </VBtn>
                </div>
                <VCard v-for="entry in headersList" :key="entry.id" variant="outlined" class="mb-2">
                  <VCardText>
                    <div class="d-flex gap-2 align-center">
                      <VTextField
                        v-model="entry.name"
                        label="Header Name"
                        placeholder="e.g., Authorization"
                        variant="outlined"
                        density="compact"
                        class="flex-grow-1"
                        hint="Standard HTTP header name"
                        persistent-hint
                      />
                      <VTextField
                        v-model="entry.value"
                        label="Header Value"
                        placeholder="e.g., Bearer your-token-here"
                        variant="outlined"
                        density="compact"
                        class="flex-grow-1"
                        hint="The header value"
                        persistent-hint
                      />
                      <VBtn
                        icon="tabler-trash"
                        size="small"
                        variant="text"
                        color="error"
                        @click="removeHeader(entry.id)"
                      />
                    </div>
                  </VCardText>
                </VCard>
                <VAlert v-if="headersList.length === 0" type="info" variant="tonal" density="compact">
                  <template #text>
                    <div class="text-caption">
                      <strong>Common headers:</strong>
                      <br />• <code>Authorization</code> → <code>Bearer your-api-token</code> <br />•
                      <code>X-API-Key</code> → <code>your-api-key</code> <br />• <code>Content-Type</code> →
                      <code>application/json</code>
                    </div>
                  </template>
                </VAlert>
              </div>

              <!-- Timeout -->
              <div class="mb-6">
                <VTextField
                  v-model.number="timeout"
                  label="Timeout (seconds)"
                  type="number"
                  variant="outlined"
                  density="compact"
                  :rules="[v => v > 0 || 'Timeout must be greater than 0']"
                  hint="How long to wait for the API response (default: 30 seconds)"
                  persistent-hint
                />
              </div>

              <!-- Workflow Input Template -->
              <div class="mb-6">
                <VTextarea
                  v-model="workflowInputTemplate"
                  label="Input to be used by the workflow"
                  placeholder="e.g., Process item: {item} or Process {item.name} with status {item.step}"
                  variant="outlined"
                  density="compact"
                  rows="3"
                  hint="If left empty, defaults to just the item JSON"
                  persistent-hint
                />
                <VAlert type="info" variant="tonal" density="compact" class="mt-2">
                  <template #text>
                    <div class="text-caption">
                      <strong>Template syntax:</strong> Template for the workflow input message. Use
                      <code>{item}</code> for the full item (JSON), or <code>{item.key}</code> to access specific fields
                      (e.g., <code>{item.name}</code>, <code>{item.step}</code>). If None, defaults to just the item
                      JSON. <br /><strong>Examples:</strong> <br />• <code>Process item: {item}</code> - Sends the
                      entire item as JSON <br />• <code>Process {item.name} with status {item.step}</code> - Accesses
                      specific fields from the item <br />• <code>New application: {item.id} - {item.name}</code> -
                      Combines multiple fields
                    </div>
                  </template>
                </VAlert>
              </div>

              <!-- Timezone Info -->
              <VAlert type="info" variant="tonal" class="mb-4">
                <template #text>
                  <div class="text-caption">
                    <strong>Timezone:</strong> {{ timezone }} (auto-detected from your browser)
                  </div>
                </template>
              </VAlert>

              <!-- Production Environment Info -->
              <VAlert type="info" variant="tonal">
                <template #text>
                  <div class="text-caption">
                    <strong>Note:</strong> Scheduled jobs will run on the production deployment of this workflow.
                  </div>
                </template>
              </VAlert>
            </VForm>
          </VCardText>

          <VDivider />

          <!-- Error Message - positioned right above submit button for visibility -->
          <VCardText v-if="errorMessage" class="pt-4 pb-2">
            <VAlert type="error" variant="tonal" closable @click:close="errorMessage = null">
              <template #prepend>
                <VIcon icon="tabler-alert-circle" />
              </template>
              <div class="text-body-2">
                <strong>Error creating trigger:</strong><br />
                {{ errorMessage }}
              </div>
            </VAlert>
          </VCardText>

          <VCardActions>
            <VSpacer />
            <VBtn color="grey" @click="close"> Cancel </VBtn>
            <VBtn
              color="primary"
              :disabled="!isFormValid || createCronJobMutation.isPending.value"
              :loading="createCronJobMutation.isPending.value"
              @click="onSubmit"
            >
              Create Trigger
            </VBtn>
          </VCardActions>
        </VWindowItem>

        <!-- Existing Triggers -->
        <VWindowItem value="existing">
          <VCardText class="scrollable-content">
            <!-- Loading State -->
            <div v-if="loading" class="text-center py-8">
              <VProgressCircular indeterminate color="primary" />
              <div class="text-body-2 mt-4">Loading triggers...</div>
            </div>

            <!-- Empty State -->
            <div v-else-if="projectCronJobs.length === 0" class="text-center py-8">
              <VIcon icon="tabler-calendar-x" size="64" color="grey" class="mb-4" />
              <div class="text-h6 mb-2">No Triggers on Event</div>
              <div class="text-body-2 text-medium-emphasis mb-4">
                You haven't created any triggers on event for this project yet.
              </div>
              <VBtn color="primary" @click="activeTab = 'create'"> Create First Trigger </VBtn>
            </div>

            <!-- Triggers List -->
            <div v-else class="d-flex flex-column gap-3">
              <CronJobCard
                v-for="cronJob in projectCronJobs"
                :key="cronJob.id"
                :cron-job="cronJob"
                @updated="fetchCronJobs"
              />
            </div>
          </VCardText>

          <VDivider />

          <VCardActions>
            <VSpacer />
            <VBtn color="grey" @click="close"> Close </VBtn>
          </VCardActions>
        </VWindowItem>
      </VWindow>
    </VCard>
  </VDialog>
</template>

<style scoped>
pre {
  font-family: 'Courier New', monospace;
  font-size: 11px;
  line-height: 1.4;
  margin: 0;
  overflow-x: auto;
}

code {
  background-color: rgba(var(--v-theme-on-surface), 0.08);
  padding: 2px 6px;
  border-radius: 3px;
  font-family: 'Courier New', monospace;
  font-size: 0.9em;
}

.scrollable-content {
  max-height: 600px;
  overflow-y: auto;
}

.code-example {
  background: rgba(var(--v-theme-surface), 0.5);
  border-radius: 4px;
  font-size: 11px;
}
</style>
