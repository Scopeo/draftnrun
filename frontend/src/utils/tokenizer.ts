import { encode } from 'gpt-tokenizer'
import { logger } from '@/utils/logger'

export const MAX_CHUNK_TOKENS = 8000

export const countTokens = (text: string | null | undefined): number => {
  if (!text) return 0

  try {
    return encode(text).length
  } catch (error) {
    logger.error('Failed to compute token count', { error })
    return Math.ceil(text.length / 4)
  }
}
