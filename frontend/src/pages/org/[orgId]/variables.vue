<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import OrgVariableDefinitions from '@/components/variables/OrgVariableDefinitions.vue'

const route = useRoute()
const orgId = computed(() => route.params.orgId as string)

definePage({
  meta: {
    action: 'read',
    subject: 'Organization',
  },
})
</script>

<template>
  <AppPage>
    <AppPageHeader
      title="Variables"
      description="Manage variable definitions and secret values for your organization."
    />

    <VCard>
      <VCardText>
        <OrgVariableDefinitions v-if="orgId" :org-id="orgId" />
      </VCardText>
    </VCard>
  </AppPage>
</template>
