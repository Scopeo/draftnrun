<script setup lang="ts">
import { computed, ref, toRef, watch } from 'vue'
import GenericConfirmDialog from '@/components/dialogs/GenericConfirmDialog.vue'
import { useVersionSorting } from '@/composables/useVersionSorting'
import { useVersionDeployment } from '@/composables/useVersionDeployment'
import { useVersionDraftLoading } from '@/composables/useVersionDraftLoading'
import { useContextMenu } from '@/composables/useVersionContextMenu'
import type { GraphRunner } from '@/types/version'

interface Props {
  graphRunners: GraphRunner[]
  currentGraphRunnerId: string | null | undefined
  projectId?: string
}

const props = defineProps<Props>()

const emit = defineEmits<{
  change: [graphRunnerId: string]
  deployed: [graphRunnerId: string, env: 'production' | 'draft']
}>()

// Use composables
const sorting = useVersionSorting(toRef(() => props.graphRunners))

const deployment = useVersionDeployment(
  toRef(() => props.projectId),
  graphRunnerId => {
    emit('deployed', graphRunnerId, 'production')
  }
)

const draftLoading = useVersionDraftLoading(
  toRef(() => props.projectId),
  graphRunnerId => {
    emit('deployed', graphRunnerId, 'draft')
  }
)

const contextMenu = useContextMenu()

// VSelect menu state
const isSelectMenuOpen = ref(false)

// Close context menu when VSelect opens
watch(isSelectMenuOpen, isOpen => {
  if (isOpen) contextMenu.closeMenu()
})

// Watch for deployment completion (watcher only stops spinner, doesn't emit)
deployment.watchDeploymentCompletion(
  toRef(() => props.graphRunners),
  () => {} // Empty callback - the immediate callback in useVersionDeployment handles emission
)

// Event handlers
const handleChange = (selectedGraphRunnerId: string | null) => {
  if (selectedGraphRunnerId) emit('change', selectedGraphRunnerId)
}

const handleContextMenu = (event: MouseEvent, graphRunnerId: string) => {
  if (!props.projectId) return

  const runner = props.graphRunners.find(r => r.graph_runner_id === graphRunnerId)
  if (runner?.env === 'draft') return // Don't show menu for draft

  contextMenu.openMenu(event, graphRunnerId)
}

const handleMenuItemRef = (el: HTMLElement | null, graphRunnerId: string) => {
  if (!props.projectId) return
  contextMenu.handleItemRef(el, graphRunnerId)
}

const handleDeploy = () => {
  if (contextMenu.menuTargetId.value) {
    deployment.deployToProduction(contextMenu.menuTargetId.value)
    contextMenu.closeMenu()
  }
}

const handleLoadDraft = async () => {
  if (contextMenu.menuTargetId.value) {
    await draftLoading.loadAsDraft(contextMenu.menuTargetId.value)
    contextMenu.closeMenu()
    // Callback handles emission now
  }
}

// Check if current menu target is production version
const isCurrentMenuTargetProduction = computed(() => {
  if (!contextMenu.menuTargetId.value) return false
  const runner = props.graphRunners.find(r => r.graph_runner_id === contextMenu.menuTargetId.value)
  return runner?.env === 'production'
})
</script>

