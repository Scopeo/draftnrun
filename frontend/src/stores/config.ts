import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

type Theme = 'light' | 'dark' | 'system'

const LS_THEME = 'draftnrun-theme'

export const useConfigStore = defineStore('config', () => {
  const theme = ref<Theme>((localStorage.getItem(LS_THEME) as Theme) || 'light')

  const resolvedTheme = computed<'light' | 'dark'>(() => {
    if (theme.value !== 'system') return theme.value
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  })

  function toggleTheme() {
    const cycle: Theme[] = ['light', 'dark', 'system']

    theme.value = cycle[(cycle.indexOf(theme.value) + 1) % cycle.length]
    localStorage.setItem(LS_THEME, theme.value)
  }

  return {
    theme,
    resolvedTheme,
    toggleTheme,
  }
})
