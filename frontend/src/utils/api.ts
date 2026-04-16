import { FetchError, ofetch } from 'ofetch'
import { logout, supabase } from '@/services/auth'
import { logger } from '@/utils/logger'

// Shared constant for session expiry flag
export const SESSION_EXPIRED_KEY = 'sessionExpired'

// Token refresh state - handles concurrent 401s
let isRefreshing = false
let refreshPromise: Promise<boolean> | null = null

/**
 * Attempts to refresh the auth token.
 * Returns true if refresh succeeded, false if logout occurred.
 * All concurrent calls share the same promise to avoid race conditions.
 */
const attemptTokenRefresh = async (): Promise<boolean> => {
  if (refreshPromise) {
    return refreshPromise
  }

  isRefreshing = true
  refreshPromise = (async () => {
    try {
      const { error: refreshError } = await supabase.auth.refreshSession()
      if (refreshError) throw refreshError
      return true
    } catch (error: unknown) {
      logger.warn('Token refresh failed', { error })
      sessionStorage.setItem(SESSION_EXPIRED_KEY, 'true')
      await logout()
      return false
    } finally {
      isRefreshing = false
      refreshPromise = null
    }
  })()

  return refreshPromise
}

/**
 * Build auth headers for raw fetch calls that can't use $api (e.g. blob downloads, 202 handling).
 * Prefer $api for all standard JSON requests.
 */
export async function getAuthHeaders(): Promise<Record<string, string>> {
  const {
    data: { session },
  } = await supabase.auth.getSession()

  if (!session?.access_token) throw new Error('No authentication token found')
  return { Authorization: `Bearer ${session.access_token}` }
}

export function getApiBaseUrl(): string {
  return (import.meta.env.VITE_SCOPEO_API_URL as string)?.replace(/\/$/, '') || ''
}

export const $api = ofetch.create({
  baseURL: import.meta.env.VITE_SCOPEO_API_URL,
  async onRequest({ options }) {
    if (!navigator.onLine) {
      throw new Error('You are offline. Please check your connection.')
    }

    const {
      data: { session },
    } = await supabase.auth.getSession()

    if (!session?.access_token) {
      throw new Error('No authentication token found')
    }

    // Don't set Content-Type for FormData - let browser set multipart/form-data with boundary
    const isFormData = options.body instanceof FormData

    options.headers = new Headers({
      ...options.headers,
      Authorization: `Bearer ${session.access_token}`,
      ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
      Accept: 'application/json',
    })
  },
  async onResponseError({ response, error }) {
    // Handle 401 - attempt token refresh then logout if it fails
    if (response?.status === 401) {
      const refreshSucceeded = await attemptTokenRefresh()

      if (!refreshSucceeded) {
        // Logout occurred, don't throw - page will redirect
        return
      }

      // Refresh succeeded - throw error so TanStack Query can retry with new token
      // The retry will get a fresh token from onRequest
    }

    // Build detailed error message
    let detailedMessage = 'An unexpected API error occurred.'

    if (response && response._data) {
      const responseData = response._data
      if (responseData && typeof responseData.detail === 'string') {
        detailedMessage = responseData.detail
      } else if (responseData) {
        detailedMessage = typeof responseData === 'string' ? responseData : JSON.stringify(responseData)
      }
    } else if (error && error.message && !error.message.startsWith('[')) {
      detailedMessage = error.message
    } else if (response) {
      detailedMessage = `API request failed with status ${response.status}: ${response.statusText || 'No status text'}`
    }

    const customError = new FetchError(detailedMessage) as any

    customError.data = response?._data || (error as any)?.data
    customError.status = response?.status || (error as any)?.status
    customError.statusText = response?.statusText || (error as any)?.statusText
    if (error) {
      customError.cause = error
    }

    throw customError
  },
})
