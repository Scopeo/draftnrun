<script setup lang="ts">
import { logger } from '@/utils/logger'
import { handleGoogleAuthCallback } from '@/services/auth'
import { useAuthStore } from '@/stores/auth'
import { useOrgStore } from '@/stores/org'

definePage({
  meta: {
    layout: 'blank',
    public: true,
  },
})

const router = useRouter()
const ability = useAbility()

// Use the tracking composable
const { trackSignIn, trackSignUp, trackSessionStart } = useTracking()

const loading = ref(true)
const error = ref<string | null>(null)

// Handle the authentication callback
onMounted(async () => {
  try {
    const route = useRoute()
    const urlParams = new URLSearchParams(window.location.search)

    // Check if this is a Gmail integration callback
    if (urlParams.get('state') === 'gmail_integration') {
      const code = urlParams.get('code')
      const error = urlParams.get('error')

      if (window.opener) {
        if (error) {
          window.opener.postMessage(
            {
              type: 'gmail_auth_error',
              error,
            },
            window.location.origin
          )
        } else if (code) {
          window.opener.postMessage(
            {
              type: 'gmail_auth_success',
              code,
            },
            window.location.origin
          )
        } else {
          window.opener.postMessage(
            {
              type: 'gmail_auth_error',
              error: 'No authorization code received',
            },
            window.location.origin
          )
        }
        window.close()
        return
      }
    }

    // Normal authentication flow — hard timeout so any hang (PKCE exchange, edge function, etc.)
    // doesn't leave the user stuck on the spinner indefinitely
    const result = await Promise.race([
      handleGoogleAuthCallback(),
      new Promise<never>((_, reject) =>
        setTimeout(() => reject(new Error('Authentication timed out — please try again')), 20_000)
      ),
    ])

    if (result) {
      const { accessToken, userData, userAbilityRules, isNewUser } = result

      const authStore = useAuthStore()

      authStore.setAuth(userData, accessToken, userAbilityRules as any)
      ability.update(userAbilityRules as any)

      logger.info('Google authentication successful', { isNewUser })

      // Track authentication event
      if (isNewUser) {
        // Track sign up for new Google user
        trackSignUp('google', userData.id, {
          email: userData.email,
          username: userData.username,
          full_name: userData.fullName,
          avatar: userData.avatar,
          is_new_user: true,
        })
      }

      // Track sign in (always happens for Google auth)
      trackSignIn('google', userData.id, {
        email: userData.email,
        username: userData.username,
        full_name: userData.fullName,
        avatar: userData.avatar,
        is_new_user: isNewUser,
      })

      // Track session start
      const orgStore = useOrgStore()

      trackSessionStart(userData.id, {
        user_email: userData.email,
        user_role: orgStore.selectedOrgRole || 'user',
        org_count: orgStore.organizations.length,
        is_super_admin: userData.super_admin || false,
        auth_method: 'google',
        is_new_user: isNewUser,
      })

      await router.replace('/')
    } else {
      throw new Error('Authentication failed')
    }
  } catch (err: unknown) {
    logger.error('Auth callback error', { error: err })
    error.value = err instanceof Error ? err.message : 'Authentication failed'

    // Redirect to login after a delay
    setTimeout(() => {
      router.replace('/login')
    }, 3000)
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="auth-wrapper d-flex align-center justify-center pa-4">
    <VCard class="auth-card pa-6 text-center" max-width="400">
      <VCardText>
        <div v-if="loading">
          <VProgressCircular indeterminate color="primary" size="64" class="mb-4" />
          <h4 class="text-h5 mb-2">Completing Sign In...</h4>
          <p class="text-body-1 mb-0">Please wait while we set up your account</p>
        </div>

        <div v-else-if="error">
          <VIcon icon="tabler-alert-circle" size="64" color="error" class="mb-4" />
          <h4 class="text-h5 mb-2 text-error">Authentication Failed</h4>
          <p class="text-body-1 mb-4">
            {{ error }}
          </p>
          <p class="text-body-2">Redirecting to login page...</p>
        </div>

        <div v-else>
          <VIcon icon="tabler-check-circle" size="64" color="success" class="mb-4" />
          <h4 class="text-h5 mb-2 text-success">Sign In Successful!</h4>
          <p class="text-body-1">Redirecting to dashboard...</p>
        </div>
      </VCardText>
    </VCard>
  </div>
</template>

<style scoped>
.auth-wrapper {
  background-color: rgb(var(--v-theme-surface));
  min-block-size: 100vh;
}

.auth-card {
  box-shadow: rgb(var(--v-theme-on-surface), 0.1) 0 2px 10px 0 !important;
}
</style>
