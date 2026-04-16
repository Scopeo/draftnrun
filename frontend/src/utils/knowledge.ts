import type { KnowledgeChunk } from '@/composables/queries/useKnowledgeQueries'
import { countTokens } from '@/utils/tokenizer'

export interface EditableChunk {
  chunkId: string
  originalChunkId: string
  markdown: string
  initialMarkdown: string
  tokenCount: number
  order: number
  lastEditedTs: string | null
}

export const toEditableChunks = (chunks: KnowledgeChunk[]): EditableChunk[] =>
  chunks.map((chunk, index) => {
    const markdown = chunk.content ?? ''

    return {
      chunkId: chunk.chunk_id,
      originalChunkId: chunk.chunk_id,
      markdown,
      initialMarkdown: markdown,
      tokenCount: countTokens(markdown),
      order: chunk.order ?? index,
      lastEditedTs: chunk.last_edited_ts ?? null,
    }
  })

export const totalTokenCount = (chunks: EditableChunk[]): number =>
  chunks.reduce((acc, chunk) => acc + chunk.tokenCount, 0)

export const createEmptyChunk = (order: number = 0): EditableChunk => ({
  chunkId: crypto.randomUUID(),
  originalChunkId: '',
  markdown: '',
  initialMarkdown: '',
  tokenCount: 0,
  order,
  lastEditedTs: null,
})
