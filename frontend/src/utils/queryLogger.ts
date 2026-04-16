/**
 * Performance logging utilities for TanStack Query.
 * All functions are no-ops in production builds (tree-shaken by Vite).
 */

interface QueryLog {
  queryKey: string
  startTime: number
  endTime?: number
  duration?: number
  cacheHit: boolean
  source: 'cache' | 'network' | 'error'
  componentName?: string
}

const queryLogs = import.meta.env.DEV ? new Map<string, QueryLog>() : (null as unknown as Map<string, QueryLog>)

function formatQueryKey(queryKey: unknown[]): string {
  return JSON.stringify(queryKey)
}

export function logQueryStart(queryKey: unknown[], componentName?: string): void {
  if (!import.meta.env.DEV) return

  const key = formatQueryKey(queryKey)
  const startTime = performance.now()

  queryLogs.set(key, {
    queryKey: key,
    startTime,
    cacheHit: false,
    source: 'network',
    componentName,
  })

  console.log(`[Query Start] ${key}`, {
    component: componentName,
    timestamp: new Date().toISOString(),
  })
}

export function logQueryEnd(queryKey: unknown[], cacheHit: boolean, error?: Error): void {
  if (!import.meta.env.DEV) return

  const key = formatQueryKey(queryKey)
  const log = queryLogs.get(key)

  if (!log) {
    console.warn(`[Query Logger] No start log found for ${key}`)
    return
  }

  const endTime = performance.now()
  const duration = endTime - log.startTime
  const source = error ? 'error' : cacheHit ? 'cache' : 'network'

  log.endTime = endTime
  log.duration = duration
  log.cacheHit = cacheHit
  log.source = source

  const logStyle = cacheHit ? 'color: #10b981; font-weight: bold' : 'color: #3b82f6; font-weight: bold'

  console.log(`%c[Query End] ${key}`, logStyle, {
    duration: `${duration.toFixed(2)}ms`,
    source,
    cacheHit,
    component: log.componentName,
    timestamp: new Date().toISOString(),
    error: error?.message,
  })

  if (queryLogs.size > 100) {
    const firstKey = queryLogs.keys().next().value

    if (firstKey) {
      queryLogs.delete(firstKey)
    }
  }
}

export function logCacheHit(queryKey: unknown[]): void {
  if (!import.meta.env.DEV) return

  const key = formatQueryKey(queryKey)

  console.log(`%c[Cache Hit] ${key}`, 'color: #10b981; font-weight: bold', {
    timestamp: new Date().toISOString(),
  })
}

export function logNetworkCall(queryKey: unknown[], endpoint: string): void {
  if (!import.meta.env.DEV) return

  const key = formatQueryKey(queryKey)

  console.log(`%c[Network Call] ${key}`, 'color: #3b82f6; font-weight: bold', {
    endpoint,
    timestamp: new Date().toISOString(),
  })
}

export function logComponentMount(componentName: string, queryKeys: unknown[][]): void {
  if (!import.meta.env.DEV) return

  console.log(`%c[Component Mount] ${componentName}`, 'color: #8b5cf6; font-weight: bold', {
    queries: queryKeys.map(formatQueryKey),
    timestamp: new Date().toISOString(),
  })
}

export function logComponentUnmount(componentName: string): void {
  if (!import.meta.env.DEV) return

  console.log(`%c[Component Unmount] ${componentName}`, 'color: #ef4444; font-weight: bold', {
    timestamp: new Date().toISOString(),
  })
}

export function getQueryPerformanceSummary(): Record<
  string,
  {
    totalCalls: number
    cacheHits: number
    networkCalls: number
    avgDuration: number
    errors: number
  }
> {
  if (!import.meta.env.DEV) return {}

  const summary: Record<string, any> = {}

  queryLogs.forEach(log => {
    if (!summary[log.queryKey]) {
      summary[log.queryKey] = {
        totalCalls: 0,
        cacheHits: 0,
        networkCalls: 0,
        totalDuration: 0,
        errors: 0,
      }
    }

    const stat = summary[log.queryKey]

    stat.totalCalls++

    if (log.source === 'cache') stat.cacheHits++
    if (log.source === 'network') stat.networkCalls++
    if (log.source === 'error') stat.errors++
    if (log.duration) stat.totalDuration += log.duration
  })

  Object.keys(summary).forEach(key => {
    const stat = summary[key]

    stat.avgDuration = stat.totalDuration / stat.totalCalls
    delete stat.totalDuration
  })

  return summary
}

export function logPerformanceSummary(): void {
  if (!import.meta.env.DEV) return

  const summary = getQueryPerformanceSummary()

  console.table(summary)
}
