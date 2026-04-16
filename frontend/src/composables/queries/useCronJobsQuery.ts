import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { type Ref, computed } from 'vue'
import { scopeoApi } from '@/api'
import { logNetworkCall, logQueryStart } from '@/utils/queryLogger'
import type {
  CronJobCreate,
  CronJobResponse,
  CronJobTriggerResponse,
  CronJobUpdate,
  CronJobWithRuns,
  CronJobsListResponse,
  CronRunResponse,
  CronRunsListResponse,
} from '@/types/cron'

/**
 * Fetch all cron jobs for an organization
 */
async function fetchCronJobs(organizationId: string): Promise<CronJobResponse[]> {
  logNetworkCall(['cron-jobs', organizationId], `/organizations/${organizationId}/crons`)

  const response: CronJobsListResponse = await scopeoApi.cron.getAll(organizationId)
  return response.cron_jobs || []
}

/**
 * Fetch a single cron job with its recent runs
 */
async function fetchCronJob(organizationId: string, cronId: string): Promise<CronJobWithRuns> {
  logNetworkCall(['cron-job', cronId], `/organizations/${organizationId}/crons/${cronId}`)

  const data = await scopeoApi.cron.getById(organizationId, cronId)
  if (!data) {
    throw new Error('Cron job not found')
  }
  return data
}

/**
 * Fetch execution runs for a cron job
 */
async function fetchCronRuns(organizationId: string, cronId: string): Promise<CronRunResponse[]> {
  logNetworkCall(['cron-runs', cronId], `/organizations/${organizationId}/crons/${cronId}/runs`)

  const response: CronRunsListResponse = await scopeoApi.cron.getRuns(organizationId, cronId)
  return response.runs || []
}

/**
 * Query: Fetch all cron jobs for an organization
 */
export function useCronJobsQuery(orgId: Ref<string | undefined>) {
  const queryKey = computed(() => ['cron-jobs', orgId.value])

  logQueryStart(queryKey.value, 'useCronJobsQuery')

  return useQuery({
    queryKey,
    queryFn: () => {
      if (!orgId.value) throw new Error('No organization ID provided')
      return fetchCronJobs(orgId.value)
    },
    enabled: computed(() => !!orgId.value),
    staleTime: 1000 * 60 * 5,
    gcTime: 1000 * 60 * 30,
    refetchOnMount: true,
  })
}

/**
 * Query: Fetch a single cron job with its recent runs
 */
export function useCronJobQuery(orgId: Ref<string | undefined>, cronId: Ref<string | undefined>) {
  const queryKey = computed(() => ['cron-job', cronId.value])

  logQueryStart(queryKey.value, 'useCronJobQuery')

  return useQuery({
    queryKey,
    queryFn: () => {
      if (!orgId.value) throw new Error('No organization ID provided')
      if (!cronId.value) throw new Error('No cron job ID provided')
      return fetchCronJob(orgId.value, cronId.value)
    },
    enabled: computed(() => !!orgId.value && !!cronId.value),
    staleTime: 1000 * 60 * 5,
    gcTime: 1000 * 60 * 30,
    refetchOnMount: true,
  })
}

/**
 * Query: Fetch execution runs for a cron job
 */
export function useCronRunsQuery(orgId: Ref<string | undefined>, cronId: Ref<string | undefined>) {
  const queryKey = computed(() => ['cron-runs', cronId.value])

  logQueryStart(queryKey.value, 'useCronRunsQuery')

  return useQuery({
    queryKey,
    queryFn: () => {
      if (!orgId.value) throw new Error('No organization ID provided')
      if (!cronId.value) throw new Error('No cron job ID provided')
      return fetchCronRuns(orgId.value, cronId.value)
    },
    enabled: computed(() => !!orgId.value && !!cronId.value),
    staleTime: 1000 * 60 * 2,
    gcTime: 1000 * 60 * 30,
    refetchOnMount: true,
  })
}

/**
 * Mutation: Create a new cron job
 */
export function useCreateCronJobMutation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ orgId, cronJobData }: { orgId: string; cronJobData: CronJobCreate }) => {
      logNetworkCall(['create-cron-job', orgId], `/organizations/${orgId}/crons`)

      return await scopeoApi.cron.create(orgId, cronJobData)
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['cron-jobs', variables.orgId] })
    },
  })
}

/**
 * Mutation: Update a cron job
 */
export function useUpdateCronJobMutation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ orgId, cronId, data }: { orgId: string; cronId: string; data: CronJobUpdate }) => {
      logNetworkCall(['update-cron-job', cronId], `/organizations/${orgId}/crons/${cronId}`)

      return await scopeoApi.cron.update(orgId, cronId, data)
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['cron-job', variables.cronId] })
      queryClient.invalidateQueries({ queryKey: ['cron-jobs', variables.orgId] })
      queryClient.invalidateQueries({ queryKey: ['cron-runs', variables.cronId] })
    },
  })
}

/**
 * Mutation: Delete a cron job
 */
export function useDeleteCronJobMutation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ orgId, cronId }: { orgId: string; cronId: string }) => {
      logNetworkCall(['delete-cron-job', cronId], `/organizations/${orgId}/crons/${cronId}`)
      await scopeoApi.cron.delete(orgId, cronId)
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['cron-job', variables.cronId] })
      queryClient.invalidateQueries({ queryKey: ['cron-jobs', variables.orgId] })
    },
  })
}

/**
 * Mutation: Pause a cron job
 */
export function usePauseCronJobMutation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ orgId, cronId }: { orgId: string; cronId: string }) => {
      logNetworkCall(['pause-cron-job', cronId], `/organizations/${orgId}/crons/${cronId}/pause`)
      await scopeoApi.cron.pause(orgId, cronId)
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['cron-job', variables.cronId] })
      queryClient.invalidateQueries({ queryKey: ['cron-jobs', variables.orgId] })
    },
  })
}

/**
 * Mutation: Resume a cron job
 */
export function useResumeCronJobMutation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ orgId, cronId }: { orgId: string; cronId: string }) => {
      logNetworkCall(['resume-cron-job', cronId], `/organizations/${orgId}/crons/${cronId}/resume`)
      await scopeoApi.cron.resume(orgId, cronId)
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['cron-job', variables.cronId] })
      queryClient.invalidateQueries({ queryKey: ['cron-jobs', variables.orgId] })
    },
  })
}

/**
 * Mutation: Manually trigger a cron job to run now
 */
export function useTriggerCronJobMutation() {
  const queryClient = useQueryClient()

  return useMutation<CronJobTriggerResponse, Error, { orgId: string; cronId: string }>({
    mutationFn: async ({ orgId, cronId }) => {
      logNetworkCall(['trigger-cron-job', cronId], `/organizations/${orgId}/crons/${cronId}/trigger`)
      return await scopeoApi.cron.trigger(orgId, cronId)
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['cron-job', variables.cronId] })
      queryClient.invalidateQueries({ queryKey: ['cron-jobs', variables.orgId] })
    },
  })
}
