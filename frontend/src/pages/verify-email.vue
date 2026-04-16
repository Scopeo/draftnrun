<script setup lang="ts">
import * as Sentry from '@sentry/vue'
import { logger } from '@/utils/logger'
import { useSelectedOrg } from '@/composables/useSelectedOrg'
import type { UserData } from '@/services/auth'
import { supabase } from '@/services/auth'
import { useAuthStore } from '@/stores/auth'
import DraftnrunLogo from '@/components/DraftnrunLogo.vue'

const route = useRoute()
const router = useRouter()
const ability = useAbility()
const { setSelectedOrg } = useSelectedOrg()

const status = ref('verifying') // 'verifying', 'success', 'error', 'already_verified'
const errorMessage = ref('')
const userData = ref<any>(null)
const organizationData = ref<any>(null)

const handleEmailVerification = async () => {
  try {
    logger.info('Starting email verification process...')
    logger.info('Current URL', { data: window.location.href })

    const hashParams = new URLSearchParams(window.location.hash.substring(1))
    const accessToken = hashParams.get('access_token')
    const refreshToken = hashParams.get('refresh_token')

    if (accessToken && refreshToken) {
      logger.info('Found verification tokens, processing...')

      const { data: setupData, error: setupError } = await supabase.functions.invoke('complete-user-setup', {
        body: {
          access_token: accessToken,
          refresh_token: refreshToken,
        },
      })

      logger.info('Setup response', { setupData, setupError })

      if (setupError) {
        throw setupError
      }

      if (setupData.alreadySetup) {
        status.value = 'already_verified'
      } else {
        if (setupData.session) {
          logger.info('Setting session from setup response...')

          const { data, error } = await supabase.auth.setSession({
            access_token: setupData.session.access_token,
            refresh_token: setupData.session.refresh_token,
          })

          if (error) {
            logger.error('Error setting session', { error })
            throw new Error(`Failed to set session: ${error.message}`)
          } else {
            logger.info('Session set successfully', data.session?.user?.email)
            await new Promise(resolve => setTimeout(resolve, 1000))

            const { data: verifyData, error: verifyError } = await supabase.auth.getSession()
            if (verifyError || !verifyData.session) {
              logger.error('Session verification failed', { error: verifyError })
              throw new Error('Session was not properly established')
            }
            logger.info('Session verified successfully')
          }
        }

        const mappedUserData: UserData = {
          id: setupData.user.id,
          fullName: setupData.user.username,
          username: setupData.user.username,
          email: setupData.user.email,
          avatar: undefined,
          role: 'client',
          super_admin: false,
        }

        const userAbilityRules = [
          { action: 'read', subject: 'all' },
          { action: ['create', 'read', 'update', 'delete'], subject: 'Project' },
          { action: ['read', 'update'], subject: 'Organization' },
        ]

        const authStore = useAuthStore()

        authStore.setAuth(mappedUserData, setupData.session?.access_token, userAbilityRules as any)
        ability.update(userAbilityRules as any)

        setSelectedOrg(setupData.organization.id, 'admin')

        userData.value = setupData.user
        organizationData.value = setupData.organization
        status.value = 'success'
      }
    } else {
      // PKCE flow: Supabase auto-exchanges ?code= for a session
      logger.info('No hash tokens found (PKCE flow), waiting for session...')

      Sentry.addBreadcrumb({ category: 'auth', message: 'verify-email: PKCE flow, waiting for session' })

      // Give Supabase time to exchange the code for a session
      await new Promise(resolve => setTimeout(resolve, 2000))

      const {
        data: { session },
        error: sessionError,
      } = await supabase.auth.getSession()

      if (sessionError) {
        throw sessionError
      }

      if (!session?.user) {
        throw new Error('No verification data found. Please check your email for the verification link.')
      }

      logger.info('Session found via PKCE', { data: session.user.email })

      Sentry.addBreadcrumb({ category: 'auth', message: `verify-email: session found for ${session.user.email}` })

      // Call complete-user-setup with the PKCE session tokens
      const { data: setupData, error: setupError } = await supabase.functions.invoke('complete-user-setup', {
        body: {
          access_token: session.access_token,
          refresh_token: session.refresh_token,
        },
      })

      logger.info('Setup response (PKCE)', { setupData, setupError })

      if (setupError) {
        Sentry.captureException(setupError, { tags: { flow: 'verify-email-pkce' } })
        throw setupError
      }

      if (setupData.alreadySetup) {
        status.value = 'already_verified'
      } else {
        const mappedUserData: UserData = {
          id: setupData.user.id,
          fullName: setupData.user.username,
          username: setupData.user.username,
          email: setupData.user.email,
          avatar: undefined,
          role: 'client',
          super_admin: false,
        }

        const userAbilityRules = [
          { action: 'read', subject: 'all' },
          { action: ['create', 'read', 'update', 'delete'], subject: 'Project' },
          { action: ['read', 'update'], subject: 'Organization' },
        ]

        const authStore = useAuthStore()

        authStore.setAuth(mappedUserData, session.access_token, userAbilityRules as any)
        ability.update(userAbilityRules as any)

        setSelectedOrg(setupData.organization.id, 'admin')

        userData.value = setupData.user
        organizationData.value = setupData.organization
        status.value = 'success'

        Sentry.addBreadcrumb({ category: 'auth', message: `verify-email: org created ${setupData.organization.id}` })
      }
    }
  } catch (error: unknown) {
    logger.error('Email verification error', { error })
    status.value = 'error'
    errorMessage.value = error instanceof Error ? error.message : 'Failed to verify email'
  }
}

