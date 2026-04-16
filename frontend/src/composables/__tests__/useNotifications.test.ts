import { beforeEach, describe, expect, it } from 'vitest'
import { useNotifications } from '../useNotifications'

describe('useNotifications', () => {
  let api: ReturnType<typeof useNotifications>

  beforeEach(() => {
    api = useNotifications()
    // Drain leftover notifications from previous tests (shared module state)
    for (const n of [...api.notifications.value]) {
      api.remove(n.id)
    }
  })

  it('notify.success adds a notification with color success', () => {
    api.notify.success('Saved!')

    const last = api.notifications.value.at(-1)!

    expect(last.message).toBe('Saved!')
    expect(last.color).toBe('success')
    expect(last.timeout).toBe(3000)
  })

  it('notify.error adds a notification with timeout 5000', () => {
    api.notify.error('Failed!')

    const last = api.notifications.value.at(-1)!

    expect(last.message).toBe('Failed!')
    expect(last.color).toBe('error')
    expect(last.timeout).toBe(5000)
  })

  it('remove(id) removes the specific notification', () => {
    api.notify.success('A')
    api.notify.success('B')

    const idA = api.notifications.value.find(n => n.message === 'A')!.id

    api.remove(idA)

    expect(api.notifications.value.find(n => n.message === 'A')).toBeUndefined()
    expect(api.notifications.value.find(n => n.message === 'B')).toBeDefined()
  })

  it('notifications have unique IDs', () => {
    api.notify.info('x')
    api.notify.info('y')
    api.notify.info('z')

    const ids = api.notifications.value.map(n => n.id)

    expect(new Set(ids).size).toBe(ids.length)
  })
})
