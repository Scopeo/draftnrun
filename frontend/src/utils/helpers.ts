export const isEmpty = (value: unknown): boolean => {
  if (value === null || value === undefined || value === '') return true

  return !!(Array.isArray(value) && value.length === 0)
}

export const isNullOrUndefined = (value: unknown): value is undefined | null => {
  return value === null || value === undefined
}

export const isEmptyArray = (arr: unknown): boolean => {
  return Array.isArray(arr) && arr.length === 0
}

export const isObject = (obj: unknown): obj is Record<string, unknown> =>
  obj !== null && !!obj && typeof obj === 'object' && !Array.isArray(obj)
