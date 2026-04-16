<script setup lang="ts">
import { VForm } from 'vuetify/components/VForm'
import { logger } from '@/utils/logger'

import { useInviteFlow } from '@/composables/useInviteFlow'
import { supabase } from '@/services/auth'
import { useAuthStore } from '@/stores/auth'
import AuthProvider from '@/components/AuthProvider.vue'
import DraftnrunLogo from '@/components/DraftnrunLogo.vue'

definePage({
  meta: {
    layout: 'blank',
    unauthenticatedOnly: true,
  },
})

const form = ref({
  username: '',
  email: '',
  password: '',
  privacyPolicies: false,
})

const isPasswordVisible = ref(false)
const loading = ref(false)

const router = useRouter()
const route = useRoute()
const ability = useAbility()

const { isInviteFlow, inviteToken, redirectTo, showSocialAuth } = useInviteFlow()
const isInvitedUser = computed(() => isInviteFlow.value)
const { notify } = useNotifications()

const { trackSignUp, trackSignIn, trackSessionStart } = useTracking()

const errors = ref<Record<string, string | undefined>>({
  email: undefined,
  password: undefined,
  username: undefined,
})

const refVForm = ref<VForm>()

const register = async () => {
  if (!form.value.privacyPolicies) {
    errors.value = {
      email: 'You must accept the privacy policy & terms',
    }
    return
  }

  loading.value = true

  try {
    if (isInvitedUser.value) {
      const { data: functionData, error: functionError } = await supabase.functions.invoke('register-with-invite', {
        body: {
          email: form.value.email,
          password: form.value.password,
          username: form.value.username,
          inviteToken: inviteToken.value,
        },
      })

      if (functionError) throw functionError

      if (functionData.session) {
        await supabase.auth.setSession({
          access_token: functionData.session.access_token,
          refresh_token: functionData.session.refresh_token,
        })

        const userData = {
          id: functionData.user.id,
          fullName: functionData.user.username,
          username: functionData.user.username,
          email: functionData.user.email,
          avatar: null,
          role: 'client',
        }

        const userAbilityRules = [{ action: 'manage', subject: 'all' }]

        const authStore = useAuthStore()

        authStore.setAuth(userData, functionData.session.access_token, userAbilityRules as any)
        ability.update(userAbilityRules as any)

        trackSignUp('email_invite', userData.id, {
          email: userData.email,
          username: userData.username,
          invite_token: inviteToken.value,
          redirect_url: redirectTo.value || '/',
        })

        trackSignIn('email_invite', userData.id, {
          email: userData.email,
          username: userData.username,
          invite_token: inviteToken.value,
          redirect_url: redirectTo.value || '/',
        })

        trackSessionStart(userData.id, {
          user_email: userData.email,
          user_role: userData.role,
          is_invited_user: true,
          invite_token: inviteToken.value,
        })
      }
    } else {
      const { data: functionData, error: functionError } = await supabase.functions.invoke('register-regular-user', {
        body: {
          email: form.value.email,
          password: form.value.password,
          username: form.value.username,
          appUrl: window.location.origin,
        },
      })

      if (functionError) {
        throw functionError
      }

      notify.success(`Account created successfully. Check your email (${form.value.email}) to verify your account.`)

      trackSignUp('email', undefined, {
        email: form.value.email,
        username: form.value.username,
        requires_verification: true,
        app_url: window.location.origin,
      })
    }

    let targetUrl = '/login'

    if (isInvitedUser.value && redirectTo.value) {
      targetUrl = `${redirectTo.value}&registered=true`
    } else if (redirectTo.value) {
      targetUrl = redirectTo.value
    }

    if (targetUrl.startsWith('http')) {
      try {
        const url = new URL(targetUrl)

        targetUrl = url.pathname + url.search
      } catch (e) {
        targetUrl = '/login'
      }
    }

    await router.push(targetUrl)
  } catch (err: unknown) {
    logger.error(err)
    errors.value = {
      email: err instanceof Error ? err.message : 'Registration failed',
    }
  } finally {
    loading.value = false
  }
}

const onSubmit = () => {
  refVForm.value?.validate().then(({ valid: isValid }) => {
    if (isValid) register()
  })
}
</script>

