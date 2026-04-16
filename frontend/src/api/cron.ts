import type {
  CronJobCreate,
  CronJobTriggerResponse,
  CronJobUpdate,
  CronJobWithRuns,
  CronJobsListResponse,
  CronRunsListResponse,
} from '@/types/cron'
import { $api } from '@/utils/api'

export const cronApi = {
  getAll: (organizationId: string): Promise<CronJobsListResponse> => $api(`/organizations/${organizationId}/crons`),

  getById: (organizationId: string, cronId: string): Promise<CronJobWithRuns> =>
    $api(`/organizations/${organizationId}/crons/${cronId}`),

  create: (organizationId: string, data: CronJobCreate) =>
    $api(`/organizations/${organizationId}/crons`, { method: 'POST', body: data }),

  update: (organizationId: string, cronId: string, data: CronJobUpdate) =>
    $api(`/organizations/${organizationId}/crons/${cronId}`, { method: 'PATCH', body: data }),

  delete: (organizationId: string, cronId: string) =>
    $api(`/organizations/${organizationId}/crons/${cronId}`, { method: 'DELETE' }),

  pause: (organizationId: string, cronId: string) =>
    $api(`/organizations/${organizationId}/crons/${cronId}/pause`, { method: 'POST' }),

  resume: (organizationId: string, cronId: string) =>
    $api(`/organizations/${organizationId}/crons/${cronId}/resume`, { method: 'POST' }),

  getRuns: (organizationId: string, cronId: string): Promise<CronRunsListResponse> =>
    $api(`/organizations/${organizationId}/crons/${cronId}/runs`),

  trigger: (organizationId: string, cronId: string): Promise<CronJobTriggerResponse> =>
    $api(`/organizations/${organizationId}/crons/${cronId}/trigger`, { method: 'POST' }),
}
