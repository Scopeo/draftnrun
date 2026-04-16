<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useQueryClient } from '@tanstack/vue-query'
import { useRouter } from 'vue-router'
import Monitoring from '@/components/monitoring/Monitoring.vue'
import { useAgentsQuery } from '@/composables/queries/useAgentsQuery'
import { useProjectsQuery } from '@/composables/queries/useProjectsQuery'
import { useSelectedOrg } from '@/composables/useSelectedOrg'

// Get selected org
const { selectedOrgId, orgChangeCounter } = useSelectedOrg()
const router = useRouter()
const queryClient = useQueryClient()

// Fetch projects and agents
const { data: projects, isLoading: isLoadingProjects } = useProjectsQuery(selectedOrgId)
const { data: agents, isLoading: isLoadingAgents } = useAgentsQuery(selectedOrgId)

// Combined loading state
const isLoading = computed(() => isLoadingProjects.value || isLoadingAgents.value)

// Get all selectable IDs
const allSelectableIds = computed(() => {
  const ids: string[] = []
  if (agents.value) {
    ids.push(...agents.value.map(a => a.id))
  }
  if (projects.value) {
    ids.push(...projects.value.map(p => p.project_id))
  }
  return ids
})

// Selected project IDs
const selectedProjectIds = ref<string[]>([])

// Auto-select all on first load, then filter out deleted projects
watch(
  allSelectableIds,
  newIds => {
    if (selectedProjectIds.value.length === 0 && newIds.length > 0) {
      selectedProjectIds.value = [...newIds]
    } else {
      selectedProjectIds.value = selectedProjectIds.value.filter(id => newIds.includes(id))
    }
  },
  { immediate: true }
)

// Check if all projects are selected
const isAllSelected = computed(() => {
  const ids = allSelectableIds.value
  return ids.length > 0 && ids.every(id => selectedProjectIds.value.includes(id))
})

// Check if we have any data
const hasData = computed(() => {
  return (agents.value && agents.value.length > 0) || (projects.value && projects.value.length > 0)
})

// Toggle project selection
const toggleProject = (id: string) => {
  const current = [...selectedProjectIds.value]
  const index = current.indexOf(id)
  if (index > -1) {
    current.splice(index, 1)
  } else {
    current.push(id)
  }
  selectedProjectIds.value = current
  queryClient.invalidateQueries({ queryKey: ['monitoring-org-charts'] })
  queryClient.invalidateQueries({ queryKey: ['monitoring-org-kpis'] })
}

// Toggle select all
const toggleSelectAll = () => {
  if (isAllSelected.value) {
    selectedProjectIds.value = []
  } else {
    selectedProjectIds.value = [...allSelectableIds.value]
  }
  queryClient.invalidateQueries({ queryKey: ['monitoring-org-charts'] })
  queryClient.invalidateQueries({ queryKey: ['monitoring-org-kpis'] })
}

// Check if any project is selected
const hasSelectedProjects = computed(() => selectedProjectIds.value.length > 0)

// Computed property that ensures selectedOrgId is non-empty when Monitoring component renders
// This properly narrows the type without using non-null assertions
const validOrgId = computed((): string | null => {
  if (!selectedOrgId.value || !hasSelectedProjects.value) {
    return null
  }
  return selectedOrgId.value
})

// Watch for organization changes - stay on monitoring page in new org
watch(orgChangeCounter, () => {
  if (selectedOrgId.value) {
    router.push(`/org/${selectedOrgId.value}/monitoring`)
    // Reset selection when org changes
    selectedProjectIds.value = []
  }
})

definePage({
  meta: {
    action: 'read',
    subject: 'Project',
  },
})
</script>

<template>
  <AppPage>
    <AppPageHeader title="Monitoring">
      <template #actions>
        <VMenu :close-on-content-click="false" location="bottom end">
          <template #activator="{ props: menuProps }">
            <VBtn
              v-bind="menuProps"
              variant="outlined"
              density="compact"
              class="project-selector"
              :loading="isLoading"
              :disabled="isLoading || !hasData"
            >
              {{ hasSelectedProjects ? `Selected (${selectedProjectIds.length})` : 'Select Projects' }}
              <VIcon icon="tabler-chevron-down" class="ms-2" />
            </VBtn>
          </template>
          <VList>
            <VListItem v-if="allSelectableIds.length > 0" @click="toggleSelectAll">
              <template #prepend>
                <VCheckbox :model-value="isAllSelected" density="compact" hide-details @click.stop="toggleSelectAll" />
              </template>
              <VListItemTitle>Select All</VListItemTitle>
            </VListItem>

            <template v-if="agents && agents.length > 0">
              <VListItem disabled class="text-caption font-weight-bold text-medium-emphasis">
                <VListItemTitle>AGENTS</VListItemTitle>
              </VListItem>
              <VListItem v-for="agent in agents" :key="agent.id" @click="toggleProject(agent.id)">
                <template #prepend>
                  <VCheckbox
                    :model-value="selectedProjectIds.includes(agent.id)"
                    density="compact"
                    hide-details
                    @click.stop="toggleProject(agent.id)"
                  />
                </template>
                <VListItemTitle>{{ agent.name }}</VListItemTitle>
              </VListItem>
            </template>

            <template v-if="projects && projects.length > 0">
              <VListItem disabled class="text-caption font-weight-bold text-medium-emphasis">
                <VListItemTitle>WORKFLOWS</VListItemTitle>
              </VListItem>
              <VListItem
                v-for="project in projects"
                :key="project.project_id"
                @click="toggleProject(project.project_id)"
              >
                <template #prepend>
                  <VCheckbox
                    :model-value="selectedProjectIds.includes(project.project_id)"
                    density="compact"
                    hide-details
                    @click.stop="toggleProject(project.project_id)"
                  />
                </template>
                <VListItemTitle>{{ project.project_name }}</VListItemTitle>
              </VListItem>
            </template>
          </VList>
        </VMenu>
      </template>
    </AppPageHeader>

    <!-- Monitoring Content -->
    <div v-if="isLoading" class="text-center pa-6">
      <VProgressCircular indeterminate />
    </div>

    <VAlert v-else-if="!hasData" type="info" variant="tonal">
      No agents or workflows available. Create an agent or workflow to view monitoring data.
    </VAlert>

    <VAlert v-else-if="!hasSelectedProjects" type="info" variant="tonal"> Please select at least one project </VAlert>

    <Monitoring
      v-else-if="validOrgId"
      :organization-id="validOrgId"
      :project-ids="selectedProjectIds"
      :is-all-selected="isAllSelected"
    />
  </AppPage>
</template>

<style lang="scss" scoped>
.project-selector {
  max-inline-size: 300px;
}
</style>
