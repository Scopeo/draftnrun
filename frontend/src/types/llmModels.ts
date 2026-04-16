import type { CreditFields } from '@/types/credits'

export interface LLMModel extends CreditFields {
  id: string
  display_name: string
  description?: string | null
  provider: string
  model_name: string
  model_capacity?: string[] | null
  credits_per_input_token?: number | null
  credits_per_output_token?: number | null
  created_at: string
  updated_at: string
}

export interface ModelCapability {
  value: string
  label: string
}

export interface ModelCapabilitiesResponse {
  capabilities: ModelCapability[]
}

export interface LLMModelCreate extends CreditFields {
  display_name: string
  description?: string | null
  provider: string
  model_name: string
  model_capacity?: string[] | null
  credits_per_input_token?: number | null
  credits_per_output_token?: number | null
}

export interface LLMModelUpdate extends LLMModelCreate {
  id?: string | null
}
