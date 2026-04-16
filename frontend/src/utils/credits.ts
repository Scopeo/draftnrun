import type { CreditFields } from '@/types/credits'

export const CREDIT_FIELD_CONFIG = {
  STEP: 0.0001,
  MIN: 0,
} as const

export function initializeCreditForm(source?: Partial<CreditFields>): CreditFields {
  return {
    credits_per_call: source?.credits_per_call ?? null,
    credits_per: source?.credits_per ?? null,
  }
}

export function resetCreditForm(): CreditFields {
  return {
    credits_per_call: null,
    credits_per: null,
  }
}

export function hasCreditValue(value: number | null | undefined): boolean {
  return value !== null && value !== undefined
}

export function validateCreditValue(value: number | null): boolean {
  if (value === null) return true
  return value >= CREDIT_FIELD_CONFIG.MIN && value <= Number.MAX_SAFE_INTEGER
}

export function validateCreditDict(value: Record<string, number> | null | undefined): boolean {
  if (value === null || value === undefined) return true
  return Object.values(value).every(v => {
    if (typeof v !== 'number') return false
    return validateCreditValue(v)
  })
}

export function validateCreditFields(fields: CreditFields): boolean {
  const callValid = validateCreditValue(fields.credits_per_call ?? null)
  const unitValid = validateCreditDict(fields.credits_per)
  return callValid && unitValid
}

export function updateCreditFields(target: Partial<CreditFields>, source: CreditFields | null): void {
  if (source === null) {
    target.credits_per_call = null
    target.credits_per = null
  } else {
    target.credits_per_call = source.credits_per_call
    target.credits_per = source.credits_per
  }
}

export function convertEmptyToNull(value: number | string | null | undefined): number | null {
  if (value === '' || value === undefined) return null
  if (value === null) return null
  return typeof value === 'string' ? Number.parseFloat(value) || null : value
}
