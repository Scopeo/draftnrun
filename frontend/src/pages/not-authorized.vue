<script setup lang="ts">
definePage({
  alias: '/pages/misc/not-authorized',
  meta: {
    layout: 'blank',
    public: true,
  },
})
</script>

<template>
  <div class="d-flex flex-column align-center justify-center text-center" style="min-block-size: 100vh; padding: 2rem">
    <VIcon icon="tabler-lock" size="80" color="error" class="mb-6" />

    <ErrorHeader
      status-code="401"
      title="Not authorized"
      description="You don't have permission to access this page."
    />

    <VBtn to="/"> Back to Home </VBtn>
  </div>
</template>
