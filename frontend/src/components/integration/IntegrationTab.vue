<script setup lang="ts">
import { computed, ref } from 'vue'
import ChatBubbleConfig from '@/components/integration/ChatBubbleConfig.vue'
import SharedAPI from '@/components/shared/SharedAPI.vue'

interface Props {
  // Project props (for workflows)
  projectId?: string
  projectName?: string
  organizationId?: string
  // Agent props
  agentId?: string
  agentName?: string
}

const props = defineProps<Props>()

const activeSubTab = ref('api')

// Determine if this is an agent context
const isAgent = computed(() => !!props.agentId)
</script>

<template>
  <div class="integration-tab">
    <VTabs v-model="activeSubTab" class="integration-tabs">
      <VTab value="api">
        <VIcon icon="tabler-api" size="18" class="me-2" />
        API / Webhook
      </VTab>
      <VTab value="chat-bubble">
        <VIcon icon="tabler-message-circle" size="18" class="me-2" />
        Chat Bubble
      </VTab>
      <VTab value="internal">
        <VIcon icon="tabler-robot" size="18" class="me-2" />
        Internal Assistants
      </VTab>
    </VTabs>

    <VWindow v-model="activeSubTab" class="integration-window">
      <VWindowItem value="api" class="integration-window-item">
        <SharedAPI v-if="isAgent" :agent="{ id: agentId, name: agentName }" type="agent" />
        <SharedAPI v-else :project-id="projectId" :project-name="projectName" type="workflow" />
      </VWindowItem>
      <VWindowItem value="chat-bubble" class="integration-window-item">
        <ChatBubbleConfig
          :project-id="agentId || projectId"
          :project-name="agentName || projectName"
          :organization-id="organizationId"
        />
      </VWindowItem>
      <VWindowItem value="internal" class="integration-window-item">
        <VCard class="pa-6 text-center fill-height d-flex align-center justify-center">
          <VCardText>
            <VIcon icon="tabler-robot" size="64" class="mb-4 text-primary" />
            <h3 class="text-h5 mb-2">Internal Assistants</h3>
            <p class="text-body-1 text-medium-emphasis">
              Workflows and deployed agents are accessible at
              <a href="https://chat.draftnrun.com" target="_blank" rel="noopener noreferrer" class="text-primary"
                >chat.draftnrun.com</a
              >
            </p>
          </VCardText>
        </VCard>
      </VWindowItem>
    </VWindow>
  </div>
</template>

<style scoped>
.integration-tab {
  height: 100%;
  overflow-y: auto;
}

.integration-tabs {
  position: sticky;
  top: 0;
  z-index: 1;
  background: rgb(var(--v-theme-surface));
  margin-bottom: 24px;
}

.integration-window {
  margin-top: 8px;
}
</style>
