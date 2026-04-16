<script setup lang="ts">
import { VForm } from 'vuetify/components/VForm'
import { logger } from '@/utils/logger'
import { useInviteFlow } from '@/composables/useInviteFlow'
import { loginWithSupabase } from '@/services/auth'
import { useAuthStore } from '@/stores/auth'
import { useOrgStore } from '@/stores/org'
import { SESSION_EXPIRED_KEY } from '@/utils/api'
import AuthProvider from '@/components/AuthProvider.vue'
import DraftnrunLogo from '@/components/DraftnrunLogo.vue'

definePage({
  meta: {
    layout: 'blank',
    unauthenticatedOnly: true,
  },
})

const isPasswordVisible = ref(false)

const route = useRoute()
const router = useRouter()
const ability = useAbility()

const { isInviteFlow, inviteToken, redirectTo, showSocialAuth } = useInviteFlow()

const { trackSignIn, trackSessionStart } = useTracking()

const errors = ref<Record<string, string | undefined>>({
  email: undefined,
  password: undefined,
})

const sessionExpired = ref(false)

onMounted(() => {
  if (sessionStorage.getItem(SESSION_EXPIRED_KEY)) {
    sessionExpired.value = true
    sessionStorage.removeItem(SESSION_EXPIRED_KEY)
  }
})

const refVForm = ref<VForm>()

const credentials = ref({
  email: '',
  password: '',
})

const rememberMe = ref(false)

const login = async () => {
  try {
    const res = await loginWithSupabase(credentials.value.email, credentials.value.password)

    const { accessToken, userData, userAbilityRules } = res

    const authStore = useAuthStore()

    authStore.setAuth(userData, accessToken, userAbilityRules as any)

    ability.update(userAbilityRules as any)

    trackSignIn('email', userData.id, {
      email: userData.email,
      username: userData.username,
      is_invite_flow: isInviteFlow.value,
      redirect_url: redirectTo.value || route.query.to || '/',
    })

    const orgStore = useOrgStore()

    trackSessionStart(userData.id, {
      user_email: userData.email,
      user_role: orgStore.selectedOrgRole || 'user',
      org_count: orgStore.organizations.length,
      is_super_admin: userData.super_admin || false,
    })

    await nextTick(() => {
      let targetUrl = '/'

      if (redirectTo.value) {
        targetUrl = redirectTo.value
      } else if (route.query.to) {
        targetUrl = String(route.query.to)
      }

      if (targetUrl.startsWith('http')) {
        try {
          const url = new URL(targetUrl)

          targetUrl = url.pathname + url.search
        } catch (e) {
          targetUrl = '/'
        }
      }

      router.replace(targetUrl)
    })
  } catch (err: unknown) {
    errors.value = {
      email: err instanceof Error ? err.message : 'Login failed',
    }
    logger.error(err)
  }
}

const onSubmit = () => {
  refVForm.value?.validate().then(({ valid: isValid }) => {
    if (isValid) login()
  })
}
</script>

<template>
  <VRow no-gutters class="auth-wrapper bg-surface">
    <VCol md="6" class="d-none d-md-flex">
      <div
        class="position-relative bg-background w-100 d-flex flex-column align-center justify-center"
        style="gap: var(--dnr-space-5)"
      >
        <DraftnrunLogo style="width: 120px; height: 120px" />
        <h2 class="text-h4 text-medium-emphasis">Welcome back</h2>
      </div>
    </VCol>

    <VCol cols="12" md="6" class="auth-card-v2 d-flex align-center justify-center">
      <VCard flat :max-width="560" class="mt-0 pa-4">
        <VCardText>
          <h4 class="text-h4 mb-1">Sign in to Draft'n Run</h4>
          <p class="mb-0">Build and deploy AI agents and workflows</p>

          <VAlert v-if="isInviteFlow" type="info" variant="tonal" class="mt-4">
            <VIcon icon="tabler-mail" class="me-2" />
            You're signing in to accept an organization invitation
          </VAlert>

          <VAlert
            v-if="sessionExpired"
            type="warning"
            variant="tonal"
            class="mt-4"
            closable
            @click:close="sessionExpired = false"
          >
            Your session has expired. Please sign in again.
          </VAlert>
        </VCardText>
        <VCardText>
          <VForm ref="refVForm" @submit.prevent="onSubmit">
            <VRow>
              <VCol cols="12">
                <VTextField
                  v-model="credentials.email"
                  label="Email"
                  placeholder="johndoe@email.com"
                  type="email"
                  autofocus
                  :rules="[requiredValidator, emailValidator]"
                  :error-messages="errors.email"
                />
              </VCol>

              <VCol cols="12">
                <VTextField
                  v-model="credentials.password"
                  label="Password"
                  placeholder="············"
                  :rules="[requiredValidator]"
                  :type="isPasswordVisible ? 'text' : 'password'"
                  autocomplete="password"
                  :error-messages="errors.password"
                  :append-inner-icon="isPasswordVisible ? 'tabler-eye-off' : 'tabler-eye'"
                  @click:append-inner="isPasswordVisible = !isPasswordVisible"
                />

                <div class="d-flex align-center flex-wrap justify-space-between my-6">
                  <VCheckbox v-model="rememberMe" label="Remember me" />
                  <RouterLink class="text-primary ms-2 mb-1" :to="{ name: 'forgot-password' }">
                    Forgot Password?
                  </RouterLink>
                </div>

                <VBtn block type="submit"> Login </VBtn>
              </VCol>

              <VCol cols="12" class="text-center text-base">
                <span class="d-inline-block">New on our platform?</span>
                <RouterLink
                  class="text-primary ms-1 d-inline-block"
                  :to="
                    isInviteFlow
                      ? `/register?invite_token=${inviteToken}&redirect_to=${encodeURIComponent(redirectTo)}`
                      : { name: 'register' }
                  "
                >
                  Create an account
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
