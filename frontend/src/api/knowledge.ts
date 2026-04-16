import { $api } from '@/utils/api'

export const knowledgeApi = {
  listFiles: (organizationId: string, sourceId: string) =>
    $api(`/knowledge/organizations/${organizationId}/sources/${sourceId}/documents`),
  getFileDetail: (organizationId: string, sourceId: string, fileId: string) =>
    $api(`/knowledge/organizations/${organizationId}/sources/${sourceId}/documents/${fileId}`),
  updateDocumentChunks: (
    organizationId: string,
    sourceId: string,
    documentId: string,
    chunks: Array<{
      chunk_id: string
      order: number
      content: string
      last_edited_ts: string
      document_id: string
      document_title?: string | null
      url?: string | null
      metadata?: Record<string, unknown> | null
    }>
  ) =>
    $api(`/knowledge/organizations/${organizationId}/sources/${sourceId}/documents/${documentId}`, {
      method: 'PUT',
      body: chunks,
    }),
  deleteFile: (organizationId: string, sourceId: string, fileId: string) =>
    $api(`/knowledge/organizations/${organizationId}/sources/${sourceId}/documents/${fileId}`, { method: 'DELETE' }),
  createChunk: (
    organizationId: string,
    sourceId: string,
    fileId: string,
    payload: {
      content: string
      chunk_id?: string | null
      last_edited_ts?: string | null
    }
  ) =>
    $api(`/knowledge/organizations/${organizationId}/sources/${sourceId}/documents/${fileId}/chunks`, {
      method: 'POST',
      body: payload,
    }),
  updateChunk: (organizationId: string, sourceId: string, chunkId: string, updateData: Record<string, any>) =>
    $api(`/knowledge/organizations/${organizationId}/sources/${sourceId}/chunks/${chunkId}`, {
      method: 'PUT',
      body: updateData,
    }),
  deleteChunk: (organizationId: string, sourceId: string, chunkId: string) =>
    $api(`/knowledge/organizations/${organizationId}/sources/${sourceId}/chunks/${chunkId}`, { method: 'DELETE' }),
}
