import { createClient } from '@supabase/supabase-js'
import * as Sentry from '@sentry/vue'
import defineAbilityFor from '../plugins/casl/ability'
import { clearSuperAdminCache } from '@/plugins/1.router/guards'
import { useAuthStore } from '@/stores/auth'
import { useOrgStore } from '@/stores/org'
import { logger } from '@/utils/logger'

export const supabase = createClient(import.meta.env.VITE_SUPABASE_URL, import.meta.env.VITE_SUPABASE_ANON_KEY, {
  auth: {
    autoRefreshToken: true,
    persistSession: true,
    detectSessionInUrl: true,
    flowType: 'pkce',
  },
})
// Add this interface near the top of the file
export interface UserData {
  id: string
  fullName: string
  username: string
  email: string | undefined
  avatar?: string | null
  role?: string
  super_admin?: boolean
}

// Promise to signal completion of the initial auth state check
let resolveInitialAuthCheck: (isLoggedIn: boolean) => void

const initialAuthCheckPromise = new Promise<boolean>(resolve => {
  resolveInitialAuthCheck = resolve
})

let initialAuthEventReceived = false

// Add a logout flag to prevent session recovery during logout
let isLoggingOut = false
function clearAllAuthAndOrgState() {
  try {
    const authStore = useAuthStore()

    authStore.clearAuth()
  } catch (authErr) {
    logger.warn('Failed to clear auth store', { error: authErr })
  }

  try {
    const orgStore = useOrgStore()

    orgStore.clearOrg()
  } catch (error) {
    logger.warn('Failed to clear org store', { error })
    if (typeof window !== 'undefined') {
      localStorage.removeItem('selectedOrgId')
      localStorage.removeItem('selectedOrgRole')
    }
  }
}

// Derive project ref from the anon key JWT (works even with custom domain URLs)
function getSupabaseProjectRef(): string {
  try {
    const jwt = import.meta.env.VITE_SUPABASE_ANON_KEY
    if (jwt) {
      const payload = JSON.parse(atob(jwt.split('.')[1]))
      if (payload.ref) return payload.ref
    }
  } catch {
    // fall through
  }
  const fallback = import.meta.env.VITE_SUPABASE_PROJECT_REF
  if (!fallback) logger.warn('auth.ts: Could not derive Supabase project ref — localStorage session key will be wrong')
  return fallback || 'unknown'
}

// Resolve quickly from localStorage; Supabase's onAuthStateChange may fire later
setTimeout(() => {
  if (!initialAuthEventReceived) {
    logger.info('auth.ts: No auth event received after timeout, resolving from localStorage.')

    let isLoggedIn = false
    try {
      const storageKey = `sb-${getSupabaseProjectRef()}-auth-token`
      const authData = localStorage.getItem(storageKey)
      if (authData) {
        isLoggedIn = !!JSON.parse(authData)?.access_token
      }
    } catch (e) {
      logger.error('auth.ts: Error checking localStorage', { error: e })
    }

    initialAuthEventReceived = true
    resolveInitialAuthCheck(isLoggedIn)
  }
}, 500)

// Global auth state check
export const checkAuthState = async () => {
  const {
    data: { session },
    error,
  } = await supabase.auth.getSession()

  if (error || !session) {
    await logout()
    return false
  }

  return true
}

// Add a listener for auth state changes
supabase.auth.onAuthStateChange(async (event, session) => {
  logger.info('Auth state change', { event, hasSession: !!session, userId: session?.user?.id })

  // Handle initial auth events
  if (!initialAuthEventReceived && (event === 'SIGNED_IN' || event === 'SIGNED_OUT' || event === 'INITIAL_SESSION')) {
    initialAuthEventReceived = true
    resolveInitialAuthCheck(!!session)
  }

  Sentry.addBreadcrumb({ category: 'auth', message: `onAuthStateChange: ${event}`, data: { hasSession: !!session } })

  // Handle sign out - keep it simple
  if (event === 'SIGNED_OUT') {
    logger.info('User signed out, clearing auth state')
    isLoggingOut = true

    // Track session end before clearing data
    if (typeof window !== 'undefined' && session?.user?.id && window.trackSessionEnd) {
      const sessionStartTime = sessionStorage.getItem('session_start_time')
      let sessionDuration: number | undefined
      if (sessionStartTime) {
        sessionDuration = Date.now() - Number.parseInt(sessionStartTime)
      }
      window.trackSessionEnd(session.user.id, sessionDuration)
    }

    clearAllAuthAndOrgState()

    setTimeout(() => {
      isLoggingOut = false
    }, 1000)
  }

  // Handle successful sign in - set up default org from database
  if (event === 'SIGNED_IN' && session?.user) {
    try {
      logger.info('User signed in, fetching organizations from database')

      const orgStore = useOrgStore()

      if (!orgStore.selectedOrgId) {
        await orgStore.fetchOrganizations(session.user.id)
        logger.info('[Auth] Fresh login - fetched orgs from database', { data: orgStore.selectedOrgId })
      } else {
        logger.info('[Auth] Org already selected, preserving user choice', { data: orgStore.selectedOrgId })
      }
    } catch (error) {
      logger.error('[Auth] Failed to fetch organizations on sign in', { error })
    }
  }

  // Handle token refresh
  if (event === 'TOKEN_REFRESHED') {
    if (session) {
      logger.info('Token refreshed successfully')

      const authStore = useAuthStore()

      authStore.updateAccessToken(session.access_token)
    } else {
      logger.info('Token refresh failed')
    }
  }
})

