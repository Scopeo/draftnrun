import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import * as Sentry from '@sentry/vue'
import { useAuthStore } from '../auth'
import type { UserData } from '@/services/auth'
import type { AppAbilityRawRule } from '@/utils/abilityRules'

vi.mock('@sentry/vue', () => ({
  setUser: vi.fn(),
  captureException: vi.fn(),
  captureMessage: vi.fn(),
  addBreadcrumb: vi.fn(),
}))

const fakeUser: UserData = {
  id: 'u1',
  fullName: 'Alice',
  username: 'alice',
  email: 'alice@example.com',
}

const fakeRules: AppAbilityRawRule[] = [{ action: 'manage', subject: 'all' }]

describe('useAuthStore', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('setAuth stores userData, accessToken and abilityRules in state and localStorage', () => {
    const store = useAuthStore()

    store.setAuth(fakeUser, 'tok-123', fakeRules)

    expect(store.userData).toEqual(fakeUser)
    expect(store.accessToken).toBe('tok-123')
    expect(store.abilityRules).toEqual(fakeRules)
    expect(localStorage.getItem('userData')).toBe(JSON.stringify(fakeUser))
    expect(localStorage.getItem('accessToken')).toBe('tok-123')
    expect(localStorage.getItem('userAbilityRules')).toBe(JSON.stringify(fakeRules))
    expect(Sentry.setUser).toHaveBeenCalledWith({ id: 'u1', email: 'alice@example.com' })
  })

  it('clearAuth clears state and localStorage', () => {
    const store = useAuthStore()

    store.setAuth(fakeUser, 'tok-123', fakeRules)
    vi.clearAllMocks()

    store.clearAuth()

    expect(store.userData).toBeNull()
    expect(store.accessToken).toBeNull()
    expect(store.abilityRules).toEqual([])
    expect(localStorage.getItem('userData')).toBeNull()
    expect(localStorage.getItem('accessToken')).toBeNull()
    expect(localStorage.getItem('userAbilityRules')).toBeNull()
    expect(Sentry.setUser).toHaveBeenCalledWith(null)
  })

  it('isAuthenticated returns true when both userData and accessToken exist', () => {
    const store = useAuthStore()

    expect(store.isAuthenticated).toBe(false)

    store.setAuth(fakeUser, 'tok-123', fakeRules)
    expect(store.isAuthenticated).toBe(true)
  })

  it('updateAbilities updates rules in state and localStorage', () => {
    const store = useAuthStore()
    const newRules: AppAbilityRawRule[] = [{ action: 'read', subject: 'Project' }]

    store.updateAbilities(newRules)

    expect(store.abilityRules).toEqual(newRules)
    expect(localStorage.getItem('userAbilityRules')).toBe(JSON.stringify(newRules))
  })

  it('hydrates from localStorage on store creation', () => {
    localStorage.setItem('userData', JSON.stringify(fakeUser))
    localStorage.setItem('accessToken', 'persisted-tok')
    localStorage.setItem('userAbilityRules', JSON.stringify(fakeRules))

    setActivePinia(createPinia())

    const store = useAuthStore()

    expect(store.userData).toEqual(fakeUser)
    expect(store.accessToken).toBe('persisted-tok')
    expect(store.abilityRules).toEqual(fakeRules)
    expect(store.isAuthenticated).toBe(true)
  })
})
