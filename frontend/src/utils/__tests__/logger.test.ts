import { beforeEach, describe, expect, it, vi } from 'vitest'

import * as Sentry from '@sentry/vue'
import { logger } from '../logger'

vi.mock('@sentry/vue', () => ({
  captureException: vi.fn(),
  captureMessage: vi.fn(),
  addBreadcrumb: vi.fn(),
}))

describe('logger', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('logger.info adds a breadcrumb', () => {
    logger.info('hello', { foo: 'bar' })

    expect(Sentry.addBreadcrumb).toHaveBeenCalledWith({
      category: 'app',
      message: 'hello',
      level: 'info',
      data: { foo: 'bar' },
    })
    expect(Sentry.captureException).not.toHaveBeenCalled()
    expect(Sentry.captureMessage).not.toHaveBeenCalled()
  })

  it('logger.error calls captureException with an Error and extra context', () => {
    logger.error('something broke', { detail: 42 })

    expect(Sentry.captureException).toHaveBeenCalledWith(expect.any(Error), { extra: { detail: 42 } })

    const errorArg = vi.mocked(Sentry.captureException).mock.calls[0][0] as Error

    expect(errorArg.message).toBe('something broke')

    expect(Sentry.addBreadcrumb).toHaveBeenCalledWith(
      expect.objectContaining({ level: 'error', message: 'something broke' })
    )
  })

  it('logger.warn calls captureMessage with warning level', () => {
    logger.warn('heads up', { ctx: 'test' })

    expect(Sentry.captureMessage).toHaveBeenCalledWith('heads up', {
      level: 'warning',
      extra: { ctx: 'test' },
    })
    expect(Sentry.addBreadcrumb).toHaveBeenCalledWith(
      expect.objectContaining({ level: 'warning', message: 'heads up' })
    )
  })

  it('produces console output in DEV mode', () => {
    const infoSpy = vi.spyOn(console, 'info').mockImplementation(() => {})
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})

    logger.info('i')
    logger.warn('w')
    logger.error('e')

    expect(infoSpy).toHaveBeenCalledWith('[INFO] i', '')
    expect(warnSpy).toHaveBeenCalledWith('[WARN] w', '')
    expect(errorSpy).toHaveBeenCalledWith('[ERROR] e', '')

    infoSpy.mockRestore()
    warnSpy.mockRestore()
    errorSpy.mockRestore()
  })
})
