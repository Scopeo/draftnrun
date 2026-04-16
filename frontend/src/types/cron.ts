export enum CronEntrypoint {
  AGENT_INFERENCE = 'agent_inference',
  DUMMY_PRINT = 'dummy_print',
  ENDPOINT_POLLING = 'endpoint_polling',
}

export enum CronStatus {
  SUCCESS = 'success',
  ERROR = 'error',
  RUNNING = 'running',
}

export enum EnvType {
  DRAFT = 'draft',
  PRODUCTION = 'production',
}

export interface AgentInferencePayload {
  project_id: string
  env: EnvType
  input_data: {
    messages?: Array<{
      role: string
      content: string
    }>
    [key: string]: any
  }
}

export interface EndpointPollingPayload {
  endpoint_url: string
  tracking_field_path: string
  filter_fields?: Record<string, string>
  headers?: Record<string, string>
  timeout?: number
  track_history?: boolean
  workflow_input: AgentInferencePayload
  workflow_input_template?: string
}

export interface CronJobCreate {
  name: string
  cron_expr: string
  tz: string
  entrypoint: CronEntrypoint
  payload: AgentInferencePayload | EndpointPollingPayload | Record<string, any>
}

export interface CronJobUpdate {
  name?: string
  cron_expr?: string
  tz?: string
  entrypoint?: CronEntrypoint
  payload?: AgentInferencePayload | EndpointPollingPayload | Record<string, any>
}

export interface CronJobResponse {
  id: string
  organization_id: string
  name: string
  cron_expr: string
  tz: string
  entrypoint: CronEntrypoint
  payload: AgentInferencePayload | EndpointPollingPayload | Record<string, any>
  is_enabled: boolean
  created_at: string
  updated_at: string
}

export interface CronRunResponse {
  id: string
  cron_id: string
  scheduled_for: string
  started_at: string
  finished_at: string | null
  status: CronStatus
  error: string | null
  result: Record<string, any> | null
}

export interface CronJobWithRuns extends CronJobResponse {
  recent_runs: CronRunResponse[]
}

export interface CronJobsListResponse {
  cron_jobs: CronJobResponse[]
  total: number
}

export interface CronRunsListResponse {
  runs: CronRunResponse[]
  total: number
}

export interface CronJobTriggerResponse {
  run_id: string
  cron_id: string
  message: string
}

// Helper type for frequency selection in UI
export enum FrequencyType {
  MINUTELY = 'minutely',
  HOURLY = 'hourly',
  DAILY = 'daily',
  WEEKLY = 'weekly',
  MONTHLY = 'monthly',
}

export interface FrequencyConfig {
  type: FrequencyType
  // For minutely: interval in minutes (1, 5, 10, 15, 30)
  // For hourly: interval in hours (1, 2, 3, 6, 12)
  interval?: number
  // For daily/weekly/monthly: time in HH:MM format
  time?: string
  // For weekly: array of day numbers (0=Sunday, 1=Monday, etc.)
  daysOfWeek?: number[]
  // For monthly: day of month (1-31)
  dayOfMonth?: number
}
