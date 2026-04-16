<script setup lang="ts">
import { useAbility } from '@casl/vue'
import { computed, defineAsyncComponent, onMounted, reactive, ref } from 'vue'
import { useDataSources } from '@/composables/useDataSources'
import { useTracking } from '@/composables/useTracking'

const ability = useAbility()
const { useTabTracking, useSearchTracking } = useTracking()

const KnowledgeExplorer = defineAsyncComponent(() => import('@/components/knowledge/KnowledgeExplorer.vue'))
const knowledgeExplorerRef = ref<InstanceType<typeof KnowledgeExplorer> | null>(null)

const _raw = useDataSources()
const ds = reactive(_raw)

const requestKnowledgeClose = () => {
  if (knowledgeExplorerRef.value?.requestClose) {
    knowledgeExplorerRef.value.requestClose()
    return
  }
  ds.closeKnowledgeExplorer()
}

onMounted(() => {
  useTabTracking(_raw.activeTab, 'data-sources', () => ({
    org_id: ds.selectedOrgId,
    sources_count: ds.sourcesData.total,
    ingestion_tasks_count: ds.ingestionTasksData.total,
  }))
  useSearchTracking(
    _raw.sourceSearch,
    'data-sources-search',
    computed(() => ds.totalSources)
  )
})

definePage({
  meta: {
    action: 'read',
    subject: 'DataSource',
  },
})
</script>

