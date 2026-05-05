import { $api } from '@/utils/api'

export interface PromptVersionSummary {
  id: string
  version_number: number
  name: string
  change_description: string | null
  created_by: string | null
  created_at: string
}

export interface PromptResponse {
  id: string
  organization_id: string
  latest_version: PromptVersionSummary | null
}

export interface PromptDetailResponse extends PromptResponse {
  versions: PromptVersionSummary[]
}

export interface PromptSectionInput {
  placeholder: string
  section_prompt_id: string
  section_prompt_version_id: string
}

export interface PromptSectionResponse {
  id: string
  placeholder: string
  section_prompt_id: string
  section_prompt_version_id: string
  section_prompt_name: string | null
  section_version_number: number | null
  latest_version_number: number | null
  is_latest: boolean
  position: number
}

export interface PromptVersionDetail {
  id: string
  prompt_id: string
  version_number: number
  name: string
  content: string
  change_description: string | null
  created_by: string | null
  created_at: string
  sections: PromptSectionResponse[]
}

export interface CreatePromptPayload {
  name: string
  content: string
  change_description?: string
  sections?: PromptSectionInput[]
}

export interface CreateVersionPayload {
  name: string
  content: string
  change_description?: string
  sections?: PromptSectionInput[]
}

export const promptsApi = {
  list: (orgId: string): Promise<PromptResponse[]> => $api(`/orgs/${orgId}/prompts`),

  get: (orgId: string, promptId: string): Promise<PromptDetailResponse> =>
    $api(`/orgs/${orgId}/prompts/${promptId}`),

  create: (orgId: string, payload: CreatePromptPayload): Promise<PromptResponse> =>
    $api(`/orgs/${orgId}/prompts`, { method: 'POST', body: payload }),

  delete: (orgId: string, promptId: string): Promise<void> =>
    $api(`/orgs/${orgId}/prompts/${promptId}`, { method: 'DELETE' }),

  getVersion: (orgId: string, promptId: string, versionId: string): Promise<PromptVersionDetail> =>
    $api(`/orgs/${orgId}/prompts/${promptId}/versions/${versionId}`),

  createVersion: (orgId: string, promptId: string, payload: CreateVersionPayload): Promise<PromptVersionDetail> =>
    $api(`/orgs/${orgId}/prompts/${promptId}/versions`, { method: 'POST', body: payload }),
}
