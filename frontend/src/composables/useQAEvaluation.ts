import { ref, watch } from 'vue'
import { useSelectedOrg } from './useSelectedOrg'
import { qaEvaluationApi } from '@/api'
import { logger } from '@/utils/logger'
import type {
  EvaluationType,
  JudgeEvaluation,
  LLMJudge,
  LLMJudgeCreate,
  LLMJudgeDefaultsResponse,
  LLMJudgeUpdate,
} from '@/types/qa'

export function useQAEvaluation() {
  const { selectedOrgId } = useSelectedOrg()

  const judges = ref<LLMJudge[]>([])
  const error = ref<string | null>(null)

  const loadingStates = ref({
    judges: false,
    creating: false,
    updating: false,
    deleting: false,
    evaluating: false,
  })

  const fetchLLMJudges = async (orgId: string) => {
    if (!orgId) {
      error.value = 'No organization ID provided'

      return
    }

    loadingStates.value.judges = true
    error.value = null

    try {
      const data = await qaEvaluationApi.getLLMJudges(orgId)

      judges.value = data || []
    } catch (err: unknown) {
      error.value = err instanceof Error ? err.message : 'Failed to fetch LLM judges'
    } finally {
      loadingStates.value.judges = false
    }
  }

  const fetchLLMJudgeDefaults = async (evaluationType?: EvaluationType): Promise<LLMJudgeDefaultsResponse | null> => {
    error.value = null

    try {
      return await qaEvaluationApi.getLLMJudgeDefaults(evaluationType)
    } catch (err: unknown) {
      error.value = err instanceof Error ? err.message : 'Failed to fetch LLM judge defaults'

      return null
    }
  }

  const createJudge = async (orgId: string, judgeData: LLMJudgeCreate): Promise<LLMJudge | null> => {
    if (!orgId) {
      error.value = 'No organization ID provided'

      return null
    }

    loadingStates.value.creating = true
    error.value = null

    try {
      const created: LLMJudge = await qaEvaluationApi.createLLMJudge(orgId, judgeData)
      await fetchLLMJudges(orgId)

      return created
    } catch (err: unknown) {
      logger.error('[QA Judge] Failed to create judge', { orgId, name: judgeData.name, error: err })
      error.value = err instanceof Error ? err.message : 'Failed to create LLM judge'

      return null
    } finally {
      loadingStates.value.creating = false
    }
  }

  const updateJudge = async (orgId: string, judgeId: string, judgeData: LLMJudgeUpdate): Promise<boolean> => {
    if (!orgId || !judgeId) {
      error.value = 'Organization ID and Judge ID are required'

      return false
    }

    loadingStates.value.updating = true
    error.value = null

    try {
      await qaEvaluationApi.updateLLMJudge(orgId, judgeId, judgeData)
      await fetchLLMJudges(orgId)

      return true
    } catch (err: unknown) {
      error.value = err instanceof Error ? err.message : 'Failed to update LLM judge'

      return false
    } finally {
      loadingStates.value.updating = false
    }
  }

  const deleteJudges = async (orgId: string, judgeIds: string[]): Promise<boolean> => {
    if (!orgId || !judgeIds.length) {
      error.value = 'Organization ID and Judge IDs are required'

      return false
    }

    loadingStates.value.deleting = true
    error.value = null

    try {
      await qaEvaluationApi.deleteLLMJudges(orgId, judgeIds)
      await fetchLLMJudges(orgId)

      return true
    } catch (err: unknown) {
      logger.error('[QA Judge] Failed to delete judges', { orgId, count: judgeIds.length, error: err })
      error.value = err instanceof Error ? err.message : 'Failed to delete LLM judges'

      return false
    } finally {
      loadingStates.value.deleting = false
    }
  }

  const runEvaluations = async (
    projectId: string,
    judgeIds: string[],
    versionOutputIds: string[]
  ): Promise<Record<string, JudgeEvaluation[]>> => {
    if (!projectId || !judgeIds.length || !versionOutputIds.length) {
      error.value = 'Project ID, Judge IDs, and Version Output IDs are required'

      return {}
    }

    loadingStates.value.evaluating = true
    error.value = null

    const results: Record<string, JudgeEvaluation[]> = {}
    const totalEvaluations = judgeIds.length * versionOutputIds.length
    let completedCount = 0
    let errorCount = 0
    const errors: Array<{ judgeId: string; versionOutputId: string; error: string }> = []

    try {
      // Initialize results for each judge
      judgeIds.forEach(judgeId => {
        results[judgeId] = []
      })

      // Execute evaluations sequentially to avoid server overload
      for (const judgeId of judgeIds) {
        for (const versionOutputId of versionOutputIds) {
          try {
            const response = await qaEvaluationApi.runJudgeEvaluation(projectId, judgeId, versionOutputId)
            if (response) {
              results[judgeId].push(response)
              completedCount++
            }
          } catch (err: unknown) {
            errorCount++

            const errorMessage = err instanceof Error ? err.message : 'Unknown error'

            errors.push({ judgeId, versionOutputId, error: errorMessage })
          }
        }
      }

      // Set error message if there were any errors (but don't fail the whole operation)
      if (errorCount > 0 && completedCount === 0)
        error.value = `All evaluations failed. First error: ${errors[0]?.error || 'Unknown error'}`
      else if (errorCount > 0) error.value = `${errorCount} evaluation(s) failed out of ${totalEvaluations}`

      return results
    } catch (err: unknown) {
      logger.error('[QA Evaluation] Failed to run evaluations', { projectId, error: err })
      error.value = err instanceof Error ? err.message : 'Failed to run evaluations'

      return results
    } finally {
      loadingStates.value.evaluating = false
    }
  }

  const fetchEvaluationsForVersionOutput = async (
    projectId: string,
    versionOutputId: string
  ): Promise<JudgeEvaluation[]> => {
    if (!projectId || !versionOutputId) {
      error.value = 'Project ID and Version Output ID are required'

      return []
    }

    error.value = null

    try {
      const data = await qaEvaluationApi.getEvaluationsByVersionOutput(projectId, versionOutputId)

      return data || []
    } catch (err: unknown) {
      error.value = err instanceof Error ? err.message : 'Failed to fetch evaluations'

      return []
    }
  }

  const deleteEvaluationsForVersionOutput = async (projectId: string, versionOutputId: string): Promise<boolean> => {
    if (!projectId || !versionOutputId) {
      error.value = 'Project ID and Version Output ID are required'

      return false
    }

    error.value = null

    try {
      const evaluations = await fetchEvaluationsForVersionOutput(projectId, versionOutputId)
      if (evaluations.length === 0) return true

      const evaluationIds = evaluations.map(e => e.id)

      await qaEvaluationApi.deleteEvaluations(projectId, evaluationIds)

      return true
    } catch (err: unknown) {
      error.value = err instanceof Error ? err.message : 'Failed to delete evaluations'

      return false
    }
  }

  const deleteEvaluationsForInputGroundtruth = async (
    projectId: string,
    datasetId: string,
    inputGroundtruthId: string,
    graphRunners: Array<{ id: string }>
  ): Promise<boolean> => {
    if (!projectId || !datasetId || !inputGroundtruthId) {
      error.value = 'Project ID, Dataset ID, and Input Groundtruth ID are required'

      return false
    }

    error.value = null

    try {
      // Parallelize fetching version output IDs for all graph runners
      const versionOutputIdsPromises = graphRunners.map(async runner => {
        try {
          const versionOutputIdsDict = await qaEvaluationApi.getVersionOutputIds(projectId, runner.id, [
            inputGroundtruthId,
          ])

          return versionOutputIdsDict?.[inputGroundtruthId] || null
        } catch (err: unknown) {
          // Silently skip if version output IDs cannot be fetched for this runner
          return null
        }
      })

      const versionOutputIdsResults = await Promise.all(versionOutputIdsPromises)
      const versionOutputIds = versionOutputIdsResults.filter((id): id is string => id !== null)

      if (versionOutputIds.length === 0) return true

      // Parallelize fetching evaluations for all version outputs
      const evaluationsPromises = versionOutputIds.map(async versionOutputId => {
        try {
          const evaluations = await fetchEvaluationsForVersionOutput(projectId, versionOutputId)

          return evaluations.map(e => e.id)
        } catch (err: unknown) {
          // Silently skip if evaluations cannot be fetched for this version output
          return []
        }
      })

      const evaluationIdsArrays = await Promise.all(evaluationsPromises)
      const allEvaluationIds = evaluationIdsArrays.flat()

      if (allEvaluationIds.length > 0) await qaEvaluationApi.deleteEvaluations(projectId, allEvaluationIds)

      return true
    } catch (err: unknown) {
      error.value = err instanceof Error ? err.message : 'Failed to delete evaluations'

      return false
    }
  }

  const setJudgeProjects = async (orgId: string, judgeId: string, projectIds: string[]): Promise<boolean> => {
    if (!orgId || !judgeId) {
      error.value = 'Organization ID and Judge ID are required'
      return false
    }
    error.value = null
    try {
      await qaEvaluationApi.setJudgeProjects(orgId, judgeId, projectIds)
      await fetchLLMJudges(orgId)
      return true
    } catch (err: unknown) {
      logger.error('[QA Judge] Failed to set judge projects', { orgId, judgeId, error: err })
      error.value = err instanceof Error ? err.message : 'Failed to update judge projects'
      return false
    }
  }

  watch(
    () => selectedOrgId.value,
    () => {
      judges.value = []
      error.value = null
    }
  )

  return {
    judges,
    error,
    loadingStates,
    fetchLLMJudges,
    fetchLLMJudgeDefaults,
    createJudge,
    updateJudge,
    deleteJudges,
    setJudgeProjects,
    runEvaluations,
    fetchEvaluationsForVersionOutput,
    deleteEvaluationsForVersionOutput,
    deleteEvaluationsForInputGroundtruth,
  }
}
