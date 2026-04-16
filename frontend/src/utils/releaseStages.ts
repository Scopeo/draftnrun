export const RELEASE_STAGE_ORDER: Record<string, number> = {
  internal: 0,
  beta: 1,
  early_access: 2,
  public: 3,
}

export const normalizeReleaseStage = (stage: string | null | undefined): keyof typeof RELEASE_STAGE_ORDER => {
  if (!stage) return 'public'

  const normalized = String(stage).trim().toLowerCase().replace(/\s+/g, '_').replace(/-/g, '_')

  return (normalized in RELEASE_STAGE_ORDER ? normalized : 'public') as keyof typeof RELEASE_STAGE_ORDER
}

export const getReleaseStageRank = (stage: string | null | undefined): number => {
  const key = normalizeReleaseStage(stage)
  return RELEASE_STAGE_ORDER[key]
}

export const compareReleaseStages = (a: string, b: string): number => {
  return getReleaseStageRank(a) - getReleaseStageRank(b)
}

export type ReleaseStageName = keyof typeof RELEASE_STAGE_ORDER
