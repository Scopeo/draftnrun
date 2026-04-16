<script setup lang="ts">
import { useRouter } from 'vue-router'
import { logger } from '@/utils/logger'
import { supabase } from '@/services/auth'
import DraftnrunLogo from '@/components/DraftnrunLogo.vue'

const router = useRouter()

const form = ref({
  newPassword: '',
  confirmPassword: '',
})

const isPasswordVisible = ref(false)
const isConfirmPasswordVisible = ref(false)
const loading = ref(false)
const successMessage = ref<string | null>(null)
const errorMessage = ref<string | null>(null)
const checkingRecoverySession = ref(true)
const hasRecoverySession = ref(false)

const resolveRecoverySession = async () => {
  try {
    const hashParams = new URLSearchParams(window.location.hash.slice(1))
    const accessToken = hashParams.get('access_token')
    const refreshToken = hashParams.get('refresh_token')
    const flowType = hashParams.get('type')

    if (accessToken && refreshToken && flowType === 'recovery') {
      const { error } = await supabase.auth.setSession({
        access_token: accessToken,
        refresh_token: refreshToken,
      })

      if (error) throw error

      // Remove tokens from URL after session is established
      window.history.replaceState({}, document.title, window.location.pathname)
    }

    const {
      data: { session },
      error,
    } = await supabase.auth.getSession()

    if (error) throw error

    hasRecoverySession.value = !!session
    if (!session) {
      errorMessage.value = 'Invalid or expired reset link. Please request a new password reset email.'
    }
  } catch (err: unknown) {
    logger.error('Failed to resolve recovery session', { error: err })
    errorMessage.value =
      err instanceof Error ? err.message : 'Invalid or expired reset link. Please request a new password reset email.'
    hasRecoverySession.value = false
  } finally {
    checkingRecoverySession.value = false
  }
}

const resetPassword = async () => {
  if (!hasRecoverySession.value) {
    errorMessage.value = 'Invalid or expired reset link. Please request a new password reset email.'
    return
  }

  if (!form.value.newPassword) {
    errorMessage.value = 'Please enter a new password'
    return
  }

  if (form.value.newPassword.length < 6) {
    errorMessage.value = 'Password must be at least 6 characters'
    return
  }

  if (form.value.newPassword !== form.value.confirmPassword) {
    errorMessage.value = 'Passwords do not match'
    return
  }

  try {
    loading.value = true
    errorMessage.value = null
    successMessage.value = null

    const { error: updateError } = await supabase.auth.updateUser({
      password: form.value.newPassword,
    })

    if (updateError) throw updateError

    successMessage.value = 'Your password has been reset successfully'

    form.value.newPassword = ''
    form.value.confirmPassword = ''

    setTimeout(() => {
      router.push({ name: 'login' })
    }, 3000)
  } catch (err: unknown) {
    logger.error('Error resetting password', { error: err })
    errorMessage.value = err instanceof Error ? err.message : 'Failed to reset password'
  } finally {
    loading.value = false
  }
}

definePage({
  meta: {
    layout: 'blank',
    public: true,
  },
})

onMounted(() => {
  resolveRecoverySession()
})
</script>

<template>
  <RouterLink to="/">
    <div class="auth-logo d-flex align-center gap-x-3">
      <DraftnrunLogo style="block-size: 2rem; inline-size: 2rem" />
      <h1 class="auth-title">Draft'n Run</h1>
    </div>
  </RouterLink>

  <VRow class="auth-wrapper bg-surface" no-gutters>
    <VCol md="8" class="d-none d-md-flex">
      <div class="position-relative bg-background w-100 d-flex align-center justify-center">
        <h2 class="text-h4 text-medium-emphasis">Set a new password</h2>
      </div>
    </VCol>

    <VCol cols="12" md="4" class="d-flex align-center justify-center">
      <VCard flat :max-width="500" class="mt-12 mt-sm-0 pa-4">
        <VCardText>
          <h4 class="text-h4 mb-1">Reset Password 🔒</h4>
          <p class="mb-0">Set a new password for your account</p>
        </VCardText>

        <VCardText>
          <VAlert v-if="checkingRecoverySession" type="info" variant="tonal" class="mb-4">
            Validating reset link...
          </VAlert>
          <VAlert
            v-if="successMessage"
            type="success"
            variant="tonal"
            closable
            class="mb-4"
            @click:close="successMessage = null"
          >
            {{ successMessage }}
          </VAlert>
          <VAlert
            v-if="errorMessage"
            type="error"
            variant="tonal"
            closable
            class="mb-4"
            @click:close="errorMessage = null"
          >
            {{ errorMessage }}
          </VAlert>

          <VForm @submit.prevent="resetPassword">
            <VRow>
              <VCol cols="12">
                <VTextField
                  v-model="form.newPassword"
                  label="New Password"
                  placeholder="············"
                  :type="isPasswordVisible ? 'text' : 'password'"
                  autocomplete="new-password"
                  :append-inner-icon="isPasswordVisible ? 'tabler-eye-off' : 'tabler-eye'"
                  :disabled="loading"
                  @click:append-inner="isPasswordVisible = !isPasswordVisible"
                />
              </VCol>

              <VCol cols="12">
                <VTextField
                  v-model="form.confirmPassword"
                  label="Confirm Password"
                  autocomplete="new-password"
                  placeholder="············"
                  :type="isConfirmPasswordVisible ? 'text' : 'password'"
                  :append-inner-icon="isConfirmPasswordVisible ? 'tabler-eye-off' : 'tabler-eye'"
                  :disabled="loading"
                  @click:append-inner="isConfirmPasswordVisible = !isConfirmPasswordVisible"
                />
              </VCol>

              <VCol cols="12">
                <VBtn
                  block
                  type="submit"
                  :loading="loading"
                  :disabled="
                    loading ||
                    checkingRecoverySession ||
                    !hasRecoverySession ||
                    !form.newPassword ||
                    !form.confirmPassword
                  "
                >
                  Reset Password
                </VBtn>
              </VCol>

              <VCol cols="12">
                <RouterLink class="d-flex align-center justify-center" :to="{ name: 'login' }">
                  <VIcon icon="tabler-chevron-left" size="20" class="me-1 flip-in-rtl" />
                  <span>Back to login</span>
                </RouterLink>
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
