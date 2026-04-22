<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useProjectAssociation } from '@/composables/useProjectAssociation'
import { useQAEvaluation } from '@/composables/useQAEvaluation'
import { useQAEvents } from '@/composables/useQAEvents'
import { useSelectedOrg } from '@/composables/useSelectedOrg'
import type { EvaluationType, LLMJudge, LLMJudgeCreate, LLMJudgeUpdate } from '@/types/qa'

interface Props {
  projectId: string
}

const props = defineProps<Props>()

const { selectedOrgId, selectedOrgRole } = useSelectedOrg()
const { emitJudgesUpdated } = useQAEvents()

const {
  judges: allOrgJudges,
  loadingStates,
  fetchLLMJudges,
  fetchLLMJudgeDefaults,
  createJudge,
  updateJudge,
  setJudgeProjects,
} = useQAEvaluation()

const orgId = computed(() => selectedOrgId.value || '')
const projectIdRef = computed(() => props.projectId)

const judgeAssoc = useProjectAssociation({
  projectId: projectIdRef,
  allItems: allOrgJudges,
})

const judges = computed(() => judgeAssoc.linkedItems(allOrgJudges.value))
const unlinkedJudges = computed(() => judgeAssoc.unlinkedItems(allOrgJudges.value))

const showCreateDialog = ref(false)
const showRemoveJudgeDialog = ref(false)
const judgeToRemove = ref<LLMJudge | null>(null)
const editingJudge = ref<LLMJudge | null>(null)
const judgeForm = ref()

const evaluationTypeOptions = [
  { title: 'Boolean', value: 'boolean' as EvaluationType },
  { title: 'Score', value: 'score' as EvaluationType },
  { title: 'Free Text', value: 'free_text' as EvaluationType },
  { title: 'JSON Equality', value: 'json_equality' as EvaluationType },
]

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

  if (templatesByType.value[newType]) {
    judgeFormData.value.prompt_template = templatesByType.value[newType]
    return
  }

  const defaultsData = await fetchLLMJudgeDefaults(newType)
  if (defaultsData?.prompt_template) {
    judgeFormData.value.prompt_template = defaultsData.prompt_template
    templatesByType.value[newType] = defaultsData.prompt_template
  }
}

const canManageJudges = computed(() => {
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
  templatesByType.value = {
    boolean: '',
    score: '',
    free_text: '',
    json_equality: '',
  }

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

  templatesByType.value[judge.evaluation_type] = judge.prompt_template
  showCreateDialog.value = true
}

const saveJudge = async () => {
  if (!orgId.value) return

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

    const success = await updateJudge(orgId.value, editingJudge.value.id, updateData)
    if (success) emitJudgesUpdated({ projectId: props.projectId })
  } else {
    const dataToSend: LLMJudgeCreate = {
      name: judgeFormData.value.name,
      description: judgeFormData.value.description,
      evaluation_type: judgeFormData.value.evaluation_type,
      prompt_template: judgeFormData.value.prompt_template,
    }

    const createdJudge = await createJudge(orgId.value, dataToSend)
    if (createdJudge) {
      if (props.projectId) {
        const existingIds = createdJudge.project_ids || []
        if (!existingIds.includes(props.projectId)) {
          await setJudgeProjects(orgId.value, createdJudge.id, [...existingIds, props.projectId])
        }
      }
      emitJudgesUpdated({ projectId: props.projectId })
    }
  }

  await closeDialog()
}

const addExistingJudge = async (judgeId: string) => {
  if (!orgId.value) return
  const projectIds = judgeAssoc.buildAddProjectIds(judgeId)
  if (!projectIds) return
  await setJudgeProjects(orgId.value, judgeId, projectIds)
  emitJudgesUpdated({ projectId: props.projectId })
}

const openRemoveJudgeDialog = (judge: LLMJudge) => {
  judgeToRemove.value = judge
  showRemoveJudgeDialog.value = true
}

const confirmRemoveJudge = async () => {
  if (!orgId.value || !judgeToRemove.value) return
  const projectIds = judgeAssoc.buildRemoveProjectIds(judgeToRemove.value.id)
  if (!projectIds) return
  await setJudgeProjects(orgId.value, judgeToRemove.value.id, projectIds)
  emitJudgesUpdated({ projectId: props.projectId })
  judgeToRemove.value = null
  showRemoveJudgeDialog.value = false
}

onMounted(async () => {
  if (orgId.value) {
    await Promise.all([fetchLLMJudges(orgId.value), fetchLLMJudgeDefaults()])
  }
})

watch(
  () => orgId.value,
  newOrgId => {
    if (newOrgId) fetchLLMJudges(newOrgId)
  }
)

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
          <!-- Add Judge (split button) -->
          <VMenu location="bottom end" :close-on-content-click="true">
            <template #activator="{ props: menuProps }">
              <VBtn color="primary" variant="outlined" v-bind="menuProps">
                <VIcon icon="tabler-plus" class="me-2" />
                Add Judge
              </VBtn>
            </template>

            <VList density="compact" min-width="220">
              <VListSubheader v-if="unlinkedJudges.length > 0">Existing judges</VListSubheader>
              <VListItem
                v-for="judge in unlinkedJudges"
                :key="judge.id"
                @click="addExistingJudge(judge.id)"
              >
                <template #prepend>
                  <VIcon icon="tabler-gavel" size="18" />
                </template>
                <VListItemTitle>{{ judge.name }}</VListItemTitle>
                <VListItemSubtitle>
                  <VChip size="x-small" variant="tonal">{{ judge.evaluation_type }}</VChip>
                </VListItemSubtitle>
              </VListItem>

              <VListItem v-if="unlinkedJudges.length === 0" disabled>
                <VListItemTitle class="text-medium-emphasis text-body-2">
                  No other judges in this organization
                </VListItemTitle>
              </VListItem>

              <VDivider class="my-1" />

              <VListItem @click="openDialog">
                <template #prepend>
                  <VIcon icon="tabler-file-plus" size="18" />
                </template>
                <VListItemTitle>Create New Judge</VListItemTitle>
              </VListItem>
            </VList>
          </VMenu>
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
                  v-if="canManageJudges"
                  icon
                  size="small"
                  variant="text"
                  color="warning"
                  @click.stop="openRemoveJudgeDialog(judge)"
                >
                  <VIcon icon="tabler-unlink" />
                  <VTooltip activator="parent">Remove from project</VTooltip>
                </VBtn>
              </div>
            </template>
          </VListItem>
        </VList>

        <div v-else class="text-center pa-8">
          <VIcon icon="tabler-gavel-off" size="64" class="mb-4 text-disabled" />
          <h3 class="text-h6 mb-2">No LLM Judges</h3>
          <p class="text-body-2 mb-4">Add an LLM judge to evaluate your test cases</p>
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

    <VDialog v-model="showRemoveJudgeDialog" max-width="var(--dnr-dialog-sm)">
      <VCard>
        <VCardTitle>Remove LLM Judge</VCardTitle>
        <VCardText>
          <p>
            Remove "{{ judgeToRemove?.name }}" from this project?
            The judge will still be available in the organization and can be re-added later.
          </p>
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" @click="showRemoveJudgeDialog = false"> Cancel </VBtn>
          <VBtn color="warning" @click="confirmRemoveJudge"> Remove </VBtn>
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
