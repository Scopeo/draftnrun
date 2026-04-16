import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import * as Sentry from '@sentry/vue'
import type { UserData } from '@/services/auth'
import type { AppAbilityRawRule } from '@/utils/abilityRules'

const LS_USER_DATA = 'userData'
const LS_ACCESS_TOKEN = 'accessToken'
const LS_ABILITY_RULES = 'userAbilityRules'

function readJson<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key)
    return raw ? JSON.parse(raw) : fallback
  } catch (error: unknown) {
    return fallback
  }
}

export const useAuthStore = defineStore('auth', () => {
  // --- State (hydrated from localStorage) ---
  const userData = ref<UserData | null>(readJson<UserData | null>(LS_USER_DATA, null))
  const accessToken = ref<string | null>(localStorage.getItem(LS_ACCESS_TOKEN))
  const abilityRules = ref<AppAbilityRawRule[]>(readJson<AppAbilityRawRule[]>(LS_ABILITY_RULES, []))

  // --- Computed ---
  const isAuthenticated = computed(() => !!(userData.value && accessToken.value))

  // --- Persistence helpers ---
  function persistUserData(data: UserData | null) {
    if (data) {
      localStorage.setItem(LS_USER_DATA, JSON.stringify(data))
    } else {
      localStorage.removeItem(LS_USER_DATA)
    }
  }

  function persistAccessToken(token: string | null) {
    if (token) {
      localStorage.setItem(LS_ACCESS_TOKEN, token)
    } else {
      localStorage.removeItem(LS_ACCESS_TOKEN)
    }
  }

  function persistAbilityRules(rules: AppAbilityRawRule[]) {
    if (rules.length > 0) {
      localStorage.setItem(LS_ABILITY_RULES, JSON.stringify(rules))
    } else {
      localStorage.removeItem(LS_ABILITY_RULES)
    }
  }

  // --- Actions ---
  function setAuth(newUserData: UserData, token: string, rules: AppAbilityRawRule[]) {
    userData.value = newUserData
    accessToken.value = token
    abilityRules.value = rules

    persistUserData(newUserData)
    persistAccessToken(token)
    persistAbilityRules(rules)

    Sentry.setUser({ id: newUserData.id, email: newUserData.email })
  }

  function clearAuth() {
    userData.value = null
    accessToken.value = null
    abilityRules.value = []

    localStorage.removeItem(LS_USER_DATA)
    localStorage.removeItem(LS_ACCESS_TOKEN)
    localStorage.removeItem(LS_ABILITY_RULES)

    Sentry.setUser(null)
  }

  function updateAbilities(rules: AppAbilityRawRule[]) {
    abilityRules.value = rules
    persistAbilityRules(rules)
  }

  function updateUserData(data: UserData) {
    userData.value = data
    persistUserData(data)
    Sentry.setUser({ id: data.id, email: data.email })
  }

  function updateAccessToken(token: string) {
    accessToken.value = token
    persistAccessToken(token)
  }

  // Hydrate Sentry on store creation if user is already authenticated
  if (userData.value) {
    Sentry.setUser({ id: userData.value.id, email: userData.value.email })
  }

  return {
    // State
    userData,
    accessToken,
    abilityRules,

    // Computed
    isAuthenticated,

    // Actions
    setAuth,
    clearAuth,
    updateAbilities,
    updateUserData,
    updateAccessToken,
  }
})
