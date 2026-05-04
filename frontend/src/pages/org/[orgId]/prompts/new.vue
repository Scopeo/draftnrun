<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import PromptForm from '@/components/prompts/PromptForm.vue'
import { useCreatePromptMutation } from '@/composables/queries/usePromptsQuery'
import { useNotifications } from '@/composables/useNotifications'
import { logger } from '@/utils/logger'

const route = useRoute()
const router = useRouter()
const orgId = computed(() => route.params.orgId as string)
const createMutation = useCreatePromptMutation(orgId)
const { notify } = useNotifications()

const name = ref('')
const content = ref('')
const commitMessage = ref('')
const formError = ref<string | null>(null)

const backTo = computed(() => ({ name: 'org-org-id-prompts', params: { orgId: orgId.value } }))

async function submit() {
  formError.value = null
  try {
    const prompt = await createMutation.mutateAsync({
      name: name.value.trim(),
      content: content.value,
      change_description: commitMessage.value.trim() || undefined,
    })
    router.push({ name: 'org-org-id-prompts-id', params: { orgId: orgId.value, id: prompt.id } })
  } catch (err: unknown) {
    logger.error('createPrompt failed', { error: err })
    const msg =
      err instanceof Error
        ? err.message
        : typeof err === 'string'
          ? err
          : typeof err === 'object' && err !== null && 'message' in err && typeof (err as { message: unknown }).message === 'string'
            ? (err as { message: string }).message
            : String(err)
    formError.value = msg || 'Failed to create prompt'
    notify.error(`Failed to create prompt: ${msg || 'Unknown error'}`)
  }
}

definePage({
  meta: { action: 'read', subject: 'Organization' },
})
</script>

<template>
  <AppPage>
    <PromptForm
      v-model:name="name"
      v-model:content="content"
      v-model:commit-message="commitMessage"
      title="New Prompt"
      subtitle="Create a new prompt for your organization's library."
      :back-to="backTo"
      submit-label="Create Prompt"
      :is-submitting="createMutation.isPending.value"
      :form-error="formError"
      @submit="submit"
    />
  </AppPage>
</template>
