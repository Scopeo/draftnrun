import type { Ref } from 'vue'
import { computed } from 'vue'
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import type {
  CreatePromptPayload,
  CreateVersionPayload,
  PromptDetailResponse,
  PromptResponse,
  PromptVersionDetail,
} from '@/api/prompts'
import { promptsApi } from '@/api/prompts'

export function usePromptsQuery(orgId: Ref<string | undefined>) {
  return useQuery({
    queryKey: computed(() => ['prompts', orgId.value]),
    queryFn: async (): Promise<PromptResponse[]> => {
      if (!orgId.value) throw new Error('No org ID')
      return await promptsApi.list(orgId.value)
    },
    enabled: computed(() => !!orgId.value),
    staleTime: 1000 * 60 * 2,
  })
}

export function usePromptDetailQuery(orgId: Ref<string | undefined>, promptId: Ref<string | undefined>) {
  return useQuery({
    queryKey: computed(() => ['prompt-detail', orgId.value, promptId.value]),
    queryFn: async (): Promise<PromptDetailResponse> => {
      if (!orgId.value || !promptId.value) throw new Error('Missing org or prompt ID')
      return await promptsApi.get(orgId.value, promptId.value)
    },
    enabled: computed(() => !!orgId.value && !!promptId.value),
    staleTime: 1000 * 60 * 2,
  })
}

export function usePromptVersionDetailQuery(
  orgId: Ref<string | undefined>,
  promptId: Ref<string | undefined>,
  versionId: Ref<string | undefined>
) {
  return useQuery({
    queryKey: computed(() => ['prompt-version', orgId.value, promptId.value, versionId.value]),
    queryFn: async (): Promise<PromptVersionDetail> => {
      if (!orgId.value || !promptId.value || !versionId.value) throw new Error('Missing IDs')
      return await promptsApi.getVersion(orgId.value, promptId.value, versionId.value)
    },
    enabled: computed(() => !!orgId.value && !!promptId.value && !!versionId.value),
    staleTime: 1000 * 60 * 2,
  })
}

export function useCreatePromptMutation(orgId: Ref<string | undefined>) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: CreatePromptPayload) => {
      if (!orgId.value) throw new Error('No org ID')
      return await promptsApi.create(orgId.value, payload)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['prompts', orgId.value] })
    },
  })
}

export function useCreateVersionMutation(orgId: Ref<string | undefined>, promptId: Ref<string | undefined>) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: CreateVersionPayload) => {
      if (!orgId.value || !promptId.value) throw new Error('Missing IDs')
      return await promptsApi.createVersion(orgId.value, promptId.value, payload)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['prompt-detail', orgId.value, promptId.value] })
      queryClient.invalidateQueries({ queryKey: ['prompt-version', orgId.value] })
      queryClient.invalidateQueries({ queryKey: ['prompts', orgId.value] })
    },
  })
}

export function useDeletePromptMutation(orgId: Ref<string | undefined>) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (promptId: string) => {
      if (!orgId.value) throw new Error('No org ID')
      return await promptsApi.delete(orgId.value, promptId)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['prompts', orgId.value] })
    },
  })
}

export interface PinPromptParams {
  projectId: string
  graphRunnerId: string
  componentInstanceId: string
  portName: string
  promptVersionId: string
}

export function usePinPromptMutation() {
  return useMutation({
    mutationFn: async (params: PinPromptParams) => {
      return await promptsApi.pinPrompt(
        params.projectId,
        params.graphRunnerId,
        params.componentInstanceId,
        params.portName,
        params.promptVersionId,
      )
    },
  })
}
