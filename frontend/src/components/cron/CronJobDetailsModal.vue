<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import cronstrue from 'cronstrue'
import { useCronJobQuery, useTriggerCronJobMutation } from '@/composables/queries/useCronJobsQuery'
import { useSelectedOrg } from '@/composables/useSelectedOrg'
import { CronEntrypoint } from '@/types/cron'

interface Props {
  modelValue: boolean
  cronId: string | null
}

interface Emit {
  (e: 'update:modelValue', value: boolean): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emit>()

const { selectedOrgId } = useSelectedOrg()

// Query for cron job details - computed ref that updates when cronId changes
const cronIdRef = computed(() => props.cronId || undefined)

const { data: cronJob, isLoading, error } = useCronJobQuery(selectedOrgId, cronIdRef)

const { mutate: triggerCronJob, isPending: isTriggerPending } = useTriggerCronJobMutation()

const showConfirmDialog = ref(false)
const feedbackDialog = ref({ show: false, type: 'success' as 'success' | 'error', title: '', message: '' })

const showConfirmDialogModel = computed({
  get: () => props.modelValue && showConfirmDialog.value,
  set: value => {
    showConfirmDialog.value = value
  },
})

const feedbackDialogModel = computed({
  get: () => props.modelValue && feedbackDialog.value.show,
  set: value => {
    feedbackDialog.value = { ...feedbackDialog.value, show: value }
  },
})

const handleRunNow = () => {
  if (!selectedOrgId.value || !props.cronId || isLoading.value || !cronJob.value) return
  showConfirmDialog.value = true
}

const confirmRunNow = () => {
  showConfirmDialog.value = false
  if (!selectedOrgId.value || !props.cronId) return
  triggerCronJob(
    { orgId: selectedOrgId.value, cronId: props.cronId },
    {
      onSuccess: () => {
        feedbackDialog.value = {
          show: true,
          type: 'success',
          title: 'Cron job triggered',
          message: 'Execution is running in the background. The runs list will refresh shortly.',
        }
      },
      onError: err => {
        const errorMessage =
          err instanceof Error
            ? err.message
            : typeof err === 'string'
              ? err
              : 'An unexpected error occurred while triggering the cron job.'

        feedbackDialog.value = {
          show: true,
          type: 'error',
          title: 'Failed to trigger',
          message: errorMessage,
        }
      },
    }
  )
}

watch(
  () => props.modelValue,
  isOpen => {
    if (isOpen) return
    showConfirmDialog.value = false
    feedbackDialog.value = { ...feedbackDialog.value, show: false }
  }
)

// Track expanded results for each run
const expandedResults = ref<Set<string>>(new Set())

// Toggle result expansion
const toggleResultExpansion = (runId: string) => {
  const key = `${props.cronId}-${runId}`
  if (expandedResults.value.has(key)) {
    expandedResults.value.delete(key)
  } else {
    expandedResults.value.add(key)
  }
}

// Close modal
const close = () => {
  emit('update:modelValue', false)
}

// Cron description (human-readable)
const cronDescription = computed(() => {
  if (!cronJob.value) return ''
  try {
    return cronstrue.toString(cronJob.value.cron_expr)
  } catch (err) {
    return cronJob.value.cron_expr
  }
})

// Status color
const statusColor = computed(() => {
  return cronJob.value?.is_enabled ? 'success' : 'warning'
})

// Status text
const statusText = computed(() => {
  return cronJob.value?.is_enabled ? 'Enabled' : 'Paused'
})

// Status icon
const statusIcon = computed(() => {
  return cronJob.value?.is_enabled ? 'tabler-player-play' : 'tabler-player-pause'
})

// Job type (Classic vs Trigger on Event)
const jobType = computed(() => {
  if (!cronJob.value) return { label: '', color: '', icon: '' }
  if (cronJob.value.entrypoint === CronEntrypoint.ENDPOINT_POLLING) {
    return {
      label: 'Trigger on Event',
      color: 'secondary',
      icon: 'tabler-radar',
    }
  }
  return {
    label: 'Classic',
    color: 'primary',
    icon: 'tabler-calendar-time',
  }
})

// Format date
const formatDate = (dateString: string | null) => {
  if (!dateString) return 'N/A'
  try {
    return new Date(dateString).toLocaleString()
  } catch (error: unknown) {
    return dateString
  }
}

// Format duration
const formatDuration = (startedAt: string | null, finishedAt: string | null) => {
  if (!startedAt) return 'N/A'
  if (!finishedAt) return 'Running...'
  try {
    const start = new Date(startedAt).getTime()
    const finish = new Date(finishedAt).getTime()
    const duration = finish - start
    const seconds = Math.floor(duration / 1000)
    const minutes = Math.floor(seconds / 60)
    const hours = Math.floor(minutes / 60)

    if (hours > 0) {
      return `${hours}h ${minutes % 60}m ${seconds % 60}s`
    }
    if (minutes > 0) {
      return `${minutes}m ${seconds % 60}s`
    }
    return `${seconds}s`
  } catch (error: unknown) {
    return 'N/A'
  }
}

// Run status color
const getRunStatusColor = (status: string) => {
  const normalizedStatus = status.toLowerCase()
  if (normalizedStatus === 'success' || normalizedStatus === 'completed') {
    return 'success'
  }
  if (normalizedStatus === 'error') {
    return 'error'
  }
  if (normalizedStatus === 'running') {
    return 'info'
  }
  return 'default'
}

// Run status icon
const getRunStatusIcon = (status: string) => {
  const normalizedStatus = status.toLowerCase()
  if (normalizedStatus === 'success' || normalizedStatus === 'completed') {
    return 'tabler-check'
  }
  if (normalizedStatus === 'error') {
    return 'tabler-x'
  }
  if (normalizedStatus === 'running') {
    return 'tabler-loader-2'
  }
  return 'tabler-circle'
}
</script>

<template>
  <VDialog
    :model-value="modelValue"
    max-width="900px"
    scrollable
    @update:model-value="emit('update:modelValue', $event)"
  >
    <VCard v-if="!isLoading && cronJob">
      <VCardTitle class="d-flex justify-space-between align-center pa-6 gap-4">
        <div class="d-flex align-center gap-3 flex-wrap">
          <span class="text-h5">{{ cronJob.name }}</span>
          <VChip :color="jobType.color" size="small" variant="tonal" :prepend-icon="jobType.icon">
            {{ jobType.label }}
          </VChip>
          <VChip :color="statusColor" size="small" :prepend-icon="statusIcon">
            {{ statusText }}
          </VChip>
        </div>
        <div class="d-flex align-center gap-2">
          <VBtn
            variant="outlined"
            size="small"
            prepend-icon="tabler-player-play"
            :loading="isTriggerPending"
            @click="handleRunNow"
          >
            Run Now
          </VBtn>
          <VBtn icon variant="text" size="small" @click="close">
            <VIcon icon="tabler-x" />
          </VBtn>
        </div>
      </VCardTitle>