// Add this function to handle API errors
export const handleApiError = async (error: any) => {
  if (error?.status === 400 || error?.status === 401) {
    try {
      // Try to refresh the session first
      const {
        data: { session },
        error: refreshError,
      } = await supabase.auth.refreshSession()

      if (!refreshError && session) {
        // Session refreshed successfully, update the access token
        const authStore = useAuthStore()

        authStore.updateAccessToken(session.access_token)
        logger.info('Token refreshed successfully after API error')
        return true
      }
    } catch (refreshErr) {
      logger.warn('Token refresh failed', { error: refreshErr })
    }

    // If refresh failed, check current session
    const {
      data: { session: currentSession },
    } = await supabase.auth.getSession()

    if (!currentSession) {
      // No valid session, log the user out
      logger.info('No valid session, logging out user')
      await logout()
      return false
    }
    return true
  }
  return true
}

// Export the promise to allow components to wait for initialization
export const ensureAuthInitialized = () => initialAuthCheckPromise

export async function loginWithSupabase(email: string, password: string) {
  try {
    const { data, error } = await supabase.auth.signInWithPassword({
      email,
      password,
    })

    if (error) throw error
    if (!data.session || !data.user) throw new Error('Authentication failed')

    // Clear explicit logout flag on successful login
    clearExplicitLogout()

    const userData = {
      id: data.user.id,
      fullName: data.user.user_metadata.full_name || data.user.email?.split('@')[0],
      username: data.user.user_metadata.username || data.user.email?.split('@')[0],
      email: data.user.email,
      avatar:
        data.user.user_metadata.avatar_url || data.user.user_metadata.picture || data.user.user_metadata.photo || null,
      super_admin: data.user.user_metadata.super_admin || false,
    }

    // Create ability rules based on user data
    const ability = defineAbilityFor(userData)

    return {
      accessToken: data.session.access_token,
      userData,
      userAbilityRules: ability.rules,
    }
  } catch (err) {
    logger.error('Login process failed', { error: err })
    throw err
  }
}

export async function registerWithSupabase(userData: { email: string; password: string; username: string }) {
  const { data, error } = await supabase.auth.signUp({
    email: userData.email,
    password: userData.password,
    options: {
      data: {
        username: userData.username,
        full_name: userData.username, // Using username as full_name initially
        super_admin: false,
      },
    },
  })

  if (error) throw error

  if (!data.user) throw new Error('Registration failed: no user returned')

  // Map Supabase user to your existing user structure
  const mappedUserData = {
    id: data.user.id,
    fullName: data.user.user_metadata.full_name || data.user.email?.split('@')[0],
    username: data.user.user_metadata.username,
    email: data.user.email,
    avatar:
      data.user.user_metadata.avatar_url || data.user.user_metadata.picture || data.user.user_metadata.photo || null,
    super_admin: data.user.user_metadata.super_admin || false,
  }

  const ability = defineAbilityFor(mappedUserData)

  return {
    accessToken: data.session?.access_token,
    userData: mappedUserData,
    userAbilityRules: ability.rules,
  }
}

// Add this function to handle the token from URL
export async function handleEmailVerification() {
  const {
    data: { session },
    error,
  } = await supabase.auth.getSession()

  if (error) throw error

  if (!session) return null

  // Map Supabase user to your existing user structure
  const userData = {
    id: session.user.id,
    fullName: session.user.user_metadata.full_name || session.user.email?.split('@')[0],
    username: session.user.user_metadata.username || session.user.email?.split('@')[0],
    email: session.user.email,
    avatar:
      session.user.user_metadata.avatar_url ||
      session.user.user_metadata.picture ||
      session.user.user_metadata.photo ||
      null,
    super_admin: session.user.user_metadata.super_admin || false,
  }

  const ability = defineAbilityFor(userData)

  return {
    accessToken: session.access_token,
    userData,
    userAbilityRules: ability.rules,
  }
}

// Add a function specifically for handling password resets
export async function resetPasswordWithToken(newPassword: string, token: string) {
  try {
    if (!token) {
      throw new Error('Password reset token is required')
    }

    // First verify the token
    const { error: verifyError } = await supabase.auth.verifyOtp({
      token_hash: token,
      type: 'recovery',
    })

    if (verifyError) throw verifyError

    // Then update the user's password
    const { error } = await supabase.auth.updateUser({
      password: newPassword,
    })

    if (error) throw error
    return true
  } catch (error) {
    logger.error('Password reset error', { error })
    throw error
  }
}

