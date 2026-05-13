<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { format } from 'date-fns'
import {
  useCreatePromptMutation,
  useDeletePromptMutation,
  usePinPromptMutation,
  usePromptDetailQuery,
} from '@/composables/queries/usePromptsQuery'
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

const upgradeMenuOpened = ref(false)
const promptIdForVersions = computed(() => (upgradeMenuOpened.value ? props.promptPin?.prompt_id : undefined))
const {
  data: promptDetail,
  isLoading: versionsLoading,
  isError: versionsError,
} = usePromptDetailQuery(orgIdRef, promptIdForVersions)

const newerVersions = computed(() => {
  if (!promptDetail.value?.versions || !props.promptPin) return []
  return promptDetail.value.versions
    .filter((v) => v.version_number > props.promptPin!.pinned_version_number)
    .sort((a, b) => b.version_number - a.version_number)
})

const latestVersionNumber = computed(() => {
  if (!promptDetail.value?.versions?.length) return props.promptPin?.latest_version_number ?? 0
  return Math.max(...promptDetail.value.versions.map((v) => v.version_number))
})

function onUpgradeMenuUpdate(open: boolean) {
  if (open) upgradeMenuOpened.value = true
}

async function pinToVersion(versionId: string) {
  try {
    await pinMutation.mutateAsync({
      projectId: props.projectId,
      graphRunnerId: props.graphRunnerId,
      componentInstanceId: props.componentInstanceId,
      portName: props.portName,
      promptVersionId: versionId,
    })
    notify.success('Prompt version updated')
    emit('migrated')
  } catch (error) {
    logger.error('Failed to update prompt version', { error })
    notify.error('Failed to update prompt version')
  }
}

function formatVersionDate(dateStr: string): string {
  return format(new Date(dateStr), 'dd/MM/yyyy')
}

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
    <!-- Pinned state: show library link + version chip + upgrade -->
    <template v-if="promptPin">
      <VChip size="small" color="primary" variant="tonal" class="me-1" @click="navigateToPrompt">
        <VIcon icon="tabler-library" size="14" class="me-1" />
        {{ promptPin.prompt_name }}
      </VChip>
      <VChip size="small" variant="outlined" class="me-1">
        #{{ promptPin.pinned_version_number }}
      </VChip>

      <!-- Upgrade menu: visible only when pinned version is not the latest -->
      <VMenu
        v-if="!promptPin.is_latest && !readonly"
        location="bottom end"
        @update:model-value="onUpgradeMenuUpdate"
      >
        <template #activator="{ props: menuProps }">
          <VTooltip location="top">
            <template #activator="{ props: tooltipProps }">
              <VBtn
                v-bind="{ ...menuProps, ...tooltipProps }"
                icon
                variant="text"
                size="x-small"
                color="warning"
              >
                <VIcon icon="tabler-arrow-up-circle" size="18" />
              </VBtn>
            </template>
            <span>Newer versions available</span>
          </VTooltip>
        </template>
        <VCard min-width="280" max-width="360">
          <VCardTitle class="text-subtitle-2 pa-3 pb-1">Update to newer version</VCardTitle>
          <VCardText v-if="versionsLoading" class="text-body-2 text-medium-emphasis pa-3">
            Loading versions...
          </VCardText>
          <VCardText v-else-if="versionsError" class="text-body-2 text-error pa-3">
            Failed to load versions
          </VCardText>
          <VList v-else-if="newerVersions.length" density="compact" class="pa-1">
            <VListItem
              v-for="version in newerVersions"
              :key="version.id"
              :disabled="pinMutation.isPending.value"
              class="rounded"
              @click="pinToVersion(version.id)"
            >
              <template #prepend>
                <span class="text-subtitle-2 font-weight-bold me-2">#{{ version.version_number }}</span>
              </template>
              <VListItemTitle class="text-body-2">
                {{ version.change_description || version.name }}
              </VListItemTitle>
              <VListItemSubtitle class="text-caption">
                {{ formatVersionDate(version.created_at) }}
              </VListItemSubtitle>
              <template #append>
                <VChip
                  v-if="version.version_number === latestVersionNumber"
                  size="x-small"
                  variant="flat"
                  color="default"
                  label
                >
                  Latest
                </VChip>
              </template>
            </VListItem>
          </VList>
          <VCardText v-else class="text-body-2 text-medium-emphasis pa-3">
            No newer versions
          </VCardText>
        </VCard>
      </VMenu>

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
