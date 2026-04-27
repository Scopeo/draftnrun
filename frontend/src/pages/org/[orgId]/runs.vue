<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useQueryClient } from '@tanstack/vue-query'
import { useRouter } from 'vue-router'
import { format } from 'date-fns'
import { useOrgRunsQuery, type OrgRun } from '@/composables/queries/useOrgRunsQuery'
import { useAgentsQuery } from '@/composables/queries/useAgentsQuery'
import { useProjectsQuery } from '@/composables/queries/useProjectsQuery'
import { useSelectedOrg } from '@/composables/useSelectedOrg'
import type { OrgRunsParams } from '@/api/observability'
import { scopeoApi } from '@/api'
import TracePreviewDrawer from '@/components/observability/TracePreviewDrawer.vue'
import { logger } from '@/utils/logger'
import { useNotifications } from '@/composables/useNotifications'

const { selectedOrgId, orgChangeCounter } = useSelectedOrg()
const router = useRouter()
const queryClient = useQueryClient()
const { notify } = useNotifications()

const { data: projects, isLoading: isLoadingProjects } = useProjectsQuery(selectedOrgId)
const { data: agents, isLoading: isLoadingAgents } = useAgentsQuery(selectedOrgId)

const allProjects = computed(() => {
  const items: { id: string; name: string }[] = []
  if (agents.value) items.push(...agents.value.filter(a => a.project_id).map(a => ({ id: a.project_id!, name: a.name })))
  if (projects.value) items.push(...projects.value.map(p => ({ id: p.project_id, name: p.project_name })))
  return items
})

const page = ref(1)
const pageSize = ref(50)
const selectedStatuses = ref<string[]>(['pending', 'running', 'completed', 'failed'])
const selectedProjectIds = ref<string[]>([])
const selectedTriggers = ref<string[]>(['api', 'sandbox', 'webhook', 'cron', 'qa'])
const selectedEnvs = ref<string[]>(['draft', 'production'])
const dateFrom = ref<string | undefined>(undefined)
const dateTo = ref<string | undefined>(undefined)

const allStatusValues = ['pending', 'running', 'completed', 'failed']
const allProjectIds = computed(() => allProjects.value.map(p => p.id))

watch(allProjects, (projects) => {
  if (projects.length && !selectedProjectIds.value.length) {
    selectedProjectIds.value = projects.map(p => p.id)
  }
}, { immediate: true })

const allProjectsSelected = computed(() =>
  allProjectIds.value.length > 0 && selectedProjectIds.value.length === allProjectIds.value.length
)

const allStatusesSelected = computed(() =>
  selectedStatuses.value.length === allStatusValues.length
)

const allTriggerValues = ['api', 'sandbox', 'webhook', 'cron', 'qa']
const allTriggersSelected = computed(() =>
  selectedTriggers.value.length === allTriggerValues.length
)

const allEnvValues = ['draft', 'production']
const allEnvsSelected = computed(() =>
  selectedEnvs.value.length === allEnvValues.length
)

const params = computed<OrgRunsParams>(() => ({
  page: page.value,
  page_size: pageSize.value,
  ...(!allStatusesSelected.value && selectedStatuses.value.length > 0 && { statuses: selectedStatuses.value }),
  ...(!allProjectsSelected.value && selectedProjectIds.value.length > 0 && { project_ids: selectedProjectIds.value }),
  ...(!allTriggersSelected.value && selectedTriggers.value.length > 0 && { triggers: selectedTriggers.value }),
  ...(!allEnvsSelected.value && selectedEnvs.value.length > 0 && { envs: selectedEnvs.value }),
  ...(dateFrom.value && { date_from: dateFrom.value }),
  ...(dateTo.value && { date_to: dateTo.value }),
}))

const { data, isLoading, isFetching, refetch } = useOrgRunsQuery(selectedOrgId, params)

const runs = computed(() => data.value?.runs ?? [])
const totalItems = computed(() => data.value?.pagination.total_items ?? 0)

const headers = [
  { title: 'Project', key: 'project_name', sortable: false },
  { title: 'Trigger', key: 'trigger', sortable: false, width: '100px' },
  { title: 'Env', key: 'env', sortable: false, width: '110px' },
  { title: 'Date', key: 'created_at', sortable: false },
  { title: 'Status', key: 'status', sortable: false },
  { title: 'Input', key: 'input', sortable: false, width: '80px' },
  { title: 'Retry', key: 'retry', sortable: false, width: '100px' },
  { title: 'Attempts', key: 'attempt_count', sortable: false, width: '100px' },
  { title: 'Trace', key: 'trace', sortable: false, width: '80px' },
]

