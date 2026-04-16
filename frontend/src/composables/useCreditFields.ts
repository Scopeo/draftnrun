import { computed, ref } from 'vue'
import type { CreditFields } from '@/types/credits'
import { initializeCreditForm, resetCreditForm, validateCreditFields } from '@/utils/credits'

export function useCreditFields(initialValue?: Partial<CreditFields>) {
  const creditFields = ref<CreditFields>(initializeCreditForm(initialValue))
  const errors = ref<Partial<Record<keyof CreditFields, string>>>({})

  const reset = () => {
    creditFields.value = resetCreditForm()
    errors.value = {}
  }

  const initialize = (source?: Partial<CreditFields>) => {
    creditFields.value = initializeCreditForm(source)
    errors.value = {}
  }

  const validate = (): boolean => {
    const isValid = validateCreditFields(creditFields.value)

    if (!isValid) {
      // Set errors for invalid fields
      Object.entries(creditFields.value).forEach(([key, value]) => {
        if (typeof value === 'number' && value < 0) {
          errors.value[key as keyof CreditFields] = 'Credit value must be non-negative'
        }
      })
    } else {
      errors.value = {}
    }

    return isValid
  }

  const hasAnyValue = computed(() => {
    return Object.values(creditFields.value).some(value => value !== null && value !== undefined)
  })

  const toApiPayload = computed(() => creditFields.value)

  return {
    creditFields,
    errors,
    reset,
    initialize,
    validate,
    hasAnyValue,
    toApiPayload,
  }
}
