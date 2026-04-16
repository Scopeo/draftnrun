<script setup lang="ts">
import { type Ref, computed, ref } from 'vue'
import { logger } from '@/utils/logger'
import { formatDateCalendar } from '@/utils/formatters'
import { useModificationHistoryQuery } from '@/composables/queries/useProjectsQuery'

interface Props {
  projectId: string | undefined
  graphRunnerId: string | undefined
  orgId: string | undefined
  lastEditedTime?: string | null
  lastEditedUserId?: string | null
  lastEditedUserEmail?: string | null
}

const props = defineProps<Props>()

// Dialog state
const showDialog = ref(false)

// Computed refs for the query
const projectIdRef = computed(() => props.projectId)
const graphRunnerIdRef = computed(() => props.graphRunnerId)
const orgIdRef = computed(() => props.orgId)

// Only fetch when dialog is open
const shouldFetch = computed(() => showDialog.value)

// Query for modification history (lazy loaded when dialog opens)
const {
  data: modificationHistory,
  isLoading: historyLoading,
  error: historyErrorObj,
  refetch: refetchHistory,
} = useModificationHistoryQuery(
  projectIdRef as Ref<string | undefined>,
  graphRunnerIdRef as Ref<string | undefined>,
  orgIdRef as Ref<string | undefined>,
  shouldFetch
)

const historyError = computed(() => historyErrorObj.value?.message || null)

// Format last edited time for the button display
const formattedLastEdited = computed(() => {
  if (!props.lastEditedTime) return null

  const formattedDate = formatDateCalendar(props.lastEditedTime)

  // Use email if available, otherwise truncated user ID, otherwise 'unknown'
  const user =
    props.lastEditedUserEmail || (props.lastEditedUserId ? `user_${props.lastEditedUserId.slice(0, 8)}` : 'unknown')

  return `Last edited ${formattedDate} · by ${user}`
})

// Check if button should be shown
const canShowButton = computed(() => {
  return props.projectId && props.graphRunnerId
})

const openDialog = () => {
  if (!props.projectId || !props.graphRunnerId) {
    logger.info('[ModificationHistoryDialog] Missing projectId or graphRunnerId')
    return
  }
  showDialog.value = true
  // Query will auto-fetch when enabled becomes true, or refetch if stale
  refetchHistory()
}

const formatHistoryDate = (dateStr: string) => {
  return formatDateCalendar(dateStr)
}
</script>

<template>
  <!-- Last edited button trigger -->
  <button
    v-if="canShowButton && formattedLastEdited"
    type="button"
    class="last-edited-button text-caption text-medium-emphasis"
    @click="openDialog"
  >
    {{ formattedLastEdited }}
  </button>

  <!-- Modification History Dialog -->
  <VDialog v-model="showDialog" max-width="var(--dnr-dialog-md)">
    <VCard>
      <VCardTitle class="d-flex align-center pa-4">
        <VIcon icon="tabler-history" class="me-2" />
        Modification History
        <VSpacer />
        <VBtn icon variant="text" size="small" @click="showDialog = false">
          <VIcon icon="tabler-x" />
        </VBtn>
      </VCardTitle>

      <VDivider />

      <VCardText class="pa-4">
        <!-- Loading state -->
        <div v-if="historyLoading" class="d-flex justify-center py-8">
          <VProgressCircular indeterminate color="primary" />
        </div>

        <!-- Error state -->
        <VAlert v-else-if="historyError" type="error" variant="tonal">
          {{ historyError }}
        </VAlert>

        <!-- Empty state -->
        <div v-else-if="!modificationHistory?.length" class="text-center py-8 text-medium-emphasis">
          <VIcon icon="tabler-history-off" size="48" class="mb-4" />
          <p>No modification history available</p>
        </div>

        <!-- History list -->
        <VList v-else-if="modificationHistory" class="history-list">
          <VListItem v-for="(item, index) in modificationHistory" :key="index" class="px-0">
            <template #prepend>
              <VIcon icon="tabler-clock" size="20" class="me-3 text-medium-emphasis" />
            </template>
            <VListItemTitle>
              {{ formatHistoryDate(item.time) }}
            </VListItemTitle>
            <VListItemSubtitle>
              by {{ item.email || (item.user_id ? `user_${item.user_id.slice(0, 8)}` : 'unknown') }}
            </VListItemSubtitle>
          </VListItem>
        </VList>
      </VCardText>
    </VCard>
  </VDialog>
</template>

<style lang="scss" scoped>
.last-edited-button {
  padding: 0;
  border: none;
  background: transparent;
  cursor: pointer;
  font: inherit;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  transition: color 0.2s ease;

  &:hover {
    color: rgb(var(--v-theme-primary));
    text-decoration: underline;
  }
}

.history-list {
  max-block-size: 400px;
  overflow-y: auto;
}
</style>
