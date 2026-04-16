<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useQAEvaluation } from '@/composables/useQAEvaluation'
import { useQAEvents } from '@/composables/useQAEvents'
import { useSelectedOrg } from '@/composables/useSelectedOrg'
import type { EvaluationType, LLMJudge, LLMJudgeCreate, LLMJudgeUpdate } from '@/types/qa'

interface Props {
  projectId: string
}

const props = defineProps<Props>()

const { selectedOrgRole } = useSelectedOrg()
const { emitJudgesUpdated } = useQAEvents()

const { judges, loadingStates, fetchLLMJudges, fetchLLMJudgeDefaults, createJudge, updateJudge, deleteJudges } =
  useQAEvaluation()

const showCreateDialog = ref(false)
const showDeleteAllDialog = ref(false)
const showDeleteSingleJudgeDialog = ref(false)
const judgeToDelete = ref<LLMJudge | null>(null)
const editingJudge = ref<LLMJudge | null>(null)
const judgeForm = ref()

const evaluationTypeOptions = [
  { title: 'Boolean', value: 'boolean' as EvaluationType },
  { title: 'Score', value: 'score' as EvaluationType },
  { title: 'Free Text', value: 'free_text' as EvaluationType },
  { title: 'JSON Equality', value: 'json_equality' as EvaluationType },
]

// Store templates in memory by evaluation type to preserve user edits
const templatesByType = ref<Record<EvaluationType, string>>({
  boolean: '',
  score: '',
  free_text: '',
  json_equality: '',
})

const judgeFormData = ref<LLMJudgeCreate>({
  name: '',
  description: null,
  evaluation_type: 'boolean',
  prompt_template: '',
})

const onEvaluationTypeChange = async () => {
  const newType = judgeFormData.value.evaluation_type

  // If we already have a template in memory for this type, use it
  if (templatesByType.value[newType]) {
    judgeFormData.value.prompt_template = templatesByType.value[newType]

    return
  }

  // Otherwise, fetch the default template for this evaluation type
  const defaultsData = await fetchLLMJudgeDefaults(newType)
  if (defaultsData?.prompt_template) {
    judgeFormData.value.prompt_template = defaultsData.prompt_template
    templatesByType.value[newType] = defaultsData.prompt_template
  }
}

const canDeleteJudges = computed(() => {
  const role = selectedOrgRole.value?.toLowerCase()
  return ['admin', 'developer'].includes(role)
})

const evaluationTypeHint = computed(() => {
  const type = judgeFormData.value.evaluation_type
  switch (type) {
    case 'boolean':
      return 'This will enforce the output format to be a boolean (true or false).'
    case 'score':
      return 'This will enforce the output format to be an integer.'
    case 'free_text':
      return 'There will be no enforced output format.'
    case 'json_equality':
      return 'This will compare the output with the groundtruth for exact JSON equality.'
    default:
      return ''
  }
})

const resetForm = async () => {
  // Reset templates in memory
  templatesByType.value = {
    boolean: '',
    score: '',
    free_text: '',
    json_equality: '',
  }

  // Force refresh defaults from backend when creating new judge
  const defaultsData = await fetchLLMJudgeDefaults('boolean')

  if (defaultsData) {
    judgeFormData.value = {
      name: '',
      description: null,
      evaluation_type: defaultsData.evaluation_type || 'boolean',
      prompt_template: defaultsData.prompt_template || '',
    }
    templatesByType.value[defaultsData.evaluation_type || 'boolean'] = defaultsData.prompt_template || ''
  } else {
    judgeFormData.value = {
      name: '',
      description: null,
      evaluation_type: 'boolean',
      prompt_template: '',
    }
  }

  editingJudge.value = null
}

const closeDialog = async () => {
  showCreateDialog.value = false
  await resetForm()
}

const openDialog = async () => {
  await resetForm()
  showCreateDialog.value = true
}

const openEditDialog = (judge: LLMJudge) => {
  editingJudge.value = judge

  // Reset templates in memory
  templatesByType.value = {
    boolean: '',
    score: '',
    free_text: '',
    json_equality: '',
  }

  judgeFormData.value = {
    name: judge.name,
    description: judge.description || null,
    evaluation_type: judge.evaluation_type,
    prompt_template: judge.prompt_template,
  }

  // Store the current template in memory
  templatesByType.value[judge.evaluation_type] = judge.prompt_template
  showCreateDialog.value = true
}

