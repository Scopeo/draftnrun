<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import * as Sentry from '@sentry/vue'
import { logger } from '@/utils/logger'
import { useAuthStore } from '@/stores/auth'
import { useOrgStore } from '@/stores/org'
import { logout } from '@/services/auth'

const router = useRouter()
const authStore = useAuthStore()
const orgStore = useOrgStore()
const noOrg = ref(false)

const WAIT_FOR_ORG_LOAD_MS = 5000

async function waitForOrgStoreToSettle() {
  if (!orgStore.isLoading || orgStore.selectedOrgId) return

  await new Promise<void>(resolve => {
    const stop = watch(
      () => orgStore.isLoading,
      loading => {
        if (!loading) {
          stop()
          resolve()
        }
      },
      { immediate: true }
    )

    setTimeout(() => {
      stop()
      resolve()
    }, WAIT_FOR_ORG_LOAD_MS)
  })
}

onMounted(async () => {
  logger.info('[Index] Mounted', {
    selectedOrgId: orgStore.selectedOrgId,
    isLoading: orgStore.isLoading,
    orgCount: orgStore.organizations.length,
  })

  await waitForOrgStoreToSettle()

  // Final fallback for races between the SIGNED_IN fetch and post-signup org creation.
  if (!orgStore.selectedOrgId && authStore.isAuthenticated && authStore.userData?.id) {
    await orgStore.fetchOrganizations(authStore.userData.id, true)
  }

  if (orgStore.selectedOrgId) {
    router.replace(`/org/${orgStore.selectedOrgId}/projects`)
    return
  }

  logger.warn('[Index] No org found after loading', { orgCount: orgStore.organizations.length })
  Sentry.addBreadcrumb({ category: 'auth', message: 'index: no org found, showing setup incomplete' })
  noOrg.value = true
})

const handleLogout = async () => {
  await logout()
}

definePage({
  meta: {
    layout: 'blank',
    public: false,
  },
})
</script>

<template>
  <div v-if="noOrg" class="d-flex align-center justify-center" style="min-height: 100vh">
    <VCard max-width="400" class="pa-6 text-center">
      <VIcon icon="tabler-alert-circle" size="48" color="warning" class="mb-4" />
      <h3 class="text-h5 mb-2">Account setup incomplete</h3>
      <p class="text-body-1 text-medium-emphasis mb-6">
        Your organization could not be created. Please contact support or try again later.
      </p>
      <VBtn block color="primary" variant="outlined" @click="handleLogout"> Logout </VBtn>
    </VCard>
  </div>
  <div v-else />
</template>