<template>
  <RouterLink to="/">
    <div class="auth-logo d-flex align-center gap-x-3">
      <DraftnrunLogo style="block-size: 2rem; inline-size: 2rem" />
      <h1 class="auth-title">Draft'n Run</h1>
    </div>
  </RouterLink>

  <VRow no-gutters class="auth-wrapper bg-surface">
    <VCol md="8" class="d-none d-md-flex">
      <div class="position-relative bg-background w-100 d-flex align-center justify-center">
        <h2 class="text-h4 text-medium-emphasis">Create your account</h2>
      </div>
    </VCol>

    <VCol cols="12" md="4" class="auth-card-v2 d-flex align-center justify-center bg-surface">
      <VCard flat :max-width="500" class="mt-12 mt-sm-0 pa-4">
        <VCardText>
          <h4 class="text-h4 mb-1">Welcome to Draft'n Run! 👋🏻</h4>

          <VAlert v-if="isInvitedUser" type="info" variant="tonal" class="mt-4">
            <VIcon icon="tabler-mail" class="me-2" />
            You have been invited to join an organization. Please create an account using your invited email address.
          </VAlert>
        </VCardText>

        <VCardText>
          <VForm ref="refVForm" @submit.prevent="onSubmit">
            <VRow>
              <VCol cols="12">
                <VTextField
                  v-model="form.username"
                  :rules="[requiredValidator]"
                  autofocus
                  label="Username"
                  placeholder="Johndoe"
                  :disabled="loading"
                />
              </VCol>

              <VCol cols="12">
                <VTextField
                  v-model="form.email"
                  :rules="[requiredValidator, emailValidator]"
                  :error-messages="errors.email"
                  label="Email"
                  type="email"
                  placeholder="johndoe@email.com"
                  :disabled="loading"
                  :hint="isInvitedUser ? 'Please use the email address from your invitation.' : undefined"
                  persistent-hint
                />
              </VCol>

              <VCol cols="12">
                <VTextField
                  v-model="form.password"
                  :rules="[requiredValidator]"
                  label="Password"
                  placeholder="············"
                  :type="isPasswordVisible ? 'text' : 'password'"
                  autocomplete="password"
                  :append-inner-icon="isPasswordVisible ? 'tabler-eye-off' : 'tabler-eye'"
                  :disabled="loading"
                  @click:append-inner="isPasswordVisible = !isPasswordVisible"
                />

                <div class="d-flex align-center my-4">
                  <VCheckbox id="privacy-policy" v-model="form.privacyPolicies" inline :disabled="loading" />
                  <VLabel for="privacy-policy" style="opacity: 1">
                    <span class="me-1 text-high-emphasis">I agree to the</span>
                    <a
                      href="https://draftnrun.com/privacy-policy/"
                      target="_blank"
                      rel="noopener noreferrer"
                      class="text-primary"
                    >
                      privacy policy
                    </a>
                    <span class="mx-1 text-high-emphasis">and</span>
                    <a
                      href="https://draftnrun.com/terms-conditions/"
                      target="_blank"
                      rel="noopener noreferrer"
                      class="text-primary"
                    >
                      terms & conditions
                    </a>
                  </VLabel>
                </div>

                <VBtn block type="submit" class="mt-6" :disabled="!form.privacyPolicies || loading" :loading="loading">
                  {{ isInvitedUser ? 'Create Account & Join Organization' : 'Sign up' }}
                </VBtn>
              </VCol>

              <VCol cols="12" class="text-center text-base">
                <span class="d-inline-block">Already have an account?</span>
                <RouterLink
                  class="text-primary ms-1 d-inline-block"
                  :to="
                    isInviteFlow
                      ? `/login?invite_token=${inviteToken}&redirect_to=${encodeURIComponent(redirectTo)}`
                      : { name: 'login' }
                  "
                >
                  Sign in instead
                </RouterLink>
              </VCol>

              <VCol v-if="showSocialAuth" cols="12" class="d-flex align-center">
                <VDivider />
                <span class="mx-4">or</span>
                <VDivider />
              </VCol>

              <VCol v-if="showSocialAuth" cols="12" class="text-center">
                <AuthProvider />
              </VCol>
            </VRow>
          </VForm>
        </VCardText>
      </VCard>
    </VCol>
  </VRow>
</template>

<style lang="scss">
@use '@styles/auth';
</style>
