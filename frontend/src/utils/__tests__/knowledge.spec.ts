import { describe, expect, it } from 'vitest'

import { type EditableChunk, toEditableChunks, totalTokenCount } from '../knowledge'

describe('toEditableChunks', () => {
  it('converts knowledge chunks to editable chunks', () => {
    const chunks = [
      {
        chunk_id: 'chunk-1',
        file_id: 'file-1',
        content: '# Hello World',
        order: 0,
        last_edited_ts: '2024-01-01T00:00:00Z',
      },
    ]

    const result = toEditableChunks(chunks)

    expect(result).toHaveLength(1)
    expect(result[0].chunkId).toBe('chunk-1')
    expect(result[0].originalChunkId).toBe('chunk-1')
    expect(result[0].markdown).toBe('# Hello World')
    expect(result[0].initialMarkdown).toBe('# Hello World')
    expect(result[0].order).toBe(0)
    expect(result[0].lastEditedTs).toBe('2024-01-01T00:00:00Z')
  })

  it('handles empty content', () => {
    const chunks = [
      {
        chunk_id: 'chunk-1',
        file_id: 'file-1',
        content: '',
        order: 0,
        last_edited_ts: null,
      },
    ]

    const result = toEditableChunks(chunks)

    expect(result[0].markdown).toBe('')
    expect(result[0].tokenCount).toBe(0)
  })

  it('handles null last_edited_ts', () => {
    const chunks = [
      {
        chunk_id: 'chunk-1',
        file_id: 'file-1',
        content: 'Some content',
        order: 0,
        last_edited_ts: null,
      },
    ]

    const result = toEditableChunks(chunks)

    expect(result[0].lastEditedTs).toBeNull()
  })
})

describe('totalTokenCount', () => {
  it('sums token counts from all chunks', () => {
    const chunks: EditableChunk[] = [
      {
        chunkId: 'chunk-1',
        originalChunkId: 'chunk-1',
        markdown: 'Hello',
        initialMarkdown: 'Hello',
        tokenCount: 10,
        order: 0,
        lastEditedTs: null,
      },
      {
        chunkId: 'chunk-2',
        originalChunkId: 'chunk-2',
        markdown: 'World',
        initialMarkdown: 'World',
        tokenCount: 20,
        order: 1,
        lastEditedTs: null,
      },
    ]

    expect(totalTokenCount(chunks)).toBe(30)
  })

  it('returns 0 for empty array', () => {
    expect(totalTokenCount([])).toBe(0)
  })
})
