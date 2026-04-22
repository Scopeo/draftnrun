<script setup lang="ts">
import GitSyncSection from '@/components/connections/GitSyncSection.vue'
import OAuthIntegrationsSection from '@/components/connections/OAuthIntegrationsSection.vue'

definePage({
  meta: {
    action: 'read',
    subject: 'Project',
  },
})
</script>

<template>
  <AppPage>
    <AppPageHeader
      title="Integrations"
      description="Connect your organization to external services. Each connection creates an OAuth variable definition that can be used in workflows."
    >
      <template #badge>
        <VChip size="small" color="warning" variant="tonal">Beta</VChip>
      </template>
    </AppPageHeader>

    <GitSyncSection />
    <OAuthIntegrationsSection />
  </AppPage>
</template>
