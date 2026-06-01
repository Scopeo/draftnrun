import type { GraphRunner } from '@/types/version'

interface VersionSelectionOptions {
  currentGraphRunner: GraphRunner | null
  updatedGraphRunners: GraphRunner[]
  env: 'production' | 'draft'
}

export function resolveGraphRunnerAfterVersionAction({
  currentGraphRunner,
  updatedGraphRunners,
  env,
}: VersionSelectionOptions): GraphRunner | null {
  if (env === 'draft') {
    return updatedGraphRunners.find(runner => runner.env === 'draft') || updatedGraphRunners[0] || null
  }

  if (!currentGraphRunner) return null

  const runnerStillExists = updatedGraphRunners.some(
    runner => runner.graph_runner_id === currentGraphRunner.graph_runner_id
  )

  if (runnerStillExists) return null

  return updatedGraphRunners.find(runner => runner.env === 'draft') || updatedGraphRunners[0] || null
}