const redirectToApp = async () => {
  await new Promise(resolve => setTimeout(resolve, 500))

  const authStore = useAuthStore()

  logger.info('Pre-redirect auth check', {
    hasUserData: !!authStore.userData,
    hasAccessToken: !!authStore.accessToken,
    userEmail: authStore.userData?.email,
    status: status.value,
  })

  router.push('/')
}

const goToLogin = () => {
  router.push('/login')
}

onMounted(() => {
  handleEmailVerification()
})

definePage({
  meta: {
    layout: 'blank',
    public: true,
  },
})
</script>

<template>
  <div class="auth-wrapper d-flex align-center justify-center pa-4">
    <div class="position-relative my-sm-16">
      <VCard class="auth-card" max-width="500" :class="$vuetify.display.smAndUp ? 'pa-6' : 'pa-2'">
        <VCardItem class="justify-center">
          <VCardTitle>
            <RouterLink to="/">
              <div class="app-logo d-flex align-center gap-x-3">
                <DraftnrunLogo style="block-size: 2rem; inline-size: 2rem" />
                <h1 class="app-logo-title text-h5">Draft'n Run</h1>
              </div>
            </RouterLink>
          </VCardTitle>
        </VCardItem>

        <VCardText>
          <div v-if="status === 'verifying'" class="text-center">
            <VProgressCircular indeterminate color="primary" size="64" class="mb-4" />
            <h4 class="text-h4 mb-2">Verifying your email ✉️</h4>
            <p class="text-body-1 mb-0">Please wait while we verify your email address...</p>
          </div>

          <div v-else-if="status === 'success'" class="text-center">
            <VIcon icon="tabler-check-circle" size="64" color="success" class="mb-4" />
            <h4 class="text-h4 mb-2">Welcome to Draft'n Run! 🎉</h4>
            <p class="text-body-1 mb-4">Your email has been verified successfully!</p>

            <VAlert type="success" variant="tonal" class="mb-4 text-start">
              <VIcon icon="tabler-building" class="me-2" />
              We've created your personal organization: <strong>{{ organizationData?.name }}</strong>
            </VAlert>

            <VBtn block color="primary" size="large" @click="redirectToApp"> Get Started </VBtn>
          </div>

          <div v-else-if="status === 'already_verified'" class="text-center">
            <VIcon icon="tabler-check-circle" size="64" color="info" class="mb-4" />
            <h4 class="text-h4 mb-2">Already Verified ✅</h4>
            <p class="text-body-1 mb-4">Your email is already verified. You can continue using the app.</p>

            <VBtn block color="primary" size="large" @click="redirectToApp"> Continue to App </VBtn>
          </div>

          <div v-else-if="status === 'error'" class="text-center">
            <VIcon icon="tabler-alert-circle" size="64" color="error" class="mb-4" />
            <h4 class="text-h4 mb-2">Verification Failed ❌</h4>
            <p class="text-body-1 mb-4">
              {{ errorMessage }}
            </p>

            <VBtn block variant="outlined" size="large" class="mb-2" @click="goToLogin"> Go to Login </VBtn>

            <div class="d-flex align-center justify-center mt-4">
              <span class="me-1">Need help? </span>
              <a href="mailto:support@draftnrun.com">Contact Support</a>
            </div>
          </div>
        </VCardText>
      </VCard>
    </div>
  </div>
</template>

<style lang="scss">
@use '@styles/auth';
</style>
