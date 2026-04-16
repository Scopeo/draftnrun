<script setup lang="ts">
import { signInWithGoogle } from '@/services/auth'

const loading = ref(false)

const handleGoogleSignIn = async () => {
  loading.value = true
  await signInWithGoogle()
}
</script>

<template>
  <div class="d-flex align-center justify-center">
    <VBtn
      variant="outlined"
      color="default"
      :loading="loading"
      prepend-icon="logos-google-icon"
      @click="handleGoogleSignIn"
    >
      Sign in with Google
    </VBtn>
  </div>
</template>