      <VDivider />

      <VCardText class="pa-6">
        <!-- Scheduler Job Details -->
        <div class="mb-4">
          <h3 class="text-h6 mb-3">Scheduler Job Details</h3>
          <VRow dense>
            <VCol cols="12" md="6">
              <div class="mb-2">
                <div class="text-caption text-medium-emphasis mb-1">Schedule</div>
                <div class="text-body-1 font-weight-medium">{{ cronDescription }}</div>
              </div>
            </VCol>
            <VCol cols="12" md="6">
              <div class="mb-2">
                <div class="text-caption text-medium-emphasis mb-1">Timezone</div>
                <div class="text-body-1 font-weight-medium">{{ cronJob.tz }}</div>
              </div>
            </VCol>
            <VCol cols="12" md="6">
              <div class="mb-2">
                <div class="text-caption text-medium-emphasis mb-1">Created At</div>
                <div class="text-body-1 font-weight-medium">{{ formatDate(cronJob.created_at) }}</div>
              </div>
            </VCol>
            <VCol cols="12" md="6">
              <div class="mb-2">
                <div class="text-caption text-medium-emphasis mb-1">Updated At</div>
                <div class="text-body-1 font-weight-medium">{{ formatDate(cronJob.updated_at) }}</div>
              </div>
            </VCol>
          </VRow>
        </div>

