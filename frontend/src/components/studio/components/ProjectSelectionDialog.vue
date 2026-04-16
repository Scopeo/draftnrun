<script setup lang="ts">
import { computed } from 'vue'
import type { Project } from '@/composables/queries/useProjectsQuery'
import type { Agent } from '@/composables/queries/useAgentsQuery'
import ProjectAvatar from '@/components/projects/ProjectAvatar.vue'

interface Props {
  modelValue: boolean

  // Data passed from parent (centralized fetching)
  projects?: any[] | null
  agents?: any[] | null
}

const props = defineProps<Props>()
const emit = defineEmits(['update:modelValue', 'select'])

const dialog = computed({
  get: () => props.modelValue,
  set: value => emit('update:modelValue', value),
})

// Use data from parent props (centralized fetching)
const projects = computed(() => props.projects || [])
const agents = computed(() => props.agents || [])

const handleProjectSelect = (project: Project) => {
  emit('select', project.project_id)
  dialog.value = false
}

const handleAgentSelect = (agent: Agent) => {
  emit('select', agent.id) // agent.id contains the project_id from backend
  dialog.value = false
}

const handleCancel = () => {
  dialog.value = false
}
</script>

<template>
  <VDialog v-model="dialog" max-width="var(--dnr-dialog-lg)" persistent>
    <VCard>
      <VCardTitle class="d-flex align-center">
        <VIcon icon="tabler-folder" size="24" color="primary" class="me-2" />
        Select Project
      </VCardTitle>

      <VDivider />

      <VCardText class="pa-6">
        <div class="text-body-1 mb-6">Choose a project or agent to reference in this workflow.</div>

        <!-- Agent Projects Section -->
        <div class="mb-6">
          <div class="text-h6 mb-4 d-flex align-center">
            <VIcon icon="tabler-user-bolt" size="20" class="me-2" />
            Agent Projects
          </div>
          <VCard variant="outlined" class="mb-4">
            <div v-if="agents.length === 0" class="pa-4 text-center text-medium-emphasis">
              No agent projects available
            </div>
            <template v-else>
              <div
                v-for="(agent, agentIndex) in agents"
                :key="agent.id"
                class="pa-4 cursor-pointer hover-bg"
                @click="handleAgentSelect(agent)"
              >
                <div class="d-flex align-center justify-space-between">
                  <div class="d-flex align-center gap-3 flex-grow-1">
                    <ProjectAvatar :icon="agent.icon" :icon-color="agent.icon_color" size="small" />
                    <div class="flex-grow-1">
                      <div class="text-subtitle-1 font-weight-medium">{{ agent.name }}</div>
                      <div v-if="agent.description" class="text-body-2 text-medium-emphasis mt-1">
                        {{ agent.description }}
                      </div>
                    </div>
                  </div>
                  <VIcon icon="tabler-chevron-right" size="16" color="medium-emphasis" />
                </div>
                <VDivider v-if="agentIndex < agents.length - 1" class="mt-4" />
              </div>
            </template>
          </VCard>
        </div>

        <!-- Projects Section -->
        <div>
          <div class="text-h6 mb-4 d-flex align-center">
            <VIcon icon="tabler-folder" size="20" class="me-2" />
            Projects
          </div>
          <VCard variant="outlined">
            <div v-if="projects.length === 0" class="pa-4 text-center text-medium-emphasis">No projects available</div>
            <template v-else>
              <div
                v-for="(project, projectIndex) in projects"
                :key="project.project_id"
                class="pa-4 cursor-pointer hover-bg"
                @click="handleProjectSelect(project)"
              >
                <div class="d-flex align-center justify-space-between">
                  <div class="d-flex align-center gap-3 flex-grow-1">
                    <ProjectAvatar :icon="project.icon" :icon-color="project.icon_color" size="small" />
                    <div class="flex-grow-1">
                      <div class="text-subtitle-1 font-weight-medium">{{ project.project_name }}</div>
                      <div v-if="project.description" class="text-body-2 text-medium-emphasis mt-1">
                        {{ project.description }}
                      </div>
                    </div>
                  </div>
                  <VIcon icon="tabler-chevron-right" size="16" color="medium-emphasis" />
                </div>
                <VDivider v-if="projectIndex < projects.length - 1" class="mt-4" />
              </div>
            </template>
          </VCard>
        </div>
      </VCardText>

      <VDivider />

      <VCardActions class="pa-4">
        <VSpacer />
        <VBtn color="grey" variant="text" @click="handleCancel"> Cancel </VBtn>
      </VCardActions>
    </VCard>
  </VDialog>
</template>

<style lang="scss" scoped>
.hover-bg {
  transition: background-color 0.2s ease;

  &:hover {
    background-color: rgba(var(--v-theme-primary), 0.04);
  }
}
</style>
