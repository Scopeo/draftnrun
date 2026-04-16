import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { type Ref, computed } from 'vue'

import { scopeoApi } from '@/api'
import { logQueryStart } from '@/utils/queryLogger'

// ==========================================
// Public Interfaces
// ==========================================

export interface KnowledgeFileSummary {
  file_id: string
  title: string | null
  chunk_count: number
  last_edited_ts: string | null
}

export interface KnowledgeFileMetadata {
  file_id: string
  title: string | null
  url: string | null
  metadata: Record<string, unknown>
  last_edited_ts: string | null
  folder_name: string | null
}

export interface KnowledgeChunk {
  chunk_id: string
  file_id: string
  content: string
  order: number
  last_edited_ts: string | null
  _processed_datetime?: string | null
}

export interface KnowledgeFileDetail {
  file: KnowledgeFileMetadata
  chunks: KnowledgeChunk[]
}

// ==========================================
// Private Types
// ==========================================

type RawKnowledgeFileSummary = Partial<{
  file_id: string
  fileId: string
  document_id: string
  documentId: string
  title: string | null
  document_title: string | null
  documentTitle: string | null
  chunk_count: number
  chunkCount: number
  last_edited_ts: string | null
  lastEditedTs: string | null
}>

type RawKnowledgeFileMetadata = Partial<{
  file_id: string
  fileId: string
  document_id: string
  documentId: string
  title: string | null
  document_title: string | null
  documentTitle: string | null
  url: string | null
  metadata: Record<string, unknown> | null
  last_edited_ts: string | null
  lastEditedTs: string | null
  folder_name: string | null
  folderName: string | null
}>

type RawKnowledgeChunk = Partial<{
  chunk_id: string
  chunkId: string
  file_id: string
  fileId: string
  document_id: string
  documentId: string
  content: string
  order: number
  last_edited_ts: string | null
  lastEditedTs: string | null
  _processed_datetime: string | null
  processed_datetime: string | null
  processedDatetime: string | null
}>

interface RawKnowledgeFileDetail {
  file?: RawKnowledgeFileMetadata
  document?: RawKnowledgeFileMetadata
  chunks: RawKnowledgeChunk[]
}

interface KnowledgeListResponse {
  total: number
  items: KnowledgeFileSummary[]
}

// ==========================================
// Private Normalizers
// ==========================================

const normalizeKnowledgeFileSummary = (item: RawKnowledgeFileSummary): KnowledgeFileSummary => {
  const chunkCount = item.chunk_count ?? item.chunkCount ?? 0
  const lastEdited = item.last_edited_ts ?? item.lastEditedTs ?? null
  const title = item.title ?? item.document_title ?? item.documentTitle ?? null

  return {
    file_id: item.file_id ?? item.fileId ?? item.document_id ?? item.documentId ?? '',
    title,
    chunk_count: typeof chunkCount === 'number' ? chunkCount : Number(chunkCount ?? 0),
    last_edited_ts: typeof lastEdited === 'string' ? lastEdited : null,
  }
}

const normalizeKnowledgeFileMetadata = (item: RawKnowledgeFileMetadata): KnowledgeFileMetadata => {
  const lastEdited = item.last_edited_ts ?? item.lastEditedTs ?? null
  const metadata = item.metadata ?? {}
  const title = item.title ?? item.document_title ?? item.documentTitle ?? null

  return {
    file_id: item.file_id ?? item.fileId ?? item.document_id ?? item.documentId ?? '',
    title,
    url: item.url ?? null,
    metadata: metadata ?? {},
    last_edited_ts: typeof lastEdited === 'string' ? lastEdited : null,
    folder_name: item.folder_name ?? item.folderName ?? null,
  }
}

const normalizeKnowledgeChunk = (chunk: RawKnowledgeChunk, index: number): KnowledgeChunk => {
  const lastEdited = chunk.last_edited_ts ?? chunk.lastEditedTs ?? null

  const processed = chunk._processed_datetime ?? chunk.processed_datetime ?? chunk.processedDatetime ?? null

  return {
    chunk_id: chunk.chunk_id ?? chunk.chunkId ?? '',
    file_id: chunk.file_id ?? chunk.fileId ?? chunk.document_id ?? chunk.documentId ?? '',
    content: chunk.content ?? '',
    order: chunk.order ?? index,
    last_edited_ts: typeof lastEdited === 'string' ? lastEdited : null,
    _processed_datetime: typeof processed === 'string' ? processed : null,
  }
}