        <VDivider class="my-4" />

        <!-- Recent Runs -->
        <div>
          <div class="mb-3">
            <h3 class="text-h6">Last 10 Runs</h3>
          </div>

          <!-- Empty State -->
          <div v-if="!cronJob.recent_runs || cronJob.recent_runs.length === 0" class="text-center py-8">
            <VIcon icon="tabler-clock-hour-4" size="64" color="grey" class="mb-4" />
            <div class="text-h6 mb-2">No Runs Yet</div>
            <div class="text-body-2 text-medium-emphasis">This cron job hasn't been executed yet.</div>
          </div>

          <!-- Runs List -->
          <div v-else class="d-flex flex-column gap-3">
            <VCard v-for="run in cronJob.recent_runs" :key="run.id" variant="outlined">
              <VCardText>
                <div class="d-flex align-center gap-3 mb-2">
                  <VChip
                    :color="getRunStatusColor(run.status)"
                    size="small"
                    :prepend-icon="getRunStatusIcon(run.status)"
                  >
                    {{ run.status }}
                  </VChip>
                  <div class="text-caption text-medium-emphasis">ID: {{ run.id.substring(0, 8) }}...</div>
                </div>

                <VRow dense>
                  <VCol cols="12" md="3">
                    <div class="mb-1">
                      <div class="text-caption text-medium-emphasis mb-1">Scheduled For</div>
                      <div class="text-body-2 font-weight-medium">{{ formatDate(run.scheduled_for) }}</div>
                    </div>
                  </VCol>
                  <VCol cols="12" md="3">
                    <div class="mb-1">
                      <div class="text-caption text-medium-emphasis mb-1">Started At</div>
                      <div class="text-body-2 font-weight-medium">{{ formatDate(run.started_at) }}</div>
                    </div>
                  </VCol>
                  <VCol cols="12" md="3">
                    <div class="mb-1">
                      <div class="text-caption text-medium-emphasis mb-1">Finished At</div>
                      <div class="text-body-2 font-weight-medium">{{ formatDate(run.finished_at) }}</div>
                    </div>
                  </VCol>
                  <VCol cols="12" md="3">
                    <div class="mb-1">
                      <div class="text-caption text-medium-emphasis mb-1">Duration</div>
                      <div class="text-body-2 font-weight-medium">
                        {{ formatDuration(run.started_at, run.finished_at) }}
                      </div>
                    </div>
                  </VCol>
                </VRow>

                <!-- Error -->
                <div v-if="run.error" class="mt-3">
                  <VAlert type="error" variant="tonal" density="compact">
                    <div class="text-caption font-weight-medium mb-1">Error:</div>
                    <div class="text-caption">{{ run.error }}</div>
                  </VAlert>
                </div>

