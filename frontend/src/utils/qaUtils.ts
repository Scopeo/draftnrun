import { logger } from '@/utils/logger'
import type { JudgeEvaluation, QATestCaseUI } from '@/types/qa'

export function getEvaluationForJudge(testCase: QATestCaseUI, judgeId: string): JudgeEvaluation | null {
  if (!testCase.evaluations || testCase.evaluations.length === 0) return null

  return testCase.evaluations.find(e => e.judge_id === judgeId) || null
}

/**
 * Get the last message from input for simplified display
 * @param input - Input object (can be a string JSON or an object)
 * @returns Last message object or null
 */
export function getLastMessage(input: string | Record<string, unknown>): { role: string; content: string } | null {
  const { messages } = parseQAInput(input)
  if (messages.length === 0) return null
  return messages[messages.length - 1]
}

/**
 * Parse input object and extract messages and additional fields
 * @param input - Input object (can be a string JSON or an object)
 * @returns Object containing messages array and additionalFields array
 */
export function parseQAInput(input: any): {
  messages: Array<{ role: string; content: string }>
  additionalFields: Array<{ key: string; value: string }>
} {
  const result = {
    messages: [] as Array<{ role: string; content: string }>,
    additionalFields: [] as Array<{ key: string; value: string }>,
  }

  if (!input) return result

  try {
    let inputObj = input

    // Parse if it's a JSON string
    if (typeof input === 'string') {
      try {
        inputObj = JSON.parse(input)
      } catch (e) {
        return result
      }
    }

    // Extract messages
    if (inputObj.messages && Array.isArray(inputObj.messages)) result.messages = inputObj.messages

    // Extract additional fields (all fields except 'messages')
    Object.keys(inputObj).forEach(key => {
      if (key !== 'messages') {
        result.additionalFields.push({
          key,
          value: typeof inputObj[key] === 'object' ? JSON.stringify(inputObj[key]) : String(inputObj[key]),
        })
      }
    })

    return result
  } catch (error) {
    logger.error('Error parsing QA input', { error })
    return result
  }
}
