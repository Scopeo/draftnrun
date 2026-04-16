<script setup lang="ts">
import { supabase } from '@/services/auth'

definePage({
  meta: {
    layout: 'blank',
    public: true,
  },
})

const route = useRoute()
const router = useRouter()

const loading = ref(true)
const processing = ref(false)
const error = ref<string | null>(null)
const authDetails = ref<any>(null)

const authorizationId = computed(() => {
  const raw = route.query.authorization_id
  if (raw == null) return undefined
  const value = (Array.isArray(raw) ? raw[0] : raw)?.trim()

  return value || undefined
})

function redirectTo(url: string) {
  window.location.replace(url)
}

onMounted(async () => {
  if (!authorizationId.value) {
    error.value = 'Missing authorization_id parameter.'
    loading.value = false
    return
  }

  try {
    const {
      data: { user },
    } = await supabase.auth.getUser()

    if (!user) {
      const currentPath = `/oauth/callback?authorization_id=${authorizationId.value}`

      router.replace(`/login?to=${encodeURIComponent(currentPath)}`)

      return
    }

    const { data, error: detailsError } = await supabase.auth.oauth.getAuthorizationDetails(authorizationId.value)

    if (detailsError || !data) {
      error.value = detailsError?.message || 'Invalid authorization request.'
      return
    }

    if ('redirect_url' in data && data.redirect_url) {
      redirectTo(data.redirect_url)
      return
    }

    authDetails.value = data
  } catch (err: unknown) {
    error.value = err instanceof Error ? err.message : 'Unexpected error loading authorization details.'
  } finally {
    loading.value = false
  }
})

async function handleDecision(decision: 'approve' | 'deny') {
  if (!authorizationId.value) return
  processing.value = true

  try {
    const { data, error: oauthError } =
      decision === 'approve'
        ? await supabase.auth.oauth.approveAuthorization(authorizationId.value)
        : await supabase.auth.oauth.denyAuthorization(authorizationId.value)

    if (oauthError || !data?.redirect_url) {
      error.value = oauthError?.message || `${decision} failed.`
      return
    }

    redirectTo(data.redirect_url)
  } catch (err: unknown) {
    error.value = err instanceof Error ? err.message : `Unexpected error during ${decision}.`
  } finally {
    processing.value = false
  }
}
</script>

<template>
  <div class="callback-page d-flex align-center justify-center">
    <VCard class="pa-6 text-center" max-width="440" elevation="4" rounded="lg">
      <VCardText v-if="loading">
        <VProgressCircular indeterminate color="primary" size="48" class="mb-4" />
        <p class="text-body-1 mb-0">Loading authorization request...</p>
      </VCardText>

      <VCardText v-else-if="error">
        <VIcon icon="tabler-alert-circle" size="48" color="error" class="mb-4" />
        <h4 class="text-h5 mb-2 text-error">Authorization Error</h4>
        <p class="text-body-1">{{ error }}</p>
      </VCardText>

      <VCardText v-else-if="authDetails">
        <h4 class="text-h5 mb-4">Authorize Access</h4>
        <p class="text-body-1 mb-2">
          <strong>{{ authDetails.client?.name || 'An MCP client' }}</strong>
          wants to access your Draft'n&nbsp;Run account.
        </p>

        <p class="text-body-2 text-medium-emphasis mb-4">
          This will grant full access to your organizations, projects, graphs, runs, and all other Draft'n&nbsp;Run
          resources through the MCP protocol.
        </p>

        <p v-if="authDetails.redirect_uri" class="text-caption text-medium-emphasis mb-4">
          Will redirect to: {{ authDetails.redirect_uri }}
        </p>

        <div class="d-flex gap-3">
          <VBtn
            variant="outlined"
            color="secondary"
            class="flex-grow-1"
            :disabled="processing"
            @click="handleDecision('deny')"
          >
            Deny
          </VBtn>
          <VBtn color="primary" class="flex-grow-1" :loading="processing" @click="handleDecision('approve')">
            Approve
          </VBtn>
        </div>
      </VCardText>
    </VCard>
  </div>
</template>

<style scoped lang="scss">
.callback-page {
  min-height: 100vh;
  background: rgb(var(--v-theme-surface));
}
</style>