                <!-- Result -->
                <div v-if="run.result" class="mt-3">
                  <div class="text-caption text-medium-emphasis mb-1">Result:</div>
                  <VCard variant="outlined">
                    <VCardText class="pa-2">
                      <pre
                        class="text-body-2 result-content"
                        :class="[
                          {
                            'result-collapsed':
                              !expandedResults.has(`${cronId}-${run.id}`) &&
                              JSON.stringify(run.result, null, 2).length > 500,
                          },
                        ]"
                        >{{ JSON.stringify(run.result, null, 2) }}</pre
                      >
                      <div v-if="JSON.stringify(run.result, null, 2).length > 500" class="d-flex justify-center mt-2">
                        <VBtn
                          size="x-small"
                          variant="text"
                          :prepend-icon="
                            expandedResults.has(`${cronId}-${run.id}`) ? 'tabler-chevron-up' : 'tabler-chevron-down'
                          "
                          @click="toggleResultExpansion(run.id)"
                        >
                          {{ expandedResults.has(`${cronId}-${run.id}`) ? 'Collapse' : 'Expand' }}
                        </VBtn>
                      </div>
                    </VCardText>
                  </VCard>
                </div>
              </VCardText>
            </VCard>
          </div>
        </div>
      </VCardText>
    </VCard>

    <!-- Loading State -->
    <VCard v-else-if="isLoading">
      <VCardText class="pa-6">
        <div class="text-center py-8">
          <VProgressCircular indeterminate color="primary" size="48" />
          <div class="text-body-1 mt-4">Loading cron job details...</div>
        </div>
      </VCardText>
    </VCard>

    <!-- Error State -->
    <VCard v-else-if="error">
      <VCardTitle class="d-flex justify-space-between align-center pa-6">
        <span class="text-h5">Error</span>
        <VBtn icon variant="text" size="small" @click="close">
          <VIcon icon="tabler-x" />
        </VBtn>
      </VCardTitle>
      <VDivider />
      <VCardText class="pa-6">
        <VAlert type="error" variant="tonal">
          <div class="text-body-1 font-weight-medium mb-2">Failed to load cron job details</div>
          <div class="text-body-2">
            {{ error instanceof Error ? error.message : 'An unexpected error occurred' }}
          </div>
        </VAlert>
      </VCardText>
    </VCard>
  </VDialog>

  <!-- Confirm dialog -->
  <VDialog v-model="showConfirmDialogModel" max-width="var(--dnr-dialog-sm)" persistent>
    <VCard>
      <VCardTitle class="d-flex align-center gap-2 pa-5">
        <VIcon icon="tabler-player-play" color="primary" />
        Run cron job now?
      </VCardTitle>
      <VCardText class="pb-2">
        This will immediately execute <strong>{{ cronJob?.name }}</strong> in the background.
      </VCardText>
      <VCardActions class="pa-5 pt-2">
        <VSpacer />
        <VBtn variant="text" @click="showConfirmDialog = false">Cancel</VBtn>
        <VBtn color="primary" variant="elevated" :loading="isTriggerPending" @click="confirmRunNow"> Run Now </VBtn>
      </VCardActions>
    </VCard>
  </VDialog>

  <!-- Feedback dialog (success / warning / error) -->
  <VDialog v-model="feedbackDialogModel" max-width="var(--dnr-dialog-sm)">
    <VCard>
      <VCardTitle class="d-flex align-center gap-2 pa-5">
        <VIcon
          :icon="feedbackDialog.type === 'success' ? 'tabler-circle-check' : 'tabler-circle-x'"
          :color="feedbackDialog.type"
        />
        {{ feedbackDialog.title }}
      </VCardTitle>
      <VCardText>
        {{ feedbackDialog.message }}
      </VCardText>
      <VCardActions class="pa-5 pt-0">
        <VSpacer />
        <VBtn variant="text" @click="feedbackDialog.show = false">OK</VBtn>
      </VCardActions>
    </VCard>
  </VDialog>
</template>

<style lang="scss" scoped>
pre {
  margin: 0;
  white-space: pre-wrap;
  word-wrap: break-word;
  font-family: 'Courier New', monospace;
  font-size: 12px;
  line-height: 1.5;
}

.result-content {
  color: rgb(var(--v-theme-on-surface));
  font-weight: 400;
}

.result-collapsed {
  max-height: 200px;
  overflow: hidden;
  position: relative;

  &::after {
    position: absolute;
    bottom: 0;
    left: 0;
    right: 0;
    height: 40px;
    background: linear-gradient(to bottom, transparent, rgb(var(--v-theme-surface)));
    content: '';
    pointer-events: none;
  }
}
</style>
