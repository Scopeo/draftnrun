<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import PromptDetail from '@/components/prompts/PromptDetail.vue'

const route = useRoute()
const orgId = computed(() => route.params.orgId as string)
const promptId = computed(() => route.params.id as string)

definePage({
  meta: {
    action: 'read',
    subject: 'Organization',
  },
})
</script>

<template>
  <AppPage>
    <PromptDetail v-if="orgId && promptId" :org-id="orgId" :prompt-id="promptId" />
  </AppPage>
</template>
