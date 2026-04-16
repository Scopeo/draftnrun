import { computed } from 'vue'
import { useLLMModelsQuery } from './queries/useLLMModelsQuery'
import { useSelectedOrg } from './useSelectedOrg'
import { formatNumberWithSpaces } from '@/utils/formatters'
import type { CreditFields } from '@/types/credits'
import type { LLMModel } from '@/types/llmModels'

export function useLLMCredits() {
  const { selectedOrgId } = useSelectedOrg()

  // Use TanStack Query instead of manual fetching
  const { data: llmModelsData } = useLLMModelsQuery(selectedOrgId)

  const llmModels = computed(() => llmModelsData.value || [])

  /**
   * Get credit display text for an LLM model
   */
  function getModelCreditDisplay(model: LLMModel | null): string {
    if (!model) return 'Free'

    const parts: string[] = []

    // Check credits_per_input_token
    if (model.credits_per_input_token !== null && model.credits_per_input_token !== undefined) {
      parts.push(`${formatNumberWithSpaces(model.credits_per_input_token)} credits/1M input tokens`)
    }

    // Check credits_per_output_token
    if (model.credits_per_output_token !== null && model.credits_per_output_token !== undefined) {
      parts.push(`${formatNumberWithSpaces(model.credits_per_output_token)} credits/1M output tokens`)
    }

    // If no token credits, show Free
    if (parts.length === 0) return 'Free'

    return parts.join(', ')
  }

  /**
   * Get credit display text for a component/tool
   * Works with any object that implements CreditFields
   */
  function getCreditDisplay(component: CreditFields & { parameters?: Array<{ type?: string }> }): string {
    // Check credits_per_call first
    if (component.credits_per_call !== null && component.credits_per_call !== undefined) {
      return `${component.credits_per_call} credits/run`
    }

    // Check credits_per dictionary
    if (component.credits_per && typeof component.credits_per === 'object') {
      const entries = Object.entries(component.credits_per)
      if (entries.length > 0) {
        // Show first entry, or join multiple with comma
        const parts = entries
          .map(([key, value]) => {
            if (value !== null && value !== undefined) {
              return `${formatNumberWithSpaces(value)} credits/${key}`
            }
            return null
          })
          .filter(Boolean)

        if (parts.length > 0) {
          return parts.join(', ')
        }
      }
    }

    // Check for llm_model parameter type
    const hasLLMModel = component.parameters?.some(param => param.type === 'llm_model')
    if (hasLLMModel) {
      return 'Model cost'
    }

    // If all credit fields are null and no LLM model, show Free
    return 'Free'
  }

  /**
   * Convert select options to items with credit information for LLM model selects
   */
  function getLLMModelItems(options: Array<{ label: string; value: any }>) {
    return options.map((option: { label: string; value: any }) => {
      // Find matching LLM model - prioritize display_name matching with label (case-insensitive)
      let model = llmModels.value.find(m => m.display_name?.toLowerCase().trim() === option.label?.toLowerCase().trim())
      if (!model) {
        // Fallback to ID matching
        model = llmModels.value.find(m => m.id === option.value)
      }
      if (!model) {
        // Fallback to model_name matching
        model = llmModels.value.find(m => m.model_name === option.value)
      }

      // If still no match, try partial display_name match
      if (!model && option.label) {
        model = llmModels.value.find(
          m =>
            m.display_name?.toLowerCase().includes(option.label.toLowerCase()) ||
            option.label.toLowerCase().includes(m.display_name?.toLowerCase() || '')
        )
      }

      const creditDisplay = getModelCreditDisplay(model || null)

      return {
        title: option.label,
        subtitle: creditDisplay,
        value: option.value,
      }
    })
  }

  return {
    llmModels,
    getModelCreditDisplay,
    getCreditDisplay,
    getLLMModelItems,
  }
}
