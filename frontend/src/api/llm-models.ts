import type { LLMModel, LLMModelCreate, LLMModelUpdate, ModelCapabilitiesResponse } from '@/types/llmModels'
import { $api } from '@/utils/api'

export const llmModelsApi = {
  list: (organizationId: string): Promise<LLMModel[]> => $api(`/organizations/${organizationId}/llm-models`),
  getCapabilities: (organizationId: string): Promise<ModelCapabilitiesResponse> =>
    $api(`/organizations/${organizationId}/llm-models/capabilities`),
  create: (organizationId: string, data: LLMModelCreate): Promise<LLMModel> =>
    $api(`/organizations/${organizationId}/llm-models`, {
      method: 'POST',
      body: data,
    }),
  update: (organizationId: string, llmModelId: string, data: LLMModelUpdate): Promise<LLMModel> =>
    $api(`/organizations/${organizationId}/llm-models/${llmModelId}`, {
      method: 'PATCH',
      body: data,
    }),
  delete: (organizationId: string, llmModelId: string): Promise<void> =>
    $api(`/organizations/${organizationId}/llm-models/${llmModelId}`, {
      method: 'DELETE',
    }),
}
