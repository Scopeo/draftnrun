<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useCreatePromptMutation, useDeletePromptMutation, usePinPromptMutation } from '@/composables/queries/usePromptsQuery'
import { useNotifications } from '@/composables/useNotifications'
import { logger } from '@/utils/logger'
import type { PromptPinInfo } from '../types/node.types'

interface Props {
  isPromptEligible: boolean
  promptPin?: PromptPinInfo | null
  promptContent: string
  projectName: string
  componentName: string
  orgId: string
  projectId: string
  graphRunnerId: string
  componentInstanceId: string
  portName: string
  readonly?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  promptPin: null,
  readonly: false,
})

const emit = defineEmits<{
  migrated: []
}>()

const router = useRouter()
const { notify } = useNotifications()
const showMigrateDialog = ref(false)
const migrateName = ref('')

const orgIdRef = computed(() => props.orgId)
const createMutation = useCreatePromptMutation(orgIdRef)
const deleteMutation = useDeletePromptMutation(orgIdRef)
const pinMutation = usePinPromptMutation()

const isMigrating = computed(() => createMutation.isPending.value || pinMutation.isPending.value)
const pendingPrompt = ref<{ id: string; versionId: string } | null>(null)

function openMigrateDialog() {
  migrateName.value = `${props.projectName}/${props.componentName}`
  pendingPrompt.value = null
  showMigrateDialog.value = true
}

function cancelMigration() {
  if (pendingPrompt.value) {
    deleteMutation.mutate(pendingPrompt.value.id, {
      onError: (err: Error) => {
        logger.error('Failed to clean up orphaned prompt', { error: err })
      },
    })
    pendingPrompt.value = null
  }
  showMigrateDialog.value = false
}

async function confirmMigrate() {
  if (!migrateName.value.trim() || !props.promptContent.trim()) return

  try {
    let versionId: string

    if (pendingPrompt.value) {
      versionId = pendingPrompt.value.versionId
    } else {
      const prompt = await createMutation.mutateAsync({
        name: migrateName.value.trim(),
        content: props.promptContent,
      })

      if (!prompt.latest_version?.id) {
        notify.error('Failed to create prompt version')
        return
      }

      pendingPrompt.value = { id: prompt.id, versionId: prompt.latest_version.id }
      versionId = prompt.latest_version.id
    }

    await pinMutation.mutateAsync({
      projectId: props.projectId,
      graphRunnerId: props.graphRunnerId,
      componentInstanceId: props.componentInstanceId,
      portName: props.portName,
      promptVersionId: versionId,
    })

    pendingPrompt.value = null
    showMigrateDialog.value = false
    notify.success('Prompt migrated to library')
    emit('migrated')
  } catch (error) {
    logger.error('Failed to migrate prompt to library', { error })
    notify.error(
      pendingPrompt.value
        ? 'Prompt was created but linking failed. Click Migrate to retry.'
        : 'Failed to migrate prompt. Please try again.',
    )
  }
}

function navigateToPrompt() {
  if (!props.promptPin) return
  router.push(`/org/${props.orgId}/prompts/${props.promptPin.prompt_id}`)
}
</script>

<template>
  <div v-if="isPromptEligible" class="prompt-migration-actions d-inline-flex align-center">
    <!-- Pinned state: show library link -->
    <template v-if="promptPin">
      <VChip size="small" color="primary" variant="tonal" class="me-1" @click="navigateToPrompt">
        <VIcon icon="tabler-library" size="14" class="me-1" />
        {{ promptPin.prompt_name }}
        <template v-if="!promptPin.is_latest">
          <VIcon icon="tabler-alert-circle" size="14" class="ms-1 text-warning" />
        </template>
      </VChip>
      <VTooltip location="top">
        <template #activator="{ props: tooltipProps }">
          <VBtn
            v-bind="tooltipProps"
            icon
            variant="text"
            size="x-small"
            @click="navigateToPrompt"
          >
            <VIcon icon="tabler-external-link" size="16" />
          </VBtn>
        </template>
        <span>Open in Prompt Library</span>
      </VTooltip>
    </template>

    <!-- Eligible but not pinned: show migrate button -->
    <template v-else-if="!readonly">
      <VTooltip location="top">
        <template #activator="{ props: tooltipProps }">
          <VBtn
            v-bind="tooltipProps"
            icon
            variant="text"
            size="x-small"
            :disabled="!promptContent.trim()"
            @click="openMigrateDialog"
          >
            <VIcon icon="tabler-library" size="18" />
          </VBtn>
        </template>
        <span>Migrate to Prompt Library</span>
      </VTooltip>
    </template>

    <!-- Migrate dialog -->
    <VDialog v-model="showMigrateDialog" max-width="500" persistent>
      <VCard>
        <VCardTitle class="text-h6 pa-6 pb-2">Migrate to Prompt Library</VCardTitle>
        <VCardText class="pa-6 pt-2">
          <p class="text-body-2 text-medium-emphasis mb-4">
            This will create a new prompt in your organization's library and link it to this component.
            The prompt will become read-only here and managed from the library.
          </p>
          <VTextField
            v-model="migrateName"
            label="Prompt name"
            variant="outlined"
            density="compact"
            placeholder="project_name/component_instance_name"
            :rules="[v => !!v?.trim() || 'Name is required']"
          />
        </VCardText>
        <VCardActions class="pa-6 pt-0">
          <VSpacer />
          <VBtn variant="text" :disabled="isMigrating" @click="cancelMigration">
            Cancel
          </VBtn>
          <VBtn
            color="primary"
            :loading="isMigrating"
            :disabled="!migrateName.trim()"
            @click="confirmMigrate"
          >
            Migrate
          </VBtn>
        </VCardActions>
      </VCard>
    </VDialog>
  </div>
</template>

<style lang="scss" scoped>
.prompt-migration-actions {
  vertical-align: middle;
}
</style>
