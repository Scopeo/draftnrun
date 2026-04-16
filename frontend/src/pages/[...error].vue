<script setup lang="ts">
definePage({
  alias: '/pages/misc/not-found/:error(.*)',
  meta: {
    layout: 'blank',
    public: true,
  },
})
</script>

<template>
  <div class="d-flex flex-column align-center justify-center text-center" style="min-block-size: 100vh; padding: 2rem">
    <VIcon icon="tabler-alert-triangle" size="80" color="warning" class="mb-6" />

    <ErrorHeader
      status-code="404"
      title="Page Not Found"
      description="We couldn't find the page you are looking for."
    />

    <VBtn to="/"> Back to Home </VBtn>
  </div>
</template>
