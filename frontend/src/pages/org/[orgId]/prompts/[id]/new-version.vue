<script setup lang="ts">
import { computed, ref } from 'vue'
import { watchOnce } from '@vueuse/core'
import { useRoute, useRouter } from 'vue-router'
import {
  usePromptDetailQuery,
  usePromptVersionDetailQuery,
  useCreateVersionMutation,
} from '@/composables/queries/usePromptsQuery'
import PromptForm from '@/components/prompts/PromptForm.vue'
import { logger } from '@/utils/logger'
import { useNotifications } from '@/composables/useNotifications'

const route = useRoute()
const router = useRouter()
const { notify } = useNotifications()
const orgId = computed(() => route.params.orgId as string)
const promptId = computed(() => route.params.id as string)

const { data: promptDetail, isPending: promptPending } = usePromptDetailQuery(orgId, promptId)
const createVersionMutation = useCreateVersionMutation(orgId, promptId)

const latestVersionId = computed(() => {
  const versions = promptDetail.value?.versions
  if (!versions?.length) return undefined
  return [...versions].sort((a, b) => b.version_number - a.version_number)[0].id
})

const {
  data: latestVersionDetail,
  isPending: versionPending,
  isError: versionError,
} = usePromptVersionDetailQuery(orgId, promptId, latestVersionId)

const bootstrapComplete = computed(() => !promptPending.value && !versionPending.value && !versionError.value)

const name = ref('')
const content = ref('')
const formError = ref<string | null>(null)

function defaultCommitMessage() {
  const now = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  const ts = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}`
  const versions = promptDetail.value?.versions
  const next = versions?.length ? Math.max(...versions.map(v => v.version_number)) + 1 : 2
  return `${ts} — v${next}`
}

const commitMessage = ref(defaultCommitMessage())

const backTo = computed(() => ({
  name: 'org-org-id-prompts-id',
  params: { orgId: orgId.value, id: promptId.value },
}))

const promptName = computed(() => {
  const full = promptDetail.value?.latest_version?.name || 'Prompt'
  const parts = full.split('/')
  return parts[parts.length - 1]
})

watchOnce(
  () => latestVersionDetail.value,
  detail => {
    if (!detail) return
    name.value = detail.name
    content.value = detail.content
    commitMessage.value = defaultCommitMessage()
  }
)

async function submit() {
  formError.value = null
  try {
    await createVersionMutation.mutateAsync({
      name: name.value.trim(),
      content: content.value,
      change_description: commitMessage.value.trim() || undefined,
    })
    router.push(backTo.value)
  } catch (err: unknown) {
    logger.error(err, { action: 'createVersion', name: name.value })
    const message = (err as Error).message || 'Failed to create version'
    notify.error(message)
    formError.value = message
  }
}

definePage({
  meta: { action: 'read', subject: 'Organization' },
})
</script>

<template>
  <AppPage>
    <LoadingState v-if="promptPending || versionPending" message="Loading prompt version..." />

    <ErrorState
      v-else-if="versionError"
      title="Failed to load version"
      message="Could not load the latest version details. Please go back and try again."
    />

    <PromptForm
      v-else-if="bootstrapComplete"
      v-model:name="name"
      v-model:content="content"
      name-readonly
      v-model:commit-message="commitMessage"
      :title="`${promptName} — New version`"
      subtitle="Prompts are immutable. To update a prompt, create a new version."
      :back-to="backTo"
      submit-label="Create Version"
      :is-submitting="createVersionMutation.isPending.value"
      :form-error="formError"
      @submit="submit"
    />
  </AppPage>
</template>
