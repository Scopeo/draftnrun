import * as Sentry from '@sentry/vue'

type LogLevel = 'info' | 'warn' | 'error'
type BreadcrumbLevel = 'info' | 'warning' | 'error'

function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object' && !Array.isArray(value)
}

function normalizeMessage(messageOrError: unknown): string {
  if (typeof messageOrError === 'string') return messageOrError
  if (messageOrError instanceof Error) return messageOrError.message
  if (messageOrError === null || messageOrError === undefined) return 'Unknown error'
  try {
    return JSON.stringify(messageOrError)
  } catch {
    return String(messageOrError)
  }
}

function normalizeContext(contextParts: unknown[]): Record<string, unknown> | undefined {
  if (contextParts.length === 0) return undefined
  if (contextParts.length === 1) {
    const single = contextParts[0]

    if (isRecord(single)) return single

    return { data: single }
  }

  return { args: contextParts }
}

function toBreadcrumbLevel(level: LogLevel): BreadcrumbLevel {
  if (level === 'warn') return 'warning'
  return level
}

function log(level: LogLevel, messageOrError: unknown, ...contextParts: unknown[]) {
  const message = normalizeMessage(messageOrError)
  const context = normalizeContext(contextParts)
  const breadcrumbLevel = toBreadcrumbLevel(level)

  if (level === 'error') {
    const error = messageOrError instanceof Error ? messageOrError : new Error(message)

    Sentry.captureException(error, { extra: context })
  } else if (level === 'warn') {
    Sentry.captureMessage(message, { level: 'warning', extra: context })
  }

  Sentry.addBreadcrumb({ category: 'app', message, level: breadcrumbLevel, data: context })
  if (import.meta.env.DEV) console[level](`[${level.toUpperCase()}] ${message}`, context ?? '')
}

export const logger = {
  info: (messageOrError: unknown, ...contextParts: unknown[]) => log('info', messageOrError, ...contextParts),
  warn: (messageOrError: unknown, ...contextParts: unknown[]) => log('warn', messageOrError, ...contextParts),
  error: (messageOrError: unknown, ...contextParts: unknown[]) => log('error', messageOrError, ...contextParts),
}
