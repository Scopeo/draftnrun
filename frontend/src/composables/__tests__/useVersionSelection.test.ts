import { describe, expect, it } from 'vitest'
import { resolveGraphRunnerAfterVersionAction } from '../useVersionSelection'
import type { GraphRunner } from '@/types/version'

const runner = (graphRunnerId: string, env: GraphRunner['env']): GraphRunner => ({
  graph_runner_id: graphRunnerId,
  env,
  tag_name: env === 'draft' ? null : `v-${graphRunnerId}`,
})

describe('resolveGraphRunnerAfterVersionAction', () => {
  it('selects the refreshed draft after loading a version as draft', () => {
    const current = runner('saved-version', null)
    const refreshedDraft = runner('new-draft', 'draft')

    expect(
      resolveGraphRunnerAfterVersionAction({
        currentGraphRunner: current,
        updatedGraphRunners: [current, refreshedDraft],
        env: 'draft',
      })
    ).toBe(refreshedDraft)
  })

  it('keeps the current runner after production deployment when it still exists', () => {
    const current = runner('saved-version', null)

    expect(
      resolveGraphRunnerAfterVersionAction({
        currentGraphRunner: current,
        updatedGraphRunners: [current, runner('draft', 'draft')],
        env: 'production',
      })
    ).toBeNull()
  })

  it('falls back to the draft after production deployment removes the current runner', () => {
    const refreshedDraft = runner('draft', 'draft')

    expect(
      resolveGraphRunnerAfterVersionAction({
        currentGraphRunner: runner('deleted-runner', null),
        updatedGraphRunners: [runner('production', 'production'), refreshedDraft],
        env: 'production',
      })
    ).toBe(refreshedDraft)
  })
})
