import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useConfigStore } from '../config'

describe('useConfigStore', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
    vi.restoreAllMocks()
  })

  it('theme defaults to light when localStorage is empty', () => {
    const store = useConfigStore()

    expect(store.theme).toBe('light')
  })

  it('toggleTheme cycles light → dark → system → light', () => {
    const store = useConfigStore()

    expect(store.theme).toBe('light')

    store.toggleTheme()
    expect(store.theme).toBe('dark')
    expect(localStorage.getItem('draftnrun-theme')).toBe('dark')

    store.toggleTheme()
    expect(store.theme).toBe('system')
    expect(localStorage.getItem('draftnrun-theme')).toBe('system')

    store.toggleTheme()
    expect(store.theme).toBe('light')
    expect(localStorage.getItem('draftnrun-theme')).toBe('light')
  })

  it('resolvedTheme returns the literal theme when not system', () => {
    const store = useConfigStore()

    expect(store.resolvedTheme).toBe('light')

    store.toggleTheme()
    expect(store.resolvedTheme).toBe('dark')
  })

  it('resolvedTheme uses matchMedia for system preference (dark)', () => {
    vi.spyOn(window, 'matchMedia').mockReturnValue({
      matches: true,
    } as MediaQueryList)

    const store = useConfigStore()

    store.toggleTheme() // dark
    store.toggleTheme() // system

    expect(store.resolvedTheme).toBe('dark')
  })

  it('resolvedTheme uses matchMedia for system preference (light)', () => {
    vi.spyOn(window, 'matchMedia').mockReturnValue({
      matches: false,
    } as MediaQueryList)

    const store = useConfigStore()

    store.toggleTheme() // dark
    store.toggleTheme() // system

    expect(store.resolvedTheme).toBe('light')
  })
})
