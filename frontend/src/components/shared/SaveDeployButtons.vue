<script setup lang="ts">
import { useAbility } from '@casl/vue'
import { computed, ref } from 'vue'
import { logger } from '@/utils/logger'
import DeployWithNotifications from '@/components/shared/DeployWithNotifications.vue'
import SaveVersionWithNotifications from '@/components/shared/SaveVersionWithNotifications.vue'
import ValidationStatusIndicator from '@/components/shared/ValidationStatusIndicator.vue'
import ErrorDisplay from '@/components/shared/ErrorDisplay.vue'
import type { GraphRunner } from '@/composables/queries/useProjectsQuery'

interface Props {
  currentGraphRunner: GraphRunner | null
  hasUnsavedChanges: boolean
  isSaving: boolean
  isDeploying: boolean
  validationStatus?: 'valid' | 'invalid' | 'saving' | 'just_saved'
  saveError?: string | null
  hasProductionDeployment?: boolean
  showStatusIndicator?: boolean
  showSchedule?: boolean
  showEndpointPolling?: boolean
  onSaveVersion: () => Promise<void> | void
  onDeploy: () => Promise<unknown>
  onScheduleClick?: () => void
  onEndpointPollingClick?: () => void
  onDeployed?: (response: unknown) => void
}

const props = withDefaults(defineProps<Props>(), {
  validationStatus: 'valid',
  saveError: null,
  hasProductionDeployment: false,
  showStatusIndicator: true,
  showSchedule: true,
  showEndpointPolling: false,
})

const emit = defineEmits<{
  deployed: [response: unknown]
}>()

const ability = useAbility()

const deployWithNotifications = ref<InstanceType<typeof DeployWithNotifications> | null>(null)
const saveVersionWithNotifications = ref<InstanceType<typeof SaveVersionWithNotifications> | null>(null)

const isDraftMode = computed(() => props.currentGraphRunner?.env === 'draft')

const isDeployDisabled = computed(() => props.hasUnsavedChanges || props.isDeploying || !isDraftMode.value)
const isSaveVersionDisabled = computed(() => props.hasUnsavedChanges || props.isSaving || !isDraftMode.value)
const showDeployButton = computed(() => ability.can('update', 'Project'))
const isScheduleDisabled = computed(() => !props.hasProductionDeployment)

const scheduleTooltip = computed(() =>
  isScheduleDisabled.value
    ? 'Schedule is only possible when a workflow has been deployed to production'
    : 'Schedule this workflow to run automatically'
)

const openDeployDialog = () => {
  if (!props.currentGraphRunner || props.hasUnsavedChanges || props.isDeploying) return
  deployWithNotifications.value?.triggerDeploy()
}

const handleSaveVersion = () => {
  if (!props.currentGraphRunner || props.hasUnsavedChanges || props.isSaving) return
  saveVersionWithNotifications.value?.triggerSaveVersion()
}

const handleDeployConfirm = async () => {
  if (!props.currentGraphRunner) return

  try {
    const deployResponse = await props.onDeploy()

    emit('deployed', deployResponse)
    if (props.onDeployed) {
      props.onDeployed(deployResponse)
    }
  } catch (error) {
    logger.error('Error deploying', { error })
    throw error
  }
}
</script>

<template>
  <div class="d-flex align-center flex-wrap gap-2">
    <VTooltip v-if="showEndpointPolling" location="bottom">
      <template #activator="{ props: tooltipProps }">
        <VBtn
          color="secondary"
          variant="tonal"
          :disabled="isScheduleDisabled"
          v-bind="tooltipProps"
          @click="onEndpointPollingClick"
        >
          <VIcon icon="tabler-radar" class="me-2" />
          Trigger on Event
        </VBtn>
      </template>
      <span>{{
        isScheduleDisabled
          ? 'Trigger on Event is only available when a workflow has been deployed to production'
          : 'Watch an API endpoint and trigger this workflow when new events are detected'
      }}</span>
    </VTooltip>

    <VTooltip v-if="showSchedule" location="bottom">
      <template #activator="{ props: tooltipProps }">
        <VBtn
          v-if="showDeployButton"
          color="primary"
          variant="tonal"
          :disabled="isScheduleDisabled"
          v-bind="tooltipProps"
          @click="onScheduleClick"
        >
          <VIcon icon="tabler-calendar-time" class="me-2" />
          Schedule
        </VBtn>
      </template>
      <span>{{ scheduleTooltip }}</span>
    </VTooltip>

    <VBtn
      v-if="showDeployButton"
      color="primary"
      variant="tonal"
      :loading="isSaving"
      :disabled="isSaveVersionDisabled"
      @click="handleSaveVersion"
    >
      <VProgressCircular v-if="isSaving" indeterminate size="18" width="2" class="me-2" />
      <VIcon v-else icon="tabler-tag" class="me-2" />
      Save Version
    </VBtn>

    <VBtn
      v-if="showDeployButton"
      color="error"
      :loading="isDeploying"
      :disabled="isDeployDisabled"
      @click="openDeployDialog"
    >
      <VProgressCircular v-if="isDeploying" indeterminate size="18" width="2" class="me-2" />
      <VIcon v-else icon="tabler-cloud-upload" class="me-2" />
      Deploy to Production
    </VBtn>

    <template v-if="showStatusIndicator && isDraftMode && ability.can('update', 'Project')">
      <ValidationStatusIndicator v-if="validationStatus !== 'invalid'" :status="validationStatus" />
      <ErrorDisplay v-else :errors="saveError" />
    </template>

    <SaveVersionWithNotifications
      ref="saveVersionWithNotifications"
      success-message="Version saved successfully! A new tagged version has been created."
      :on-save-version="onSaveVersion"
    />

    <DeployWithNotifications
      ref="deployWithNotifications"
      success-message="Deployment successful! The production environment has been updated. You are now working on a new draft version."
      :on-deploy="handleDeployConfirm"
    />
  </div>
</template>
