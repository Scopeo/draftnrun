<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import cronstrue from 'cronstrue'
import { useCronJobsQuery } from '@/composables/queries/useCronJobsQuery'
import { useSelectedOrg } from '@/composables/useSelectedOrg'
import CronJobCard from '@/components/cron/CronJobCard.vue'
import CronJobDetailsModal from '@/components/cron/CronJobDetailsModal.vue'
import type { CronJobResponse } from '@/types/cron'

definePage({
  meta: {
    layout: 'default',
    requiresAuth: true,
  },
})

const { selectedOrgId, orgChangeCounter } = useSelectedOrg()
const router = useRouter()

// TanStack Query hook
const { data: cronJobs, isLoading: loading, refetch: fetchCronJobs } = useCronJobsQuery(selectedOrgId)

// Search and filter
const search = ref('')
const statusFilter = ref<'all' | 'enabled' | 'paused'>('all')

// Filtered cron jobs
const filteredCronJobs = computed(() => {
  if (!cronJobs.value) return []
  let filtered = cronJobs.value

  // Filter by search
  if (search.value) {
    const searchLower = search.value.toLowerCase()

    filtered = filtered.filter(
      cron => cron.name.toLowerCase().includes(searchLower) || cron.cron_expr.toLowerCase().includes(searchLower)
    )
  }

  // Filter by status
  if (statusFilter.value === 'enabled') {
    filtered = filtered.filter(cron => cron.is_enabled)
  } else if (statusFilter.value === 'paused') {
    filtered = filtered.filter(cron => !cron.is_enabled)
  }

  return filtered
})

// Stats
const stats = computed(() => {
  if (!cronJobs.value) return { total: 0, enabled: 0, paused: 0 }
  return {
    total: cronJobs.value.length,
    enabled: cronJobs.value.filter(c => c.is_enabled).length,
    paused: cronJobs.value.filter(c => !c.is_enabled).length,
  }
})

// Format cron description
const formatCronDescription = (cronExpr: string) => {
  try {
    return cronstrue.toString(cronExpr)
  } catch (error: unknown) {
    return cronExpr
  }
}

// Handle cron job updated/deleted
const handleCronJobUpdate = () => {
  fetchCronJobs()
}

// Details modal state
const showDetailsModal = ref(false)
const selectedCronId = ref<string | null>(null)

// Handle card click
const handleCardClick = (cronJob: CronJobResponse) => {
  selectedCronId.value = cronJob.id
  showDetailsModal.value = true
}

// Watch for organization changes - stay on scheduler page in new org
watch(orgChangeCounter, () => {
  if (selectedOrgId.value) {
    router.push(`/org/${selectedOrgId.value}/scheduler`)
  }
})
</script>

<template>
  <AppPage>
    <AppPageHeader title="Scheduler" description="Manage cron jobs for your organization" />

    <!-- Stats Cards -->
    <VRow class="mb-6">
      <VCol cols="12" sm="4">
        <VCard>
          <VCardText>
            <div class="d-flex justify-space-between align-center">
              <div>
                <div class="text-sm text-medium-emphasis mb-1">Total Jobs</div>
                <div class="text-h4 font-weight-bold">
                  {{ stats.total }}
                </div>
              </div>
              <VAvatar variant="tonal" color="primary" size="48">
                <VIcon icon="tabler-calendar-time" size="28" />
              </VAvatar>
            </div>
          </VCardText>
        </VCard>
      </VCol>

      <VCol cols="12" sm="4">
        <VCard>
          <VCardText>
            <div class="d-flex justify-space-between align-center">
              <div>
                <div class="text-sm text-medium-emphasis mb-1">Enabled</div>
                <div class="text-h4 font-weight-bold text-success">
                  {{ stats.enabled }}
                </div>
              </div>
              <VAvatar variant="tonal" color="success" size="48">
                <VIcon icon="tabler-player-play" size="28" />
              </VAvatar>
            </div>
          </VCardText>
        </VCard>
      </VCol>

      <VCol cols="12" sm="4">
        <VCard>
          <VCardText>
            <div class="d-flex justify-space-between align-center">
              <div>
                <div class="text-sm text-medium-emphasis mb-1">Paused</div>
                <div class="text-h4 font-weight-bold text-warning">
                  {{ stats.paused }}
                </div>
              </div>
              <VAvatar variant="tonal" color="warning" size="48">
                <VIcon icon="tabler-player-pause" size="28" />
              </VAvatar>
            </div>
          </VCardText>
        </VCard>
      </VCol>
    </VRow>

    <!-- Filters -->
    <VCard class="mb-6">
      <VCardText>
        <VRow>
          <VCol cols="12" md="6">
            <VTextField
              v-model="search"
              placeholder="Search cron jobs..."
              prepend-inner-icon="tabler-search"
              variant="outlined"
              density="compact"
              hide-details
              clearable
            />
          </VCol>

          <VCol cols="12" md="6">
            <VSelect
              v-model="statusFilter"
              :items="[
                { value: 'all', title: 'All Statuses' },
                { value: 'enabled', title: 'Enabled' },
                { value: 'paused', title: 'Paused' },
              ]"
              prepend-inner-icon="tabler-filter"
              variant="outlined"
              density="compact"
              hide-details
            />
          </VCol>
        </VRow>
      </VCardText>
    </VCard>

    <!-- Cron Jobs List -->
    <div v-if="loading" class="text-center py-8">
      <VProgressCircular indeterminate color="primary" size="48" />
      <div class="text-body-1 mt-4">Loading cron jobs...</div>
    </div>

    <div v-else-if="filteredCronJobs.length === 0" class="text-center py-12">
      <VIcon icon="tabler-calendar-x" size="80" color="grey" class="mb-4" />
      <div class="text-h5 mb-2">
        {{ (cronJobs?.length ?? 0) === 0 ? 'No Cron Jobs Yet' : 'No Matching Cron Jobs' }}
      </div>
      <div class="text-body-1 text-medium-emphasis">
        {{
          (cronJobs?.length ?? 0) === 0
            ? 'Create cron jobs from the agent or project pages.'
            : 'Try adjusting your filters or search term.'
        }}
      </div>
    </div>

    <div v-else class="d-flex flex-column gap-4">
      <CronJobCard
        v-for="cronJob in filteredCronJobs"
        :key="cronJob.id"
        :cron-job="cronJob"
        @updated="handleCronJobUpdate"
        @deleted="handleCronJobUpdate"
        @click="handleCardClick(cronJob)"
      />
    </div>

    <!-- Cron Job Details Modal -->
    <CronJobDetailsModal v-model="showDetailsModal" :cron-id="selectedCronId" />
  </AppPage>
</template>
