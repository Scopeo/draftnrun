import DiffMatchPatch from 'diff-match-patch'

export interface DiffSegment {
  type: 'equal' | 'added' | 'removed'
  value: string
}

const TYPE_MAP: Record<number, DiffSegment['type']> = {
  [DiffMatchPatch.DIFF_EQUAL]: 'equal',
  [DiffMatchPatch.DIFF_INSERT]: 'added',
  [DiffMatchPatch.DIFF_DELETE]: 'removed',
}

export function computeWordDiff(oldText: string, newText: string): DiffSegment[] {
  const dmp = new DiffMatchPatch()
  const diffs = dmp.diff_main(oldText, newText)
  dmp.diff_cleanupSemantic(diffs)

  return diffs.map(([op, text]) => ({ type: TYPE_MAP[op], value: text }))
}