<template>
  <AppPage>
    <AppPageHeader title="Knowledge Base" description="Manage your data sources and knowledge base." />

    <!-- Knowledge Explorer (full-screen overlay) -->
    <template v-if="ds.selectedKnowledgeSource">
      <div class="knowledge-explorer-wrapper">
        <VCard class="knowledge-explorer-wrapper__header">
          <VCardText class="d-flex align-center gap-2">
            <IconBtn variant="text" @click="requestKnowledgeClose">
              <VIcon icon="tabler-arrow-left" />
            </IconBtn>
            <div class="d-flex flex-column">
              <span class="text-sm text-medium-emphasis">Knowledge Explorer</span>
              <span class="text-h6">{{ ds.selectedKnowledgeSource.source_name }}</span>
            </div>
            <VSpacer />
          </VCardText>
        </VCard>

        <Suspense>
          <KnowledgeExplorer
            :key="ds.knowledgeExplorerKey"
            ref="knowledgeExplorerRef"
            :organization-id="ds.selectedOrgId"
            :source="ds.selectedKnowledgeSource"
            :editable="ability.can('update', 'Knowledge')"
            @close="ds.closeKnowledgeExplorer"
          />
        </Suspense>
      </div>
    </template>

    <!-- Main content: tabs -->
    <template v-else>
      <VTabs v-model="ds.activeTab" class="mb-0">
        <VTab value="sources">Available Data Sources</VTab>
        <VTab value="ingestion">Ingestion Tasks</VTab>
      </VTabs>

      <VWindow v-model="ds.activeTab">
        <VWindowItem value="sources">
          <DataSourcesTable
            :items="ds.paginatedSources"
            :total-items="ds.totalSources"
            :headers="ds.sourceHeaders"
            :items-per-page="ds.sourceItemsPerPage"
            :page="ds.sourcePage"
            :search="ds.sourceSearch"
            :loading="ds.sourcesData.loading"
            :error="ds.sourcesData.error"
            :is-initial-load="ds.sourcesData.isInitialLoad"
            :highlighted-source-id="ds.highlightedSourceId"
            @update:items-per-page="ds.sourceItemsPerPage = $event"
            @update:page="ds.sourcePage = $event"
            @update:search="ds.sourceSearch = $event"
            @update:options="ds.updateSourceOptions"
            @view="ds.viewDataSource"
            @delete="ds.deleteDataSource"
            @update="ds.updateDataSource"
            @add-files="ds.addFilesToSource"
            @open-upload="ds.showFileUploadDialog = true"
            @open-database="ds.showDatabaseDialog = true"
            @open-website="ds.showWebsiteDialog = true"
            @retry="ds.queryClient.invalidateQueries({ queryKey: ['sources', ds.selectedOrgId] })"
          />
        </VWindowItem>

        <VWindowItem value="ingestion">
          <IngestionTasksTable
            :tasks="ds.ingestionTasksData.tasks"
            :loading="ds.ingestionTasksData.loading"
            :error="ds.ingestionTasksData.error"
            :is-initial-load="ds.ingestionTasksData.isInitialLoad"
            @view-source="ds.viewSourceFromIngestion"
            @delete="ds.deleteIngestionTask"
            @show-error="ds.showTaskErrorDetails"
            @retry="ds.queryClient.invalidateQueries({ queryKey: ['ingestion-tasks', ds.selectedOrgId] })"
          />
        </VWindowItem>
      </VWindow>
    </template>

    <!-- Dialogs -->
    <DataSourceDialogUpload
      v-model="ds.showFileUploadDialog"
      :org-id="ds.selectedOrgId"
      @created="ds.handleDialogCreated"
    />

    <DataSourceDialogUpload
      v-model="ds.showAddFilesDialog"
      :org-id="ds.selectedOrgId"
      :source="ds.sourceToAddFiles"
      @created="ds.handleDialogCreated"
      @closed="ds.handleAddFilesClose"
    />

    <DataSourceDialogDatabase
      v-model="ds.showDatabaseDialog"
      :org-id="ds.selectedOrgId"
      @created="ds.handleDialogCreated"
    />

    <DataSourceDialogWebsite
      v-model="ds.showWebsiteDialog"
      :org-id="ds.selectedOrgId"
      @created="ds.handleDialogCreated"
    />

    <DataSourceDialogGoogleDrive
      v-model="ds.showGoogleDriveDialog"
      :org-id="ds.selectedOrgId"
      @created="ds.handleDialogCreated"
    />

    <!-- Confirmation Dialogs -->
    <GenericConfirmDialog
      v-if="ds.sourceToDelete"
      v-model:is-dialog-visible="ds.showDeleteConfirmation"
      :title="ds.getDeleteTitle()"
      :message="ds.getDeleteMessage()"
      confirm-text="Delete anyway"
      cancel-text="Cancel"
      confirm-color="error"
      :loading="ds.isCheckingUsage"
      @confirm="ds.handleDeleteConfirm"
      @cancel="ds.handleDeleteCancel"
    />

    <GenericConfirmDialog
      v-if="ds.sourceToUpdate"
      v-model:is-dialog-visible="ds.showUpdateConfirmation"
      title="Update Data Source"
      :message="`Are you sure you want to update the data source '${ds.sourceToUpdate.source_name}'? This will refresh the data from the database.`"
      confirm-text="Update"
      confirm-color="primary"
      :loading="ds.isUpdatingSource"
      @confirm="ds.handleUpdateConfirm"
      @cancel="ds.handleUpdateCancel"
    />

    <GenericConfirmDialog
      v-if="ds.taskToDelete"
      v-model:is-dialog-visible="ds.showIngestionTaskDeleteConfirmation"
      title="Confirm Delete"
      :message="`Are you sure you want to delete the ingestion task '${ds.taskToDelete.source_name}'? This action cannot be undone.`"
      confirm-text="Delete"
      confirm-color="error"
      @confirm="ds.handleIngestionTaskDeleteConfirm"
      @cancel="ds.handleIngestionTaskDeleteCancel"
    />

    <!-- Ingestion Task Error Details Dialog -->
    <VDialog v-model="ds.showIngestionTaskErrorDialog" max-width="var(--dnr-dialog-md)">
      <VCard>
        <VCardTitle class="d-flex align-center">
          <VIcon
            :icon="
              ds.taskWithError?.result_metadata?.type === 'error' ? 'tabler-alert-circle' : 'tabler-alert-triangle'
            "
            :color="ds.taskWithError?.result_metadata?.type === 'error' ? 'error' : 'warning'"
            size="24"
            class="me-2"
          />
          <span>
            {{
              ds.taskWithError?.result_metadata?.type === 'error' ? 'Ingestion Task Error' : 'Ingestion Task Warning'
            }}
          </span>
        </VCardTitle>
        <VCardText>
          <div v-if="ds.taskWithError?.result_metadata?.message">
            <strong class="mb-2 d-block">
              {{ ds.taskWithError?.result_metadata?.type === 'error' ? 'Error Details:' : 'Warning Details:' }}
            </strong>
            <VAlert
              :type="ds.taskWithError?.result_metadata?.type === 'error' ? 'error' : 'warning'"
              variant="tonal"
              class="mt-2"
            >
              {{ ds.taskWithError.result_metadata.message }}
            </VAlert>
          </div>
          <div v-else>
            <VAlert type="info" variant="tonal">No additional details available.</VAlert>
          </div>
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn color="primary" variant="elevated" @click="ds.showIngestionTaskErrorDialog = false">Close</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>
  </AppPage>
</template>

<style lang="scss">
.knowledge-explorer-wrapper {
  display: flex;
  flex-direction: column;
  block-size: calc(100vh - var(--v-layout-top, 0px) - var(--v-layout-bottom, 0px));
  overflow: hidden;
}

.knowledge-explorer-wrapper__header {
  flex-shrink: 0;
  margin-block-end: 1rem;
}
</style>
