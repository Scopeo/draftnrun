<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import {
  usePromptDetailQuery,
  usePromptVersionDetailQuery,
  useDeletePromptMutation,
} from '@/composables/queries/usePromptsQuery'
import PromptVersionSidebar from './PromptVersionSidebar.vue'
import PromptVersionDetailPanel from './PromptVersionDetailPanel.vue'
import VersionCompareDialog from './VersionCompareDialog.vue'
import LoadingState from '@/components/shared/LoadingState.vue'
import { useNotifications } from '@/composables/useNotifications'

const { notify } = useNotifications()

const props = defineProps<{
  orgId: string
  promptId: string
}>()

const orgIdRef = computed(() => props.orgId)
const promptIdRef = computed(() => props.promptId)

const { data: promptDetail, isLoading: isLoadingPrompt } = usePromptDetailQuery(orgIdRef, promptIdRef)
const deletePromptMutation = useDeletePromptMutation(orgIdRef)

const selectedVersionId = ref<string | null>(null)
const showDeleteConfirm = ref(false)
const showCompareDialog = ref(false)
const compareVersionId = ref<string | null>(null)

function openCompare(versionId: string) {
  compareVersionId.value = versionId
  showCompareDialog.value = true
}

const selectedVersionIdRef = computed(() => selectedVersionId.value || undefined)
const {
  data: selectedVersionDetail,
  isLoading: isLoadingVersion,
} = usePromptVersionDetailQuery(orgIdRef, promptIdRef, selectedVersionIdRef)

watch(promptIdRef, () => {
  selectedVersionId.value = null
  showCompareDialog.value = false
  compareVersionId.value = null
})

watch(
  () => promptDetail.value,
  (detail) => {
    if (detail?.versions?.length && !selectedVersionId.value) {
      const sorted = [...detail.versions].sort((a, b) => b.version_number - a.version_number)
      selectedVersionId.value = sorted[0].id
    }
  },
  { immediate: true }
)

const latestVersionNumber = computed(() => {
  if (!promptDetail.value?.versions?.length) return 0
  return Math.max(...promptDetail.value.versions.map((v) => v.version_number))
})

const promptFullName = computed(() => promptDetail.value?.latest_version?.name || 'Prompt')
const promptNameParts = computed(() => promptFullName.value.split('/'))

const newVersionRoute = computed(() => ({
  name: 'org-org-id-prompts-id-new-version',
  params: { orgId: props.orgId, id: props.promptId },
}))

const router = useRouter()

async function handleDelete() {
  try {
    await deletePromptMutation.mutateAsync(props.promptId)
    await router.push({ name: 'org-org-id-prompts', params: { orgId: props.orgId } })
    showDeleteConfirm.value = false
  } catch (err) {
    notify.error(`Failed to delete prompt: ${err instanceof Error ? err.message : err}`)
  }
}
</script>

<template>
  <div class="prompt-detail-page">
    <LoadingState v-if="isLoadingPrompt" message="Loading prompt..." />

    <template v-else-if="promptDetail">
      <div class="prompt-detail-page__header">
        <div class="d-flex align-center gap-4 flex-wrap">
          <RouterLink
            :to="{ name: 'org-org-id-prompts', params: { orgId: props.orgId } }"
            class="text-decoration-none"
          >
            <VChip size="small" variant="tonal" color="primary" label prepend-icon="tabler-file-text">
              Prompt Library
            </VChip>
          </RouterLink>
          <template v-for="(part, idx) in promptNameParts" :key="idx">
            <VIcon icon="tabler-chevron-right" size="16" color="grey-400" />
            <span v-if="idx < promptNameParts.length - 1" class="text-body-1 text-medium-emphasis">{{ part }}</span>
            <h2 v-else class="text-h5">{{ part }}</h2>
          </template>
          <VSpacer />
          <VBtn icon variant="text" size="small" color="error" @click="showDeleteConfirm = true">
            <VIcon icon="tabler-trash" size="20" />
            <VTooltip activator="parent" location="bottom">Delete prompt</VTooltip>
          </VBtn>
        </div>
      </div>

      <VCard class="prompt-detail-page__card">
        <div class="prompt-detail-page__layout">
          <div class="prompt-detail-page__sidebar">
            <PromptVersionSidebar
              :versions="promptDetail.versions"
              :selected-version-id="selectedVersionId"
              :new-version-route="newVersionRoute"
              @select="selectedVersionId = $event"
              @compare="openCompare"
            />
          </div>
          <div class="prompt-detail-page__content">
            <PromptVersionDetailPanel
              :version="selectedVersionDetail"
              :latest-version-number="latestVersionNumber"
              :is-loading-version="isLoadingVersion"
            />
          </div>
        </div>
      </VCard>

      <VersionCompareDialog
        v-model="showCompareDialog"
        :org-id="props.orgId"
        :prompt-id="props.promptId"
        :base-version-id="selectedVersionId"
        :compare-version-id="compareVersionId"
      />

      <VDialog v-model="showDeleteConfirm" max-width="440">
        <VCard>
          <VCardTitle class="text-h6 pa-4">Delete Prompt</VCardTitle>
          <VCardText>
            Are you sure you want to delete <strong>{{ promptFullName }}</strong>?
            This will remove all versions. This action cannot be undone.
          </VCardText>
          <VCardActions class="justify-end pa-4">
            <VBtn variant="text" @click="showDeleteConfirm = false">Cancel</VBtn>
            <VBtn color="error" :loading="deletePromptMutation.isPending.value" @click="handleDelete">
              Delete
            </VBtn>
          </VCardActions>
        </VCard>
      </VDialog>
    </template>
  </div>
</template>

<style lang="scss" scoped>
.prompt-detail-page {
  display: flex;
  flex-direction: column;
  block-size: calc(100vh - 64px - var(--dnr-page-padding) * 2);

  &__header {
    margin-block-end: var(--dnr-space-6);
    flex-shrink: 0;
  }

  &__card {
    overflow: hidden;
    flex: 1;
    min-block-size: 0;
  }

  &__layout {
    display: grid;
    grid-template-columns: 320px 1fr;
    block-size: 100%;
  }

  &__sidebar {
    overflow-y: auto;
  }

  &__content {
    overflow-y: auto;
  }
}
</style>
