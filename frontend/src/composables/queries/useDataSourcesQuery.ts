import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { type Ref, computed } from 'vue'
import { scopeoApi } from '@/api'
import { logQueryStart } from '@/utils/queryLogger'

export interface TaskResultMetadata {
  message: string
  type: string
}

export interface IngestionTask {
  id: string
  source_id: string | null
  source_name: string
  source_type: string
  status: string | boolean
  created_at: string
  result_metadata?: TaskResultMetadata | null
}

export interface Source {
  id: string
  source_name: string
  source_type: string
  source_attributes?: Record<string, unknown>
  database_name?: string
  database_schema?: string
  database_table_name?: string
  qdrant_collection_name?: string
  qdrant_schema?: Record<string, any>
  embedding_model_name?: string
  created_at: string
  updated_at?: string
  last_ingestion_time?: string
  url?: string
}

/**
 * Document reading mode options
 */
export type DocumentReadingMode = 'standard' | 'llamaparse' | 'mistral_ocr'

/**
 * Website ingestion source attributes
 */
export interface WebsiteIngestionSourceAttributes {
  url?: string | null // Single URL to scrape
  follow_links?: boolean // Whether to follow links on the page (advanced)
  max_depth?: number // Maximum depth for link following (advanced)
  limit?: number // Maximum number of pages to crawl (advanced)
  include_paths?: string[] | null // URL pathname regex patterns to include
  exclude_paths?: string[] | null // URL pathname regex patterns to exclude
  include_tags?: string[] | null // HTML tags to include in content extraction (advanced)
  exclude_tags?: string[] | null // HTML tags to exclude from content extraction (advanced)
}

/**
 * Ingestion task payload for creating website ingestion tasks
 */
export interface WebsiteIngestionTaskPayload {
  source_name: string
  source_type: 'website'
  status: string
  source_attributes: WebsiteIngestionSourceAttributes
}

/**
 * Fetches all ingestion tasks for an organization
 * Automatically refetches every 5 seconds for real-time updates
 */
export function useIngestionTasksQuery(orgId: Ref<string | undefined>) {
  const queryKey = computed(() => ['ingestion-tasks', orgId.value] as const)

  return useQuery<IngestionTask[]>({
    queryKey,
    queryFn: async () => {
      logQueryStart(['ingestion-tasks', orgId.value], 'useIngestionTasksQuery')

      if (!orgId.value) {
        return []
      }

      const data = await scopeoApi.ingestionTask.getAll(orgId.value)

      // Map the API response to IngestionTask interface
      return (
        data.map((item: any) => ({
          id: item.id,
          source_id: item.source_id,
          source_name: item.source_name,
          source_type: item.source_type,
          status: item.status,
          created_at: item.created_at,
          result_metadata: item.result_metadata || null,
        })) || []
      )
    },
    enabled: computed(() => !!orgId.value),
    staleTime: 1000 * 3,
    gcTime: 1000 * 60 * 30,
    refetchInterval: 1000 * 5,
    refetchIntervalInBackground: false,
    refetchOnMount: true,
  })
}

/**
 * Fetches all sources for an organization
 * Automatically refetches every 10 seconds for real-time updates
 */
export function useSourcesQuery(orgId: Ref<string | undefined>) {
  const queryKey = computed(() => ['sources', orgId.value] as const)

  return useQuery<Source[]>({
    queryKey,
    queryFn: async () => {
      logQueryStart(['sources', orgId.value], 'useSourcesQuery')

      if (!orgId.value) {
        return []
      }

      const data = await scopeoApi.sources.getAll(orgId.value)

      // Map the API response to Source interface
      return (
        data.map((item: any) => ({
          id: item.id,
          source_name: item.name,
          source_type: item.type,
          database_name: item.database_name,
          database_schema: item.database_schema,
          database_table_name: item.database_table_name,
          qdrant_collection_name: item.qdrant_collection_name,
          qdrant_schema: item.qdrant_schema,
          embedding_model_name: item.embedding_model_name,
          created_at: item.created_at,
          updated_at: item.updated_at,
          last_ingestion_time: item.last_ingestion_time,
          source_attributes: item.source_attributes,
        })) || []
      )
    },
    enabled: computed(() => !!orgId.value),
    staleTime: 1000 * 5,
    gcTime: 1000 * 60 * 30,
    refetchInterval: 1000 * 10,
    refetchIntervalInBackground: false,
    refetchOnMount: true,
  })
}

/**
 * Mutation to create a new ingestion task
 */
export function useCreateIngestionTaskMutation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ orgId, payload }: { orgId: string; payload: any }) => {
      return await scopeoApi.ingestionTask.create(orgId, payload)
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['ingestion-tasks', variables.orgId] })
    },
  })
}

/**
 * Mutation to delete an ingestion task
 */
export function useDeleteIngestionTaskMutation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ orgId, taskId }: { orgId: string; taskId: string }) => {
      return await scopeoApi.ingestionTask.delete(orgId, taskId)
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['ingestion-tasks', variables.orgId] })
    },
  })
}

/**
 * Mutation to update a source
 */
export function useUpdateSourceMutation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ orgId, sourceId }: { orgId: string; sourceId: string }) => {
      return await scopeoApi.sources.update(orgId, sourceId)
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['sources', variables.orgId] })
    },
  })
}

/**
 * Mutation to delete a source
 */
export function useDeleteSourceMutation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ orgId, sourceId }: { orgId: string; sourceId: string }) => {
      return await scopeoApi.sources.delete(orgId, sourceId)
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['sources', variables.orgId] })
    },
  })
}