const normalizeKnowledgeFileDetail = (detail: RawKnowledgeFileDetail): KnowledgeFileDetail => {
  const fileData = detail.file ?? detail.document ?? {}

  return {
    file: normalizeKnowledgeFileMetadata(fileData),
    chunks: (detail.chunks ?? []).map((chunk, index) => normalizeKnowledgeChunk(chunk, index)),
  }
}

// ==========================================
// Query Keys
// ==========================================

const KNOWLEDGE_FILES_QUERY = 'knowledge-files'
const KNOWLEDGE_FILE_DETAIL_QUERY = 'knowledge-file-detail'

// ==========================================
// Query Hooks
// ==========================================

export const useKnowledgeFilesQuery = (organizationId: Ref<string | undefined>, sourceId: Ref<string | undefined>) => {
  const queryKey = computed(() => [KNOWLEDGE_FILES_QUERY, organizationId.value, sourceId.value] as const)

  const query = useQuery<KnowledgeListResponse>({
    queryKey,
    queryFn: async () => {
      logQueryStart([...queryKey.value], 'useKnowledgeFilesQuery')

      if (!organizationId.value || !sourceId.value) return { total: 0, items: [] }

      const response = await scopeoApi.knowledge.listFiles(organizationId.value, sourceId.value)

      return {
        total: response?.total ?? 0,
        items: (response?.items ?? [])
          .map((item: RawKnowledgeFileSummary) => normalizeKnowledgeFileSummary(item))
          .filter((item: KnowledgeFileSummary): item is KnowledgeFileSummary => Boolean(item.file_id)),
      }
    },
    enabled: computed(() => Boolean(organizationId.value && sourceId.value)),
    staleTime: 1000 * 30,
  })

  return {
    ...query,
    refetch: query.refetch,
  }
}

export const useKnowledgeFileDetailQuery = (
  organizationId: Ref<string | undefined>,
  sourceId: Ref<string | undefined>,
  fileId: Ref<string | undefined>
) => {
  const queryKey = computed(
    () => [KNOWLEDGE_FILE_DETAIL_QUERY, organizationId.value, sourceId.value, fileId.value] as const
  )

  const query = useQuery<KnowledgeFileDetail | null>({
    queryKey,
    queryFn: async () => {
      logQueryStart([...queryKey.value], 'useKnowledgeFileDetailQuery')

      if (!organizationId.value || !sourceId.value || !fileId.value) return null

      const detail = await scopeoApi.knowledge.getFileDetail(organizationId.value, sourceId.value, fileId.value)

      if (!detail) return null

      return normalizeKnowledgeFileDetail(detail)
    },
    enabled: computed(() => Boolean(organizationId.value && sourceId.value && fileId.value)),
    staleTime: 1000 * 10,
  })

  return {
    ...query,
    refetch: query.refetch,
  }
}

export const useDeleteKnowledgeChunkMutation = () => {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({
      organizationId,
      sourceId,
      chunkId,
    }: {
      organizationId: string
      sourceId: string
      chunkId: string
    }) => scopeoApi.knowledge.deleteChunk(organizationId, sourceId, chunkId),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: [KNOWLEDGE_FILE_DETAIL_QUERY, variables.organizationId, variables.sourceId],
      })
      queryClient.invalidateQueries({
        queryKey: [KNOWLEDGE_FILES_QUERY, variables.organizationId, variables.sourceId],
      })
    },
  })
}

export interface UpdateDocumentChunksPayload {
  chunk_id: string
  order: number
  content: string
  last_edited_ts: string
  document_id: string
  document_title?: string | null
  url?: string | null
  metadata?: Record<string, unknown> | null
}

export const useUpdateDocumentChunksMutation = () => {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({
      organizationId,
      sourceId,
      documentId,
      chunks,
    }: {
      organizationId: string
      sourceId: string
      documentId: string
      chunks: UpdateDocumentChunksPayload[]
    }) => scopeoApi.knowledge.updateDocumentChunks(organizationId, sourceId, documentId, chunks),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: [KNOWLEDGE_FILE_DETAIL_QUERY, variables.organizationId, variables.sourceId, variables.documentId],
      })
      queryClient.invalidateQueries({
        queryKey: [KNOWLEDGE_FILES_QUERY, variables.organizationId, variables.sourceId],
      })
    },
  })
}

export const useDeleteKnowledgeFileMutation = () => {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({
      organizationId,
      sourceId,
      fileId,
    }: {
      organizationId: string
      sourceId: string
      fileId: string
    }) => scopeoApi.knowledge.deleteFile(organizationId, sourceId, fileId),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: [KNOWLEDGE_FILES_QUERY, variables.organizationId, variables.sourceId],
      })
    },
  })
}
