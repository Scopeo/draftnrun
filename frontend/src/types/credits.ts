export interface CreditFields {
  credits_per_call?: number | null
  credits_per?: Record<string, number> | null
}

export const CREDIT_FIELD_KEYS = ['credits_per_call', 'credits_per'] as const

export type CreditFieldKey = (typeof CREDIT_FIELD_KEYS)[number]

export const CREDIT_FIELD_LABELS: Record<CreditFieldKey, string> = {
  credits_per_call: 'Credits per Call',
  credits_per: 'Credits per',
} as const

export const CREDIT_FIELD_TOOLTIPS: Record<CreditFieldKey, string> = {
  credits_per_call: 'A fixed credit amount charged once for each request, regardless of token usage.',
  credits_per: 'Credits charged per as a dictionary (key-value pairs).',
} as const

export const CREDIT_TABLE_COLUMNS = [
  { title: 'Credits/Call', key: 'credits_per_call' },
  { title: 'Credits per', key: 'credits_per' },
] as const
