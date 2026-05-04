<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import PromptLibraryList from '@/components/prompts/PromptLibraryList.vue'

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
      title="Prompt Library"
      description="Manage and version your organization's reusable prompts."
    />
    <PromptLibraryList v-if="orgId" :org-id="orgId" />
  </AppPage>
</template>