const triggerLabelMap: Record<string, string> = {
  api: 'API',
  sandbox: 'Sandbox',
  webhook: 'Webhook',
  cron: 'Cron',
  qa: 'QA',
}

const envColorMap: Record<string, string> = {
  draft: 'warning',
  production: 'success',
}

const envLabelMap: Record<string, string> = {
  draft: 'Draft',
  production: 'Prod',
}

const agentIdByProjectId = computed(() => {
  const map = new Map<string, string>()
  if (agents.value) {
    for (const a of agents.value) {
      if (a.project_id) map.set(a.project_id, a.id)
    }
  }
  return map
})

const getProjectUrl = (projectId: string): string => {
  const orgId = selectedOrgId.value
  if (!orgId) return '#'
  const agentId = agentIdByProjectId.value.get(projectId)
  if (agentId) return `/org/${orgId}/agents/${agentId}`
  return `/org/${orgId}/projects/${projectId}`
}

const statusOptions = [
  { title: 'Pending', value: 'pending' },
  { title: 'Running', value: 'running' },
  { title: 'Completed', value: 'completed' },
  { title: 'Failed', value: 'failed' },
]

const triggerOptions = [
  { title: 'API', value: 'api' },
  { title: 'Sandbox', value: 'sandbox' },
  { title: 'Webhook', value: 'webhook' },
  { title: 'Cron', value: 'cron' },
  { title: 'QA', value: 'qa' },
]

const envOptions = [
  { title: 'Draft', value: 'draft' },
  { title: 'Production', value: 'production' },
]

const statusColorMap: Record<string, string> = {
  pending: 'warning',
  running: 'info',
  completed: 'success',
  failed: 'error',
}

const formatDate = (value: string) => format(new Date(value), 'dd/MM/yyyy HH:mm:ss')

const resetFilters = () => {
  page.value = 1
  selectedStatuses.value = [...allStatusValues]
  selectedProjectIds.value = [...allProjectIds.value]
  selectedTriggers.value = [...allTriggerValues]
  selectedEnvs.value = [...allEnvValues]
  dateFrom.value = undefined
  dateTo.value = undefined
}

watch([selectedStatuses, selectedProjectIds, selectedTriggers, selectedEnvs, dateFrom, dateTo], () => {
  page.value = 1
})

watch(orgChangeCounter, () => {
  if (selectedOrgId.value) {
    router.push(`/org/${selectedOrgId.value}/runs`)
    resetFilters()
  }
})

// --- Input dialog ---
const inputDialogVisible = ref(false)
const inputDialogData = ref<Record<string, any> | null>(null)
const inputDialogLoading = ref(false)

const openInputDialog = async (run: OrgRun) => {
  if (!selectedOrgId.value) return
  inputDialogLoading.value = true
  inputDialogVisible.value = true
  try {
    inputDialogData.value = await scopeoApi.observability.getOrgRunInput(selectedOrgId.value, run.id)
  } catch (err) {
    logger.error('openInputDialog failed', { error: err, runId: run.id, orgId: selectedOrgId.value })
    notify.error(`Failed to load input for run ${run.id}`)
    inputDialogData.value = null
  } finally {
    inputDialogLoading.value = false
  }
}

// --- Retry ---
const retryLoading = ref<string | null>(null)

const retryRun = async (run: OrgRun, legacyEnv?: string) => {
  retryLoading.value = run.id
  try {
    await scopeoApi.runs.retry(run.project_id, run.id, legacyEnv ? { env: legacyEnv } : {})
    queryClient.invalidateQueries({ queryKey: ['org-runs'] })
  } catch (err) {
    logger.error('retryRun failed', { error: err, runId: run.id, projectId: run.project_id })
    notify.error(`Failed to retry run ${run.id}`)
  } finally {
    retryLoading.value = null
  }
}

// --- Trace drawer ---
const traceDrawerOpen = ref(false)
const selectedTraceId = ref<string | undefined>(undefined)

const openTraceDrawer = (traceId: string) => {
  selectedTraceId.value = traceId
  traceDrawerOpen.value = true
}

definePage({
  meta: {
    action: 'read',
    subject: 'Project',
  },
})
</script>

