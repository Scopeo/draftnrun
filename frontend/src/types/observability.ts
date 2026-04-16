export type CallType = 'all' | 'api' | 'sandbox' | 'qa' | 'webhook'

export interface CallTypeOption {
  value: CallType
  label: string
  icon?: string
  minWidth?: number
}

export const CALL_TYPE_OPTIONS: CallTypeOption[] = [
  { value: 'all', label: 'All' },
  { value: 'sandbox', label: 'Playground', icon: 'tabler-flask' },
  { value: 'api', label: 'API', icon: 'tabler-api' },
  { value: 'qa', label: 'QA', icon: 'tabler-clipboard-check' },
  { value: 'webhook', label: 'Webhook', icon: 'tabler-webhook' },
]

export interface Span {
  span_id: string
  name: string
  start_time: string
  end_time: string
  parent_id?: string
  children?: Span[]
  input?: any
  output?: any
  status_code: string
  model_name?: string
  documents: any[]
  cumulative_llm_token_count_prompt?: number
  cumulative_llm_token_count_completion?: number
  span_kind?: string
  llm_token_count_prompt?: number | null
  llm_token_count_completion?: number | null
  tool_info?: any
  conversation_id?: string
  trace_id?: string
  total_credits?: number | null
  original_retrieval_rank?: number[]
  original_reranker_rank?: number[]
  input_preview?: string
  output_preview?: string
}

export interface TraceMessage {
  role: 'user' | 'assistant'
  content: string
}

export interface TraceData {
  span: {
    input?: Array<string | { messages?: Array<{ role: string; content: string }>; [key: string]: any }>
    conversation_id?: string
  }
}