const saveJudge = async () => {
  if (!props.projectId) return

  // Store current template in memory before saving
  templatesByType.value[judgeFormData.value.evaluation_type] = judgeFormData.value.prompt_template

  const isValid = await judgeForm.value?.validate()
  if (!isValid?.valid) return

  if (editingJudge.value) {
    const updateData: LLMJudgeUpdate = {
      name: judgeFormData.value.name,
      description: judgeFormData.value.description,
      evaluation_type: judgeFormData.value.evaluation_type,
      prompt_template: judgeFormData.value.prompt_template,
    }

    const success = await updateJudge(props.projectId, editingJudge.value.id, updateData)
    if (success) {
      // Emit event to notify other components (e.g., QADatasetTable) to refresh judges
      emitJudgesUpdated({ projectId: props.projectId })
    }
  } else {
    const dataToSend: LLMJudgeCreate = {
      name: judgeFormData.value.name,
      description: judgeFormData.value.description,
      evaluation_type: judgeFormData.value.evaluation_type,
      prompt_template: judgeFormData.value.prompt_template,
    }

    const success = await createJudge(props.projectId, dataToSend)
    if (success) {
      // Emit event to notify other components (e.g., QADatasetTable) to refresh judges
      emitJudgesUpdated({ projectId: props.projectId })
    }
  }

  await closeDialog()
}

const openDeleteAllDialog = () => {
  if (judges.value.length === 0) return
  showDeleteAllDialog.value = true
}

const confirmDeleteAll = async () => {
  if (!props.projectId || judges.value.length === 0) return

  const allJudgeIds = judges.value.map(j => j.id)

  const success = await deleteJudges(props.projectId, allJudgeIds)
  if (success) {
    // Emit event to notify other components (e.g., QADatasetTable) to refresh judges
    emitJudgesUpdated({ projectId: props.projectId })
  }
  showDeleteAllDialog.value = false
}

const openDeleteSingleJudgeDialog = (judge: LLMJudge) => {
  judgeToDelete.value = judge
  showDeleteSingleJudgeDialog.value = true
}

const confirmDeleteSingleJudge = async () => {
  if (!props.projectId || !judgeToDelete.value) return

  const success = await deleteJudges(props.projectId, [judgeToDelete.value.id])
  if (success) {
    // Emit event to notify other components (e.g., QADatasetTable) to refresh judges
    emitJudgesUpdated({ projectId: props.projectId })
  }
  judgeToDelete.value = null
  showDeleteSingleJudgeDialog.value = false
}

onMounted(async () => {
  if (props.projectId) {
    await Promise.all([fetchLLMJudges(props.projectId), fetchLLMJudgeDefaults()])
  }
})

watch(
  () => props.projectId,
  newProjectId => {
    if (newProjectId) fetchLLMJudges(newProjectId)
  }
)

// Watch for prompt template changes and save to memory
watch(
  () => judgeFormData.value.prompt_template,
  newTemplate => {
    if (newTemplate && judgeFormData.value.evaluation_type)
      templatesByType.value[judgeFormData.value.evaluation_type] = newTemplate
  }
)
</script>