<template>
  <div class="version-selector-wrapper">
    <VSelect
      v-if="sorting.sortedGraphRunners.value.length > 0"
      v-model:menu="isSelectMenuOpen"
      :model-value="currentGraphRunnerId"
      :items="sorting.sortedGraphRunners.value"
      item-title="versionLabel"
      item-value="graph_runner_id"
      density="compact"
      variant="outlined"
      hide-details
      :disabled="deployment.isDeploying.value || draftLoading.isLoadingDraft.value"
      class="version-selector"
      @update:model-value="handleChange"
    >
      <!-- Selected item display -->
      <template #selection="{ item }">
        <div class="d-flex align-center gap-2">
          <span class="font-weight-medium">{{ item.raw.versionLabel }}</span>
          <VChip v-if="item.raw.env" :color="sorting.getEnvColor(item.raw.env)" size="x-small" class="text-capitalize">
            {{ sorting.getEnvLabel(item.raw.env) }}
          </VChip>
        </div>
      </template>

      <!-- Dropdown item display -->
      <template #item="{ props: itemProps, item }">
        <VListItem
          v-bind="itemProps"
          :ref="(el: any) => handleMenuItemRef(el, item.raw.graph_runner_id)"
          :title="item.raw.versionLabel"
          @contextmenu.prevent="handleContextMenu($event, item.raw.graph_runner_id)"
        >
          <template #append>
            <VChip
              v-if="item.raw.env"
              :color="sorting.getEnvColor(item.raw.env)"
              size="x-small"
              class="text-capitalize"
            >
              {{ sorting.getEnvLabel(item.raw.env) }}
            </VChip>
          </template>
        </VListItem>

        <!-- Context menu for deployment actions -->
        <VMenu
          v-if="projectId && item.raw.env !== 'draft' && contextMenu.menuTargetId.value === item.raw.graph_runner_id"
          v-model="contextMenu.menuVisible.value"
          :activator="contextMenu.menuActivatorElement.value as any"
          location="bottom end"
          :close-on-content-click="false"
        >
          <VList density="compact">
            <VListItem
              :disabled="
                deployment.isDeploying.value || draftLoading.isLoadingDraft.value || isCurrentMenuTargetProduction
              "
              @click="handleDeploy"
              @contextmenu.prevent.stop="
                () => {
                  contextMenu.closeMenu()
                  isSelectMenuOpen = true
                }
              "
            >
              <template #prepend>
                <VProgressCircular v-if="deployment.isDeploying.value" indeterminate size="20" width="2" class="me-2" />
                <VIcon v-else icon="tabler-cloud-upload" />
              </template>
              <VListItemTitle>Deploy to Production</VListItemTitle>
            </VListItem>

            <VListItem
              :disabled="deployment.isDeploying.value || draftLoading.isLoadingDraft.value"
              @click="handleLoadDraft"
              @contextmenu.prevent.stop="
                () => {
                  contextMenu.closeMenu()
                  isSelectMenuOpen = true
                }
              "
            >
              <template #prepend>
                <VProgressCircular
                  v-if="draftLoading.isLoadingDraft.value"
                  indeterminate
                  size="20"
                  width="2"
                  class="me-2"
                />
                <VIcon v-else icon="tabler-edit" />
              </template>
              <VListItemTitle>Start draft from this version</VListItemTitle>
            </VListItem>
          </VList>
        </VMenu>
      </template>
    </VSelect>

    <!-- Loading spinner overlay -->
    <VProgressCircular
      v-if="deployment.isDeploying.value"
      indeterminate
      size="24"
      width="2"
      class="deployment-spinner"
    />
  </div>

  <!-- Confirmation dialogs -->
  <GenericConfirmDialog
    v-model:is-dialog-visible="deployment.showConfirmDialog.value"
    title="Deploy to Production"
    message="A version is already deployed in production. Are you sure you want to deploy this version? This will replace the current production version."
    confirm-text="Deploy this version"
    confirm-color="error"
    @confirm="deployment.confirmDeployment"
    @cancel="deployment.cancelDeployment"
  />

  <GenericConfirmDialog
    v-model:is-dialog-visible="draftLoading.showConfirmDialog.value"
    title="Start draft from this version"
    message="Current draft will be erased and replaced by this version, you are going to lose your changes on the current draft"
    confirm-text="Continue"
    confirm-color="error"
    @confirm="draftLoading.confirmLoadDraft"
    @cancel="draftLoading.cancelLoadDraft"
  />

  <!-- Error snackbars -->
  <VSnackbar v-model="deployment.showError.value" color="error" :timeout="5000" location="bottom">
    <VIcon icon="tabler-alert-circle" class="me-2" />
    {{ deployment.errorMessage.value }}
    <template #actions>
      <VBtn color="white" variant="text" @click="deployment.showError.value = false"> Close </VBtn>
    </template>
  </VSnackbar>

  <VSnackbar v-model="draftLoading.showError.value" color="error" :timeout="5000" location="bottom">
    <VIcon icon="tabler-alert-circle" class="me-2" />
    {{ draftLoading.errorMessage.value }}
    <template #actions>
      <VBtn color="white" variant="text" @click="draftLoading.showError.value = false"> Close </VBtn>
    </template>
  </VSnackbar>
</template>

<style lang="scss" scoped>
.version-selector-wrapper {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.version-selector {
  min-inline-size: 180px;
  max-inline-size: 250px;

  :deep(.v-field) {
    --v-field-padding-start: 10px;
    --v-field-padding-end: 4px;
  }

  :deep(.v-field__input) {
    padding-block: 2px;
    min-block-size: 32px;
  }
}

.deployment-spinner {
  position: absolute;
  right: -32px;
  top: 50%;
  transform: translateY(-50%);
}
</style>
