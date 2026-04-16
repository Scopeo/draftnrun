<script setup lang="ts">
import { computed, ref } from 'vue'
import cronstrue from 'cronstrue'
import { logger } from '@/utils/logger'
import {
  useDeleteCronJobMutation,
  usePauseCronJobMutation,
  useResumeCronJobMutation,
} from '@/composables/queries/useCronJobsQuery'
import { useProjectsQuery } from '@/composables/queries/useProjectsQuery'
import { useSelectedOrg } from '@/composables/useSelectedOrg'
import GenericConfirmDialog from '@/components/dialogs/GenericConfirmDialog.vue'
import { CronEntrypoint, type CronJobResponse } from '@/types/cron'

interface Props {
  cronJob: CronJobResponse
}

interface Emit {
  (e: 'updated'): void
  (e: 'deleted'): void
  (e: 'click'): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emit>()

const { selectedOrgId } = useSelectedOrg()

// TanStack Query mutations
const deleteCronJobMutation = useDeleteCronJobMutation()
const pauseCronJobMutation = usePauseCronJobMutation()
const resumeCronJobMutation = useResumeCronJobMutation()

// Get projects to lookup project name
const { data: projects } = useProjectsQuery(selectedOrgId)

// Combined mutating state
const mutating = computed(
  () =>
    deleteCronJobMutation.isPending.value ||
    pauseCronJobMutation.isPending.value ||
    resumeCronJobMutation.isPending.value
)

// Delete confirmation
const showDeleteConfirm = ref(false)

// Cron description (human-readable)
const cronDescription = computed(() => {
  try {
    return cronstrue.toString(props.cronJob.cron_expr)
  } catch (err) {
    return props.cronJob.cron_expr
  }
})

// Status color
const statusColor = computed(() => {
  return props.cronJob.is_enabled ? 'success' : 'warning'
})

// Status text
const statusText = computed(() => {
  return props.cronJob.is_enabled ? 'Enabled' : 'Paused'
})

// Status icon
const statusIcon = computed(() => {
  return props.cronJob.is_enabled ? 'tabler-player-play' : 'tabler-player-pause'
})

// Job type (Classic vs Trigger on Event)
const jobType = computed(() => {
  if (props.cronJob.entrypoint === CronEntrypoint.ENDPOINT_POLLING) {
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

// Toggle pause/resume
const toggleStatus = async () => {
  if (!selectedOrgId.value) return

  try {
    if (props.cronJob.is_enabled) {
      // Currently enabled, so pause it
      await pauseCronJobMutation.mutateAsync({
        orgId: selectedOrgId.value,
        cronId: props.cronJob.id,
      })
    } else {
      // Currently paused, so resume it
      await resumeCronJobMutation.mutateAsync({
        orgId: selectedOrgId.value,
        cronId: props.cronJob.id,
      })
    }
    emit('updated')
  } catch (err) {
    logger.error('[CronJobCard] Error toggling cron job status', { error: err })
  }
}

// Delete cron job
const handleDelete = async () => {
  if (!selectedOrgId.value) return

  try {
    await deleteCronJobMutation.mutateAsync({
      orgId: selectedOrgId.value,
      cronId: props.cronJob.id,
    })
    emit('deleted')
    showDeleteConfirm.value = false
  } catch (err) {
    logger.error('[CronJobCard] Error deleting cron job', { error: err })
  }
}

// Format date
const formatDate = (dateString: string) => {
  try {
    return new Date(dateString).toLocaleString()
  } catch (error: unknown) {
    return dateString
  }
}

// Payload info (for display)
const payloadInfo = computed(() => {
  const payload = props.cronJob.payload as any

  // Handle both classic cron jobs (project_id at root) and endpoint polling jobs (project_id in workflow_input)
  const projectId = payload?.workflow_input?.project_id || payload?.project_id

  // Find project name from projects list
  let projectName: string | null = null
  if (projectId && projects.value) {
    const project = projects.value.find(p => p.project_id === projectId)

    projectName = project?.project_name || null
  }

  // Get all input data - handle both structures
  const inputData = payload?.workflow_input?.input_data || payload?.input_data || {}
  const messages = inputData.messages || []

  // Get additional fields (all fields except messages)
  const additionalFields = Object.entries(inputData)
    .filter(([key]) => key !== 'messages')
    .map(([key, value]) => ({ key, value }))

  // Get env - handle both structures
  const env = payload?.workflow_input?.env || payload?.env || 'N/A'

  return {
    projectId: projectId || null,
    projectName,
    env,
    messageCount: messages.length,
    messages: messages.length > 0 ? messages : null,
    additionalFields,
    hasInputData: messages.length > 0 || additionalFields.length > 0,
  }
})
</script>

<template>
  <VCard variant="outlined" class="cron-job-card" @click="emit('click')">
    <VCardText>
      <div class="d-flex justify-space-between align-start">
        <!-- Left side - Info -->
        <div class="flex-grow-1 me-4">
          <div class="d-flex align-center gap-2 mb-2 flex-wrap">
            <h3 class="text-h6">
              {{ cronJob.name }}
            </h3>
            <VChip :color="jobType.color" size="small" variant="tonal" :prepend-icon="jobType.icon">
              {{ jobType.label }}
            </VChip>
            <VChip :color="statusColor" size="small" :prepend-icon="statusIcon">
              {{ statusText }}
            </VChip>
          </div>

          <div class="text-body-2 text-medium-emphasis mb-2">
            <VIcon icon="tabler-clock" size="16" class="me-1" />
            {{ cronDescription }}
          </div>

          <div class="text-caption text-medium-emphasis">
            <VIcon icon="tabler-calendar" size="14" class="me-1" />
            Created: {{ formatDate(cronJob.created_at) }}
          </div>

          <!-- Payload Info -->
          <div class="mt-3">
            <VChip v-if="payloadInfo.projectName" size="small" variant="tonal" class="me-2 mb-2">
              <VIcon icon="tabler-folder" start size="14" />
              {{ payloadInfo.projectName }}
            </VChip>
            <VChip v-if="payloadInfo.hasInputData" size="small" variant="tonal" class="me-2 mb-2">
              <VIcon icon="tabler-database" start size="14" />
              Input Data
              <template v-if="payloadInfo.messageCount > 0 || payloadInfo.additionalFields.length > 0">
                ({{ payloadInfo.messageCount > 0 ? `${payloadInfo.messageCount} msg` : ''
                }}{{ payloadInfo.messageCount > 0 && payloadInfo.additionalFields.length > 0 ? ', ' : ''
                }}{{
                  payloadInfo.additionalFields.length > 0
                    ? `${payloadInfo.additionalFields.length} field${payloadInfo.additionalFields.length !== 1 ? 's' : ''}`
                    : ''
                }})
              </template>
            </VChip>
            <VChip size="small" variant="tonal" class="me-2 mb-2">
              <VIcon icon="tabler-server" start size="14" />
              {{ payloadInfo.env }}
            </VChip>
            <VChip size="small" variant="tonal" class="mb-2">
              <VIcon icon="tabler-map-pin" start size="14" />
              {{ cronJob.tz }}
            </VChip>
          </div>

          <!-- Input Data (if available) -->
          <div v-if="payloadInfo.hasInputData" class="mt-3">
            <div class="text-caption text-medium-emphasis mb-2">
              <VIcon icon="tabler-list-details" size="14" class="me-1" />
              Input Data:
            </div>

            <!-- Messages -->
            <div v-if="payloadInfo.messages && payloadInfo.messages.length > 0" class="ms-4 mb-2">
              <div class="text-caption font-weight-medium mb-1">Messages ({{ payloadInfo.messages.length }}):</div>
              <div class="ms-2">
                <div v-for="(message, index) in payloadInfo.messages" :key="index" class="text-caption mb-1">
                  <VChip size="x-small" variant="outlined" class="me-2">
                    {{ message.role }}
                  </VChip>
                  <span class="text-medium-emphasis">{{ message.content }}</span>
                </div>
              </div>
            </div>

            <!-- Additional Fields -->
            <div v-if="payloadInfo.additionalFields.length > 0" class="ms-4">
              <div class="text-caption font-weight-medium mb-1">
                Additional Fields ({{ payloadInfo.additionalFields.length }}):
              </div>
              <div class="ms-2">
                <div v-for="(field, index) in payloadInfo.additionalFields" :key="index" class="text-caption mb-1">
                  <VChip size="x-small" variant="tonal" color="primary" class="me-2">
                    {{ field.key }}
                  </VChip>
                  <span class="text-medium-emphasis">{{
                    typeof field.value === 'object' ? JSON.stringify(field.value) : field.value
                  }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Right side - Actions -->
        <div class="cron-job-actions" @click.stop>
          <div>
            <VTooltip :text="cronJob.is_enabled ? 'Pause this job' : 'Enable this job'" location="start">
              <template #activator="{ props: tooltipProps }">
                <VBtn
                  v-bind="tooltipProps"
                  :icon="cronJob.is_enabled ? 'tabler-player-pause' : 'tabler-player-play'"
                  variant="tonal"
                  size="small"
                  :color="cronJob.is_enabled ? 'warning' : 'success'"
                  :loading="mutating"
                  @click="toggleStatus"
                />
              </template>
            </VTooltip>
          </div>
          <div>
            <VTooltip text="Delete this job" location="start">
              <template #activator="{ props: tooltipProps }">
                <VBtn
                  v-bind="tooltipProps"
                  icon="tabler-trash"
                  variant="tonal"
                  size="small"
                  color="error"
                  @click="showDeleteConfirm = true"
                />
              </template>
            </VTooltip>
          </div>
        </div>
      </div>
    </VCardText>

    <!-- Delete Confirmation Dialog -->
    <GenericConfirmDialog
      v-model:is-dialog-visible="showDeleteConfirm"
      title="Delete Cron Job"
      :message="`Are you sure you want to delete the cron job <strong>${cronJob.name}</strong>? This action cannot be undone.`"
      confirm-text="Delete"
      confirm-color="error"
      @confirm="handleDelete"
      @cancel="showDeleteConfirm = false"
    />
  </VCard>
</template>

<style lang="scss" scoped>
.cron-job-card {
  cursor: pointer;
  transition: all 0.2s ease-in-out;

  &:hover {
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
    transform: translateY(-2px);
  }
}

.cron-job-actions {
  display: flex;
  flex-direction: column;
  align-items: center;
  flex-shrink: 0;
  gap: 12px;
}
</style>