<template>
  <div class="llm-judges-container">
    <VCard class="mb-4">
      <VCardTitle class="d-flex align-center justify-space-between">
        <div class="d-flex align-center">
          <VIcon icon="tabler-gavel" size="24" class="me-2" />
          LLM Judges
        </div>

        <div class="d-flex align-center gap-2">
          <VBtn color="primary" variant="outlined" @click="openDialog">
            <VIcon icon="tabler-plus" class="me-2" />
            Create Judge
          </VBtn>

          <VBtn
            v-if="canDeleteJudges"
            color="error"
            variant="outlined"
            :disabled="judges.length === 0"
            @click="openDeleteAllDialog"
          >
            <VIcon icon="tabler-trash" class="me-2" />
            Delete All
          </VBtn>
        </div>
      </VCardTitle>

      <VCardText>
        <VList v-if="judges.length > 0">
          <VListItem v-for="judge in judges" :key="judge.id">
            <VListItemTitle class="font-weight-medium">
              {{ judge.name }}
            </VListItemTitle>

            <VListItemSubtitle>
              <div class="d-flex align-center gap-2 mt-1">
                <VChip size="x-small" variant="tonal">
                  {{ judge.evaluation_type }}
                </VChip>
                <span class="text-caption">{{ judge.llm_model_reference }}</span>
              </div>
              <span v-if="judge.description" class="text-caption text-medium-emphasis mt-1 d-block">
                {{ judge.description }}
              </span>
            </VListItemSubtitle>

            <template #append>
              <div class="d-flex gap-1">
                <VBtn icon size="small" variant="text" @click.stop="openEditDialog(judge)">
                  <VIcon icon="tabler-edit" />
                </VBtn>
                <VBtn
                  v-if="canDeleteJudges"
                  icon
                  size="small"
                  variant="text"
                  color="error"
                  @click.stop="openDeleteSingleJudgeDialog(judge)"
                >
                  <VIcon icon="tabler-trash" />
                </VBtn>
              </div>
            </template>
          </VListItem>
        </VList>

        <div v-else class="text-center pa-8">
          <VIcon icon="tabler-gavel-off" size="64" class="mb-4 text-disabled" />
          <h3 class="text-h6 mb-2">No LLM Judges</h3>
          <p class="text-body-2 mb-4">Create an LLM judge to evaluate your test cases</p>
          <VBtn color="primary" @click="openDialog">
            <VIcon icon="tabler-plus" class="me-2" />
            Create Judge
          </VBtn>
        </div>
      </VCardText>
    </VCard>

    <VDialog v-model="showCreateDialog" max-width="var(--dnr-dialog-lg)" scrollable>
      <VCard>
        <VCardTitle>{{ editingJudge ? 'Edit Judge' : 'Create Judge' }}</VCardTitle>
        <VDivider />
        <VCardText>
          <VForm ref="judgeForm">
            <VTextField
              v-model="judgeFormData.name"
              label="Name"
              variant="outlined"
              :rules="[v => !!v || 'Name is required']"
              class="mb-4"
            />

            <VTextarea
              v-model="judgeFormData.description"
              label="Description"
              variant="outlined"
              rows="2"
              class="mb-4"
            />

            <VSelect
              v-model="judgeFormData.evaluation_type"
              :items="evaluationTypeOptions"
              item-title="title"
              item-value="value"
              label="Evaluation Type"
              variant="outlined"
              :rules="[v => !!v || 'Evaluation type is required']"
              class="mb-2"
              @update:model-value="onEvaluationTypeChange"
            />

            <VAlert v-if="judgeFormData.evaluation_type" variant="tonal" density="compact" class="mb-4">
              <span class="text-body-2">{{ evaluationTypeHint }}</span>
            </VAlert>

            <VTextarea
              v-model="judgeFormData.prompt_template"
              label="Prompt Template"
              variant="outlined"
              rows="8"
              hint="You can use {{input}}, {{output}} and {{groundtruth}} as variables"
              persistent-hint
              :rules="[v => !!v || 'Prompt template is required']"
              class="mb-4"
            />
          </VForm>
        </VCardText>
        <VDivider />
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" @click="closeDialog"> Cancel </VBtn>
          <VBtn
            color="primary"
            :loading="loadingStates.creating || loadingStates.updating"
            :disabled="!judgeFormData.name || !judgeFormData.prompt_template || !judgeFormData.evaluation_type"
            @click="saveJudge"
          >
            {{ editingJudge ? 'Update' : 'Create' }}
          </VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <VDialog v-model="showDeleteAllDialog" max-width="var(--dnr-dialog-sm)">
      <VCard>
        <VCardTitle>Delete All LLM Judges</VCardTitle>
        <VCardText>
          <p>Are you sure you want to delete all {{ judges.length }} LLM judges? This action cannot be undone.</p>
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" @click="showDeleteAllDialog = false"> Cancel </VBtn>
          <VBtn color="error" :loading="loadingStates.deleting" @click="confirmDeleteAll"> Delete All </VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <VDialog v-model="showDeleteSingleJudgeDialog" max-width="var(--dnr-dialog-sm)">
      <VCard>
        <VCardTitle>Delete LLM Judge</VCardTitle>
        <VCardText>
          <p>Are you sure you want to delete "{{ judgeToDelete?.name }}"? This action cannot be undone.</p>
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" @click="showDeleteSingleJudgeDialog = false"> Cancel </VBtn>
          <VBtn color="error" :loading="loadingStates.deleting" @click="confirmDeleteSingleJudge"> Delete </VBtn>
        </VCardActions>
      </VCard>
    </VDialog>
  </div>
</template>

<style lang="scss" scoped>
.llm-judges-container {
  .bg-primary-lighten-5 {
    background-color: rgba(var(--v-theme-primary), 0.05);
  }
}
</style>