// Update session validation to also check claims
export async function validateSession() {
  const {
    data: { session },
    error,
  } = await supabase.auth.getSession()

  if (error || !session) {
    const authStore = useAuthStore()

    authStore.clearAuth()
    return false
  }

  // Update user data with latest claims
  const claims = session.user?.app_metadata
  const authStore = useAuthStore()
  if (authStore.userData) {
    authStore.updateUserData({
      ...authStore.userData,
      role: claims?.role || 'user',
    })
  }

  return true
}

// Export isLoggingOut for router guards to check
export const getIsLoggingOut = () => isLoggingOut

// Check if user has explicitly logged out
export const hasExplicitlyLoggedOut = () => {
  if (typeof window === 'undefined') return false
  return localStorage.getItem('explicitLogout') === 'true'
}

// Clear explicit logout flag (call when user logs in)
export const clearExplicitLogout = () => {
  if (typeof window !== 'undefined') {
    localStorage.removeItem('explicitLogout')
  }
}

// Update the existing logout function
export async function logout() {
  isLoggingOut = true
  clearSuperAdminCache()
  clearAllAuthAndOrgState()

  // Set a flag to prevent auto-recovery after logout
  if (typeof window !== 'undefined') {
    localStorage.setItem('explicitLogout', 'true')

    // Also clear Supabase localStorage to prevent session recovery
    const supabaseStorageKey = `sb-${getSupabaseProjectRef()}-auth-token`

    localStorage.removeItem(supabaseStorageKey)
  }

  try {
    // Try to sign out, but don't block if it fails
    await Promise.race([
      supabase.auth.signOut(),
      new Promise((_resolve, reject) => setTimeout(() => reject(new Error('Timeout')), 3000)),
    ])
  } catch (error) {
    logger.warn('Logout API call failed, but continuing with local cleanup', { error })
  }

  // Reset logout flag after a delay
  setTimeout(() => {
    isLoggingOut = false
  }, 1000)

  // Always redirect regardless of API success/failure
  if (window.location.pathname !== '/login') {
    window.location.href = '/login'
  }
}

// Google authentication function
export async function signInWithGoogle() {
  try {
    const { data, error } = await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: {
        redirectTo: `${window.location.origin}/auth/callback`,
        queryParams: {
          access_type: 'offline',
          prompt: 'consent',
        },
        scopes: 'email profile',
      },
    })

    if (error) throw error
    return data
  } catch (err) {
    logger.error('Google sign-in failed', { error: err })
    throw err
  }
}

// Helper function to call complete-user-setup for new Google users
export async function completeUserSetup(user: any, session: any) {
  try {
    const { data, error } = await supabase.functions.invoke('complete-user-setup', {
      body: {
        access_token: session.access_token,
        refresh_token: session.refresh_token,
        user_id: user.id,
      },
    })

    if (error) throw error
    return data
  } catch (err) {
    logger.error('Failed to complete user setup', { error: err })
    throw err
  }
}

// Handle Google auth callback and organization setup
export async function handleGoogleAuthCallback() {
  try {
    const {
      data: { session },
      error,
    } = await supabase.auth.getSession()

    if (error) throw error
    if (!session?.user) throw new Error('No session found')

    // Clear explicit logout flag on successful Google auth
    clearExplicitLogout()

    const user = session.user

    logger.info('Google auth callback for user', { data: user.email })

    // Check if this is a new user (created_at is recent)
    const userCreatedAt = new Date(user.created_at || '')
    const now = new Date()
    const isNewUser = now.getTime() - userCreatedAt.getTime() < 5 * 60 * 1000 // 5 minutes

    if (isNewUser) {
      logger.info('New Google user detected, setting up organization...')

      try {
        const setupResult = await Promise.race([
          completeUserSetup(user, session),
          new Promise<never>((_, reject) =>
            setTimeout(() => reject(new Error('User setup timed out')), 10_000)
          ),
        ])

        if (setupResult.success) {
          logger.info('Organization created for Google user', { data: setupResult.organization })

          if (typeof window !== 'undefined') {
            localStorage.setItem('selectedOrgId', setupResult.organization.id)
            localStorage.setItem('selectedOrgRole', 'admin')
          }
        }
      } catch (setupErr) {
        // Non-fatal: user is authenticated, org setup can be retried later
        logger.warn('User setup failed or timed out, continuing login', { error: setupErr })
        Sentry.captureMessage('complete-user-setup failed or timed out', {
          level: 'warning',
          tags: { context: 'complete-user-setup', userId: user.id },
          extra: { email: user.email, error: setupErr instanceof Error ? setupErr.message : String(setupErr) },
        })
      }
    }

    // Create user data object
    const userData = {
      id: user.id,
      fullName: user.user_metadata.full_name || user.user_metadata.name || user.email?.split('@')[0],
      username: user.user_metadata.preferred_username || user.user_metadata.name || user.email?.split('@')[0],
      email: user.email,
      avatar: user.user_metadata.avatar_url || user.user_metadata.picture || user.user_metadata.photo || null,
      super_admin: user.user_metadata.super_admin || false,
    }

    // Create ability rules
    const ability = defineAbilityFor(userData)

    return {
      accessToken: session.access_token,
      userData,
      userAbilityRules: ability.rules,
      isNewUser,
    }
  } catch (err) {
    logger.error('Google auth callback failed', { error: err })
    throw err
  }
}
