<script setup lang="ts">
import { logger } from '@/utils/logger'
import { supabase } from '@/services/auth'
import DraftnrunLogo from '@/components/DraftnrunLogo.vue'

const email = ref('')
const loading = ref(false)
const successMessage = ref<string | null>(null)
const errorMessage = ref<string | null>(null)

const sendResetLink = async () => {
  if (!email.value) {
    errorMessage.value = 'Please enter your email address'
    return
  }

  try {
    loading.value = true
    errorMessage.value = null
    successMessage.value = null

    const { error } = await supabase.auth.resetPasswordForEmail(email.value, {
      redirectTo: `${window.location.origin}/reset-password`,
    })

    if (error) throw error

    successMessage.value = 'A password reset link has been sent to your email'
  } catch (err: unknown) {
    logger.error('Error sending reset link', { error: err })
    errorMessage.value = err instanceof Error ? err.message : 'Failed to send reset link'
  } finally {
    loading.value = false
  }
}

definePage({
  meta: {
    layout: 'blank',
    unauthenticatedOnly: true,
  },
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
        <h2 class="text-h4 text-medium-emphasis">Reset your password</h2>
      </div>
    </VCol>

    <VCol cols="12" md="4" class="d-flex align-center justify-center">
      <VCard flat :max-width="500" class="mt-12 mt-sm-0 pa-4">
        <VCardText>
          <h4 class="text-h4 mb-1">Forgot Password? 🔒</h4>
          <p class="mb-0">Enter your email and we'll send you a reset link</p>
        </VCardText>

        <VCardText>
          <VAlert
            v-if="successMessage"
            type="success"
            variant="tonal"
            closable
            class="mb-4"
            @click:close="successMessage = null"
          >
            {{ successMessage }}
            <div class="mt-2">
              <small>Open the link in your email to set a new password.</small>
            </div>
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

          <VForm @submit.prevent="sendResetLink">
            <VRow>
              <VCol cols="12">
                <VTextField
                  v-model="email"
                  autofocus
                  label="Email"
                  type="email"
                  placeholder="johndoe@email.com"
                  :disabled="loading"
                  required
                />
              </VCol>

              <VCol cols="12">
                <VBtn block type="submit" :loading="loading" :disabled="loading || !email"> Send Reset Link </VBtn>
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
