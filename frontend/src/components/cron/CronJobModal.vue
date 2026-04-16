<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { logger } from '@/utils/logger'
import { useCreateCronJobMutation, useCronJobsQuery } from '@/composables/queries/useCronJobsQuery'
import { useSelectedOrg } from '@/composables/useSelectedOrg'
import CronFrequencySelector from '@/components/cron/CronFrequencySelector.vue'
import CronInputDataEditor from '@/components/cron/CronInputDataEditor.vue'
import CronJobCard from '@/components/cron/CronJobCard.vue'
import { CronEntrypoint, type CronJobCreate, EnvType, type FrequencyConfig } from '@/types/cron'

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

// Form state
const name = ref('')
const cronExpression = ref('')
const cronDescription = ref('')
const frequencyConfig = ref<FrequencyConfig>()
const inputData = ref<{ messages?: Array<{ role: string; content: string }>; [key: string]: any }>({ messages: [] })
const timezone = ref(Intl.DateTimeFormat().resolvedOptions().timeZone)

// Validation
const isFormValid = computed(() => {
  // Check if name and cron expression are filled
  if (name.value.trim() === '' || cronExpression.value === '') {
    return false
  }

  // Check if input data has at least some content (messages or other fields)
  const hasMessages = inputData.value.messages && inputData.value.messages.length > 0
  const hasOtherFields = Object.keys(inputData.value).filter(key => key !== 'messages').length > 0

  return hasMessages || hasOtherFields
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
  inputData.value = { messages: [] }
  activeTab.value = 'create'
}

// Create cron job
const onSubmit = async () => {
  if (!isFormValid.value || !selectedOrgId.value) {
    return
  }

  try {
    const cronJobData: CronJobCreate = {
      name: name.value,
      cron_expr: cronExpression.value,
      tz: timezone.value,
      entrypoint: CronEntrypoint.AGENT_INFERENCE,
      payload: {
        project_id: props.projectId,
        env: EnvType.PRODUCTION,
        input_data: inputData.value,
      },
    }

    logger.info('[CronJobModal] Submitting cron job', {
      cronJobData,
      cronExpressionValue: cronExpression.value,
      cronExpressionLength: cronExpression.value.length,
      cronExpressionFields: cronExpression.value.split(' '),
      cronExpressionFieldCount: cronExpression.value.split(' ').length,
    })

    const newCronJob = await createCronJobMutation.mutateAsync({
      orgId: selectedOrgId.value,
      cronJobData,
    })

    // Success - emit event and switch to existing tab
    emit('created', newCronJob)
    resetForm()
    activeTab.value = 'existing'
  } catch (err) {
    logger.error('[CronJobModal] Error creating cron job', { error: err })
  }
}

// Close modal
const close = () => {
  emit('update:isDialogVisible', false)
  resetForm()
}

// Filter cron jobs for current project
const projectCronJobs = computed(() => {
  if (!cronJobs.value) return []
  return cronJobs.value.filter(cron => {
    // Check if the payload has a project_id that matches
    const payload = cron.payload as any
    return payload?.project_id === props.projectId
  })
})

// Fetch cron jobs when modal opens
watch(
  () => props.isDialogVisible,
  visible => {
    if (visible && selectedOrgId.value) {
      fetchCronJobs()
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
        <span class="text-h6">Schedule Cron Jobs</span>
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
          Existing Jobs
          <VChip v-if="projectCronJobs.length > 0" size="small" color="primary" class="ms-2">
            {{ projectCronJobs.length }}
          </VChip>
        </VTab>
      </VTabs>

      <VDivider />

      <VWindow v-model="activeTab">
        <!-- Create New Cron Job -->
        <VWindowItem value="create">
          <VCardText style="max-height: 600px; overflow-y: auto">
            <VForm @submit.prevent="onSubmit">
              <!-- Name -->
              <div class="mb-6">
                <VTextField
                  v-model="name"
                  label="Cron Job Name"
                  placeholder="e.g., Daily Report Generator"
                  variant="outlined"
                  density="compact"
                  :rules="[v => !!v || 'Name is required']"
                />
              </div>

              <!-- Frequency Selector -->
              <div class="mb-6">
                <CronFrequencySelector v-model="frequencyConfig" @cron-expression="onFrequencyChange" />
              </div>

              <!-- Input Data Editor -->
              <div class="mb-6">
                <CronInputDataEditor v-model="inputData" />
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

          <VCardActions>
            <VSpacer />
            <VBtn color="grey" @click="close"> Cancel </VBtn>
            <VBtn
              color="primary"
              :disabled="!isFormValid || createCronJobMutation.isPending.value"
              :loading="createCronJobMutation.isPending.value"
              @click="onSubmit"
            >
              Create Cron Job
            </VBtn>
          </VCardActions>
        </VWindowItem>

        <!-- Existing Cron Jobs -->
        <VWindowItem value="existing">
          <VCardText style="max-height: 600px; overflow-y: auto">
            <!-- Loading State -->
            <div v-if="loading" class="text-center py-8">
              <VProgressCircular indeterminate color="primary" />
              <div class="text-body-2 mt-4">Loading cron jobs...</div>
            </div>

            <!-- Empty State -->
            <div v-else-if="projectCronJobs.length === 0" class="text-center py-8">
              <VIcon icon="tabler-calendar-x" size="64" color="grey" class="mb-4" />
              <div class="text-h6 mb-2">No Cron Jobs</div>
              <div class="text-body-2 text-medium-emphasis mb-4">
                You haven't created any cron jobs for this project yet.
              </div>
              <VBtn color="primary" @click="activeTab = 'create'"> Create First Cron Job </VBtn>
            </div>

            <!-- Cron Jobs List -->
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