<template>
  <AppPage>
    <AppPageHeader title="Runs">
      <template #filters>
        <div class="d-flex flex-wrap gap-3 align-center">
          <VSelect
            v-model="selectedProjectIds"
            :items="allProjects.map(p => ({ title: p.name, value: p.id }))"
            multiple
            density="compact"
            variant="outlined"
            hide-details
            label="Projects"
            style="min-inline-size: 200px; max-inline-size: 300px"
            :loading="isLoadingProjects || isLoadingAgents"
          >
            <template #prepend-item>
              <VListItem @click="selectedProjectIds = allProjectsSelected ? [] : [...allProjectIds]">
                <template #prepend>
                  <VCheckboxBtn :model-value="allProjectsSelected" :indeterminate="selectedProjectIds.length > 0 && !allProjectsSelected" />
                </template>
                <VListItemTitle>All Projects</VListItemTitle>
              </VListItem>
              <VDivider />
            </template>
            <template #selection="{ index }">
              <span v-if="allProjectsSelected && index === 0">All Projects</span>
              <span v-else-if="!allProjectsSelected && index === 0">{{ selectedProjectIds.length }} project{{ selectedProjectIds.length > 1 ? 's' : '' }}</span>
            </template>
          </VSelect>

          <VSelect
            v-model="selectedStatuses"
            :items="statusOptions"
            multiple
            density="compact"
            variant="outlined"
            hide-details
            label="Status"
            style="min-inline-size: 160px; max-inline-size: 220px"
          >
            <template #prepend-item>
              <VListItem @click="selectedStatuses = allStatusesSelected ? [] : [...allStatusValues]">
                <template #prepend>
                  <VCheckboxBtn :model-value="allStatusesSelected" :indeterminate="selectedStatuses.length > 0 && !allStatusesSelected" />
                </template>
                <VListItemTitle>All Statuses</VListItemTitle>
              </VListItem>
              <VDivider />
            </template>
            <template #selection="{ index }">
              <span v-if="allStatusesSelected && index === 0">All Statuses</span>
              <span v-else-if="!allStatusesSelected && index === 0">{{ selectedStatuses.length }} status{{ selectedStatuses.length > 1 ? 'es' : '' }}</span>
            </template>
          </VSelect>

          <VSelect
            v-model="selectedTriggers"
            :items="triggerOptions"
            multiple
            density="compact"
            variant="outlined"
            hide-details
            label="Trigger"
            style="min-inline-size: 160px; max-inline-size: 220px"
          >
            <template #prepend-item>
              <VListItem @click="selectedTriggers = allTriggersSelected ? [] : [...allTriggerValues]">
                <template #prepend>
                  <VCheckboxBtn :model-value="allTriggersSelected" :indeterminate="selectedTriggers.length > 0 && !allTriggersSelected" />
                </template>
                <VListItemTitle>All Triggers</VListItemTitle>
              </VListItem>
              <VDivider />
            </template>
            <template #selection="{ index }">
              <span v-if="allTriggersSelected && index === 0">All Triggers</span>
              <span v-else-if="!allTriggersSelected && index === 0">{{ selectedTriggers.length }} trigger{{ selectedTriggers.length > 1 ? 's' : '' }}</span>
            </template>
          </VSelect>

          <VSelect
            v-model="selectedEnvs"
            :items="envOptions"
            multiple
            density="compact"
            variant="outlined"
            hide-details
            label="Env"
            style="min-inline-size: 140px; max-inline-size: 200px"
          >
            <template #prepend-item>
              <VListItem @click="selectedEnvs = allEnvsSelected ? [] : [...allEnvValues]">
                <template #prepend>
                  <VCheckboxBtn :model-value="allEnvsSelected" :indeterminate="selectedEnvs.length > 0 && !allEnvsSelected" />
                </template>
                <VListItemTitle>All Envs</VListItemTitle>
              </VListItem>
              <VDivider />
            </template>
            <template #selection="{ index }">
              <span v-if="allEnvsSelected && index === 0">All Envs</span>
              <span v-else-if="!allEnvsSelected && index === 0">{{ selectedEnvs.length }} env{{ selectedEnvs.length > 1 ? 's' : '' }}</span>
            </template>
          </VSelect>

          <VTextField
            v-model="dateFrom"
            type="datetime-local"
            label="From"
            density="compact"
            variant="outlined"
            hide-details
            style="min-inline-size: 200px; max-inline-size: 220px"
          />

          <VTextField
            v-model="dateTo"
            type="datetime-local"
            label="To"
            density="compact"
            variant="outlined"
            hide-details
            style="min-inline-size: 200px; max-inline-size: 220px"
          />

          <VBtn
            v-if="!allStatusesSelected || !allProjectsSelected || !allTriggersSelected || !allEnvsSelected || dateFrom || dateTo"
            variant="text"
            size="small"
            @click="resetFilters"
          >
            Clear filters
          </VBtn>

          <VBtn
            icon
            variant="tonal"
            size="small"
            :loading="isFetching"
            @click="refetch()"
          >
            <VIcon icon="tabler-refresh" size="18" />
            <VTooltip activator="parent" location="top">Refresh</VTooltip>
          </VBtn>
        </div>
      </template>
    </AppPageHeader>

    <VCard>
      <VDataTableServer
        :headers="headers"
        :items="runs"
        :items-length="totalItems"
        :items-per-page="pageSize"
        :page="page"
        :loading="isLoading || isFetching"
        class="text-no-wrap"
        @update:page="page = $event"
        @update:items-per-page="pageSize = $event"
      >
        <template #item.project_name="{ item }">
          <RouterLink
            :to="getProjectUrl(item.project_id)"
            class="font-weight-medium text-primary text-decoration-none"
            @click.stop
          >
            {{ item.project_name }}
          </RouterLink>
        </template>

        <template #item.trigger="{ item }">
          <span class="text-medium-emphasis text-caption">{{ triggerLabelMap[item.trigger] || item.trigger }}</span>
        </template>

        <template #item.env="{ item }">
          <VChip v-if="item.env" :color="envColorMap[item.env] || 'default'" size="small" variant="tonal">
            {{ envLabelMap[item.env] ?? item.env }}
          </VChip>
          <span v-else class="text-disabled">--</span>
        </template>

        <template #item.created_at="{ item }">
          {{ formatDate(item.created_at) }}
        </template>

        <template #item.status="{ item }">
          <VChip :color="statusColorMap[item.status] || 'default'" size="small" variant="tonal">
            {{ item.status }}
          </VChip>
        </template>

        <template #item.input="{ item }">
          <VBtn
            v-if="item.input_available"
            icon
            size="x-small"
            variant="text"
            @click="openInputDialog(item)"
          >
            <VIcon icon="tabler-eye" size="18" />
            <VTooltip activator="parent" location="top">View input</VTooltip>
          </VBtn>
          <span v-else class="text-disabled">--</span>
        </template>

        <template #item.retry="{ item }">
          <VBtn
            v-if="item.input_available && (item.graph_runner_id || item.env)"
            size="x-small"
            variant="tonal"
            :loading="retryLoading === item.id"
            @click="retryRun(item)"
          >
            <VIcon icon="tabler-refresh" size="14" class="me-1" />
            Retry
          </VBtn>
          <!-- TODO: remove legacy env dropdown once all runs without graph_runner_id have expired -->
          <VMenu v-else-if="item.input_available" location="bottom">
            <template #activator="{ props: menuProps }">
              <VBtn
                v-bind="menuProps"
                size="x-small"
                variant="tonal"
                :loading="retryLoading === item.id"
              >
                <VIcon icon="tabler-refresh" size="14" class="me-1" />
                Retry
                <VIcon icon="tabler-chevron-down" size="14" class="ms-1" />
              </VBtn>
            </template>
            <VList density="compact">
              <VListItem v-for="env in allEnvValues" :key="env" @click="retryRun(item, env)">
                <VListItemTitle>{{ envLabelMap[env] ?? env }}</VListItemTitle>
              </VListItem>
            </VList>
          </VMenu>
          <span v-else class="text-disabled">--</span>
        </template>

        <template #item.attempt_count="{ item }">
          <VChip v-if="item.attempt_count > 1" size="small" variant="tonal" color="warning">
            {{ item.attempt_count }}
          </VChip>
          <span v-else>1</span>
        </template>

        <template #item.trace="{ item }">
          <VBtn
            v-if="item.trace_id"
            icon
            size="x-small"
            variant="text"
            @click="openTraceDrawer(item.trace_id)"
          >
            <VIcon icon="tabler-list-tree" size="18" />
            <VTooltip activator="parent" location="top">View trace</VTooltip>
          </VBtn>
          <span v-else class="text-disabled">--</span>
        </template>

        <template #no-data>
          <div class="text-center pa-6 text-medium-emphasis">
            No runs found. Adjust your filters or wait for new runs.
          </div>
        </template>
      </VDataTableServer>
    </VCard>

    <!-- Input dialog -->
    <VDialog v-model="inputDialogVisible" max-width="700">
      <VCard>
        <VCardTitle class="d-flex align-center">
          Run Input
          <VSpacer />
          <VBtn icon variant="text" size="small" @click="inputDialogVisible = false">
            <VIcon icon="tabler-x" />
          </VBtn>
        </VCardTitle>
        <VCardText>
          <VProgressCircular v-if="inputDialogLoading" indeterminate class="d-block mx-auto my-4" />
          <pre
            v-else-if="inputDialogData"
            class="text-body-2 pa-3 rounded"
            style="background: rgb(var(--v-theme-on-surface), 0.04); overflow: auto; max-block-size: 500px"
          >{{ JSON.stringify(inputDialogData, null, 2) }}</pre>
          <VAlert v-else type="warning" variant="tonal">Input data not available.</VAlert>
        </VCardText>
      </VCard>
    </VDialog>

    <TracePreviewDrawer v-model:open="traceDrawerOpen" :trace-id="selectedTraceId" />
  </AppPage>
</template>
