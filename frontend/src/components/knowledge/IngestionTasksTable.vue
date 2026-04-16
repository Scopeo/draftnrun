<script setup lang="ts">
import { useAbility } from '@casl/vue'
import { format } from 'date-fns'
import { computed, ref } from 'vue'
import type { IngestionTask } from '@/composables/queries/useDataSourcesQuery'
import { getStatusChipProps, hasTaskErrorOrWarning } from '@/composables/useDataSources'

const props = defineProps<{
  tasks: IngestionTask[]
  loading: boolean
  error: Error | null
  isInitialLoad: boolean
}>()

const emit = defineEmits<{
  viewSource: [task: IngestionTask]
  delete: [task: IngestionTask]
  showError: [task: IngestionTask]
  retry: []
}>()

const ability = useAbility()

const headers = [
  { title: 'NAME', key: 'source_name' },
  { title: 'TYPE', key: 'source_type' },
  { title: 'STATUS', key: 'status' },
  { title: 'CREATED', key: 'created_at' },
  { title: 'ACTIONS', key: 'actions', sortable: false, width: '100px' },
]

const itemsPerPage = ref(10)
const page = ref(1)
const sortBy = ref('created_at')
const orderBy = ref('desc')
const search = ref('')

const filteredTasks = computed(() => {
  let filtered = [...(props.tasks || [])]
  if (search.value) {
    const term = search.value.toLowerCase()

    filtered = filtered.filter(
      item => item.source_name?.toLowerCase().includes(term) || item.source_type?.toLowerCase().includes(term)
    )
  }
  if (sortBy.value) {
    filtered.sort((a, b) => {
      type K = 'source_name' | 'source_type' | 'status' | 'created_at'
      const aVal = a[sortBy.value as K]
      const bVal = b[sortBy.value as K]
      return orderBy.value === 'desc' ? (aVal > bVal ? -1 : 1) : aVal < bVal ? -1 : 1
    })
  }
  return filtered
})

const paginatedTasks = computed(() => {
  const start = (page.value - 1) * itemsPerPage.value
  return filteredTasks.value.slice(start, start + itemsPerPage.value)
})

const totalTasks = computed(() => filteredTasks.value.length)

const updateOptions = (options: any) => {
  sortBy.value = options.sortBy[0]?.key || 'created_at'
  orderBy.value = options.sortBy[0]?.order || 'desc'
}

const isTaskDone = (task: IngestionTask) => {
  const s = String(task.status).toLowerCase()
  return s === 'done' || s === 'completed' || task.status === true
}
</script>

<template>
  <VCard class="mt-0 rounded-t-0">
    <VCardText v-if="isInitialLoad && loading" class="d-flex justify-center align-center pa-4">
      <VProgressCircular indeterminate color="primary" />
    </VCardText>
    <VCardText v-else-if="error" class="d-flex justify-center align-center pa-4">
      <VAlert type="error" title="Error loading ingestion tasks" prominent>
        <p>{{ error?.message || 'An unknown error occurred while fetching ingestion tasks.' }}</p>
        <template #append>
          <VBtn variant="text" @click="emit('retry')">Retry</VBtn>
        </template>
      </VAlert>
    </VCardText>

    <VDataTableServer
      v-else
      v-model:items-per-page="itemsPerPage"
      v-model:page="page"
      :headers="headers"
      :items="paginatedTasks"
      :items-length="totalTasks"
      class="text-no-wrap"
      @update:options="updateOptions"
    >
      <template #item.type="{ item }">
        <div class="d-flex align-center">
          <VIcon v-if="item.source_type === 'google_drive'" icon="tabler-brand-google-drive" size="18" class="me-2" />
          <VIcon v-else-if="item.source_type === 'pdf'" icon="tabler-file-text" size="18" class="me-2" />
          <VIcon v-else-if="item.source_type === 'local'" icon="tabler-upload" size="18" class="me-2" />
          <VIcon
            v-else-if="item.source_type === 'postgresql' || item.source_type === 'database'"
            icon="tabler-database"
            size="18"
            class="me-2"
          />
          <VIcon v-else-if="item.source_type === 'api'" icon="tabler-api" size="18" class="me-2" />
          <VIcon v-else-if="item.source_type === 'website'" icon="tabler-world" size="18" class="me-2" />
          <VIcon v-else icon="tabler-file" size="18" class="me-2" />
          {{ item.source_type }}
        </div>
      </template>

      <template #item.status="{ item }">
        <VTooltip v-if="hasTaskErrorOrWarning(item)" location="bottom">
          <template #activator="{ props: tooltipProps }">
            <VChip v-bind="tooltipProps" :color="getStatusChipProps(item).color" size="small">
              <VIcon
                icon="tabler-alert-triangle"
                :color="getStatusChipProps(item).showWarning ? 'warning' : 'error'"
                size="16"
                class="me-1"
              />
              {{ getStatusChipProps(item).text }}
            </VChip>
          </template>
          <span>{{ item.result_metadata?.message || 'No details available' }}</span>
        </VTooltip>
        <VChip v-else :color="getStatusChipProps(item).color" size="small">
          {{ getStatusChipProps(item).text }}
        </VChip>
      </template>

      <template #item.actions="{ item }">
        <VMenu>
          <template #activator="{ props }">
            <IconBtn v-bind="props">
              <VIcon icon="tabler-dots-vertical" />
            </IconBtn>
          </template>
          <VList density="compact">
            <VListItem v-if="isTaskDone(item) && item.source_id" @click="emit('viewSource', item)">
              <template #prepend><VIcon icon="tabler-eye" size="18" /></template>
              <VListItemTitle>View Source</VListItemTitle>
            </VListItem>
            <VListItem v-if="ability.can('delete', 'DataSource')" @click="emit('delete', item)">
              <template #prepend><VIcon icon="tabler-trash" size="18" color="error" /></template>
              <VListItemTitle class="text-error">Delete</VListItemTitle>
            </VListItem>
          </VList>
        </VMenu>
      </template>

      <template #item.created_at="{ item }">
        {{ format(new Date(item.created_at), 'MMM dd, yyyy HH:mm') }}
      </template>

      <template #no-data>
        <EmptyState
          icon="tabler-list-check"
          title="No Ingestion Tasks Found"
          description="Ingestion tasks will appear here when you process data sources."
        />
      </template>
    </VDataTableServer>
  </VCard>
</template>
