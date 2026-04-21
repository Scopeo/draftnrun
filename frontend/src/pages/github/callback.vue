<script setup lang="ts">
definePage({
  meta: {
    layout: 'blank',
    public: true,
  },
})

const route = useRoute()

const installationId = computed(() => {
  const raw = route.query.installation_id
  if (raw == null) return undefined
  const value = Array.isArray(raw) ? raw[0] : raw
  return value ? Number(value) : undefined
})

const setupAction = computed(() => {
  const raw = route.query.setup_action
  return (Array.isArray(raw) ? raw[0] : raw) ?? 'install'
})

onMounted(() => {
  if (window.opener) {
    window.opener.postMessage(
      {
        type: 'github-app-installed',
        installation_id: installationId.value,
        setup_action: setupAction.value,
      },
      window.location.origin,
    )
    window.close()
  }
})
</script>

<template>
  <div class="callback-page d-flex align-center justify-center">
    <VCard class="pa-6 text-center" max-width="440" elevation="4" rounded="lg">
      <VCardText v-if="installationId">
        <VIcon icon="tabler-check" size="48" color="success" class="mb-4" />
        <h4 class="text-h5 mb-2">GitHub App Installed</h4>
        <p class="text-body-1 text-medium-emphasis">
          You can close this window and return to Draft'n&nbsp;Run.
        </p>
      </VCardText>

      <VCardText v-else>
        <VIcon icon="tabler-alert-circle" size="48" color="error" class="mb-4" />
        <h4 class="text-h5 mb-2 text-error">Missing Installation</h4>
        <p class="text-body-1">No installation_id was provided by GitHub.</p>
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
