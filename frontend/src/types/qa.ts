// Dataset types
export interface QADataset {
  id: string
  project_id: string
  dataset_name: string
  created_at: string
  updated_at: string
}

// Version types
export interface QAVersion {
  id: string
  project_id: string
  version: string
  created_at: string
  updated_at: string
  graph_runner_id?: string
  env?: string | null
  tag_name?: string | null
}

// Custom columns types
export interface QACustomColumn {
  id: string
  dataset_id: string
  column_id: string
  column_name: string
  column_display_position: number
}

// QAColumnListResponse is now just an array directly
export type QAColumnListResponse = QACustomColumn[]

export interface QAColumnCreate {
  column_name: string
}

export interface QAColumnRename {
  column_name: string
}

// Type for custom_columns in input-groundtruth
export type CustomColumnsDict = Record<string, string | null>

// Input-Groundtruth entry types
export interface QAInputGroundtruth {
  id: string
  dataset_id: string
  input: any // Can be string or JSON object
  groundtruth: string
  custom_columns?: CustomColumnsDict | null
  created_at: string
  updated_at: string
}

// Entry with version output (from GET endpoint)
export interface QAEntryWithOutput {
  input_id: string
  input: any // Can be string or JSON object
  groundtruth: string
  output: string | null
  version: string | null
}

// Run result types
export interface QARunResult {
  input_id: string
  input: any // Can be string or JSON object
  groundtruth: string
  output: string
  version: string
  success: boolean
  error?: string
}

export interface QARunSummary {
  total: number
  done: number
  failed: number
  success_rate: number
}

export interface QARunResponse {
  results: QARunResult[]
  summary: QARunSummary
}

// Request types
export interface CreateDatasetsRequest {
  datasets_name: string[]
}

export interface UpdateDatasetsRequest {
  datasets: Array<{
    id: string
    dataset_name: string
  }>
}

export interface DeleteDatasetsRequest {
  dataset_ids: string[]
}

// Note: Versions are predefined enum values (draft/production) and don't have CRUD operations

export interface CreateInputGroundtruthsRequest {
  inputs_groundtruths: Array<{
    input: any // Can be string or JSON object
    groundtruth: string
    custom_columns?: CustomColumnsDict | null
  }>
}

export interface UpdateInputGroundtruthsRequest {
  inputs_groundtruths: Array<{
    id: string
    input?: any // Can be string or JSON object
    groundtruth?: string
    custom_columns?: CustomColumnsDict | null
  }>
}

export interface DeleteInputGroundtruthsRequest {
  input_groundtruth_ids: string[]
}

export interface RunQAProcessRequest {
  graph_runner_id: string
  input_ids?: string[]
  run_all?: boolean
}

// Evaluation Types
export type EvaluationType = 'boolean' | 'score' | 'free_text' | 'json_equality'

export interface LLMJudge {
  id: string
  project_id: string
  name: string
  description?: string | null
  evaluation_type: EvaluationType
  llm_model_reference: string
  prompt_template: string
  temperature?: number | null
  created_at: string
  updated_at: string
}

export interface LLMJudgeCreate {
  name: string
  description?: string | null
  evaluation_type: EvaluationType
  llm_model_reference?: string
  prompt_template: string
  temperature?: number | null
}

export interface LLMJudgeUpdate {
  name?: string | null
  description?: string | null
  evaluation_type?: EvaluationType | null
  llm_model_reference?: string | null
  prompt_template?: string | null
  temperature?: number | null
}

export interface JudgeEvaluation {
  id: string
  judge_id: string
  version_output_id: string
  evaluation_result: Record<string, any>
  created_at: string
  updated_at: string
}

export interface LLMJudgeDefaultsResponse {
  evaluation_type: EvaluationType
  llm_model_reference: string
  prompt_template: string
  temperature: number
}

// UI-specific types
export interface QATestCaseUI {
  id: string
  input: any
  groundtruth: string
  custom_columns?: CustomColumnsDict
  output?: string | null
  version?: string | null
  version_output_id?: string | null
  status?: 'Pending' | 'Run' | 'Failed' | 'Running'
  evaluations?: JudgeEvaluation[]
  position?: number
}
