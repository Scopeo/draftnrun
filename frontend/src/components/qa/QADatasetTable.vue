<script setup lang="ts">
import { reactive } from 'vue'
import { useQADatasetTable } from '@/composables/useQADatasetTable'
import type { EditableField } from '@/composables/useQATestCaseEditing'

interface Props {
  projectId?: string
  graphRunners?: Array<{ graph_runner_id: string; tag_name?: string; env?: string | null }>
}

const props = withDefaults(defineProps<Props>(), {
  projectId: undefined,
  graphRunners: () => [],
})

const composable = useQADatasetTable(props)
const { fileInputRef } = composable
const t = reactive(composable)
</script>

<template>
  <div class="qa-dataset-container">
    <!-- Header -->
    <QADatasetTableHeader
      :current-dataset="t.currentDataset"
      :current-version="t.currentVersion"
      :datasets="t.datasetOptions"
      :versions="t.versionOptions"
      :can-manage-datasets="t.canManageDatasets"
      :unlinked-datasets="t.unlinkedDatasetOptions"
      @dataset-change="t.onDatasetChange"
      @version-change="t.onVersionChange"
      @create-dataset="t.showCreateDatasetDialog = true"
      @add-existing-dataset="t.addDatasetToProject"
      @remove-dataset="t.openRemoveDatasetDialog"
      @import-csv="t.triggerFileInput"
      @export-csv="t.exportDatasetToCSV"
    />

    <input ref="fileInputRef" type="file" accept=".csv" style="display: none" @change="t.handleFileSelect" />

    <VCard>
      <!-- Async QA Run Progress -->
      <div v-if="t.currentSessionId" class="qa-progress-bar px-4 pt-3">
        <div class="d-flex align-center justify-space-between mb-1">
          <span class="text-body-2 font-weight-medium">
            <template v-if="t.qaProgress.total > 0">
              Processing {{ t.qaProgress.index }}/{{ t.qaProgress.total }}...
            </template>
            <template v-else> Waiting for results... </template>
          </span>
          <div class="d-flex align-center gap-2">
            <VBtn
              v-if="t.wsDisconnected"
              icon
              variant="text"
              size="small"
              :loading="t.refreshing"
              title="Refresh"
              @click="t.refreshSessionStatus"
            >
              <VIcon icon="tabler-refresh" />
              <VTooltip activator="parent">Refresh results</VTooltip>
            </VBtn>
            <span v-if="t.qaProgress.total > 0" class="text-body-2 text-medium-emphasis">
              {{ Math.round(((t.qaProgress.index - 1) / t.qaProgress.total) * 100) }}%
            </span>
          </div>
        </div>
        <VProgressLinear
          v-if="t.qaProgress.total > 0"
          :model-value="((t.qaProgress.index - 1) / t.qaProgress.total) * 100"
          color="primary"
          height="6"
          rounded
        />
        <VProgressLinear v-else indeterminate color="primary" height="6" rounded />
      </div>

      <!-- Data Table -->
      <VDataTable
        v-model="t.selected"
        v-model:page="t.currentPage"
        v-model:items-per-page="t.itemsPerPage"
        :headers="t.headers"
        :items="t.testCases"
        :loading="t.loading"
        item-value="id"
        show-select
        class="qa-table"
      >
        <template #top>
          <QADatasetTableStatusBanner :show="t.shouldShowStatusBanner" :is-busy="t.isBusy" :text="t.statusText" />
        </template>

        <template #item.position="{ item }">
          <div class="qa-row-number text-center">{{ item.position }}</div>
        </template>

        <template #item.input="{ item }">
          <QATestCaseInputCell
            :test-case="item"
            :is-saving="t.activeSavingKey === `${item.id}-input` && t.savingState[`${item.id}-input`] === true"
            @click="t.openEditTestCaseDialog(item)"
          />
        </template>

        <template #item.groundtruth="{ item }">
          <QADatasetTableEditableCell
            :model-value="item.groundtruth"
            :saving="t.activeSavingKey === `${item.id}-groundtruth` && t.savingState[`${item.id}-groundtruth`] === true"
            placeholder="Click to add expected output..."
            @update:model-value="
              (val: any) => {
                item.groundtruth = val
                t.onUpdateTestCase(item, 'groundtruth')
              }
            "
            @cell-click="t.onCellClick(item, 'groundtruth', $event)"
          />
        </template>

        <!-- Custom Column Headers -->
        <template
          v-for="col in t.customColumns"
          :key="`header-custom-${col.column_id}`"
          #[`header.custom-${col.column_id}`]
        >
          <QACustomColumnHeader
            :column="col"
            :is-editing="t.editingColumnId === col.column_id"
            :editing-name="t.editingColumnName"
            @start-edit="t.startEditingColumnName(col)"
            @update-name="t.editingColumnName = $event"
            @save="t.saveEditingColumnName"
            @cancel="t.cancelEditingColumnName"
            @delete="t.openDeleteColumnDialog(col)"
          />
        </template>

        <!-- Custom Columns -->
        <template
          v-for="col in t.customColumns"
          :key="`custom-${col.column_id}`"
          #[`item.custom-${col.column_id}`]="{ item }"
        >
          <QADatasetTableEditableCell
            :model-value="item.custom_columns?.[col.column_id]"
            :saving="
              t.activeSavingKey === `${item.id}-custom-${col.column_id}` &&
              t.savingState[`${item.id}-custom-${col.column_id}`] === true
            "
            @update:model-value="
              (val: any) => {
                item.custom_columns![col.column_id] = val
                t.onUpdateTestCase(item, `custom-${col.column_id}` as EditableField)
              }
            "
            @cell-click="t.onCellClick(item, `custom-${col.column_id}` as EditableField, $event)"
          />
        </template>

        <template #item.output="{ item }">
          <QATestCaseOutputCell :test-case="item" @click="t.openOutputDialog(item)" />
        </template>

        <template #item.status="{ item }">
          <QATestCaseStatusCell :status="item.status" />
        </template>

        <template #item.actions="{ item }">
          <div class="d-flex align-center gap-1">
            <VBtn
              icon
              size="small"
              variant="text"
              color="primary"
              :loading="t.rowRunning[item.id] === true"
              :disabled="t.isRunning && t.rowRunning[item.id] !== true"
              @click="t.runSingleTest(item)"
            >
              <VIcon icon="tabler-player-play" />
              <VTooltip activator="parent">Run Test Case</VTooltip>
            </VBtn>
            <VBtn
              icon
              size="small"
              variant="text"
              color="secondary"
              :loading="t.rowEvaluating[item.id]"
              :disabled="!item.output || !item.version_output_id || !t.judges.length"
              @click="t.evaluateSingleTest(item)"
            >
              <VIcon icon="tabler-gavel" />
              <VTooltip activator="parent">{{ t.getEvaluateTooltip(item) }}</VTooltip>
            </VBtn>
          </div>
        </template>

        <template #header.evaluations-group>
          <div class="evaluations-group-header"><span>Evaluations</span></div>
        </template>

        <template #header.insert-column>
          <div class="d-flex align-center justify-center">
            <VBtn
              icon
              color="primary"
              variant="text"
              size="small"
              density="compact"
              :disabled="!t.currentDataset"
              @click="t.showCreateColumnDialog = true"
            >
              <VIcon icon="tabler-plus" size="18" />
              <VTooltip activator="parent">Create new column</VTooltip>
            </VBtn>
          </div>
        </template>

        <template #item.insert-column><div /></template>

        <template v-for="judge in t.judges" :key="`eval-header-${judge.id}`" #[`header.evaluation-${judge.id}`]>
          <div class="evaluation-sub-header">
            <span>{{ judge.name }}</span>
          </div>
        </template>

        <template v-for="judge in t.judges" :key="`eval-${judge.id}`" #[`item.evaluation-${judge.id}`]="{ item }">
          <JudgeEvaluationCell
            :test-case="item"
            :judge="judge"
            :loading="t.loadingEvaluations[item.id]"
            @click="t.handleJudgeEvaluationClick"
          />
        </template>

        <template #loading><VSkeletonLoader type="table-row@6" /></template>

        <template #no-data>
          <QADatasetTableEmptyState
            :has-datasets="t.hasDatasets"
            @create-dataset="t.showCreateDatasetDialog = true"
            @add-test-case="t.addNewTestCase"
          />
        </template>
      </VDataTable>

      <QADatasetTableActions
        :selected-count="t.selected.length"
        :selected-with-output-count="t.selectedWithOutput.length"
        :test-cases-count="t.testCases.length"
        :test-cases-with-output-count="t.testCasesWithOutput.length"
        :has-datasets="t.hasDatasets"
        :judges-count="t.judges.length"
        :can-evaluate-selected="t.canEvaluateSelected"
        :evaluating-selected="t.evaluatingSelected"
        :batch-running-all="t.batchRunningAll"
        :evaluating-all="t.evaluatingAll"
        :is-running="t.isRunning"
        :refreshing="t.refreshing"
        @run-selected="t.runSelectedTests"
        @evaluate-selected="t.evaluateSelectedTests"
        @run-all="t.runAllTests"
        @evaluate-all="t.evaluateAllTests"
        @delete-selected="t.confirmDeleteSelected"
        @add-test-case="t.addNewTestCase"
        @refresh="t.refreshSessionStatus"
      />
    </VCard>

    <QALLMJudgesManager :project-id="t.projectId" class="mt-4" />

    <!-- Dialogs -->
    <QACreateDatasetDialog v-model="t.showCreateDatasetDialog" :loading="t.creating" @create="t.createNewDataset" />

    <VDialog v-model="t.showRemoveDatasetDialog" max-width="var(--dnr-dialog-sm)">
      <VCard>
        <VCardTitle>Remove Dataset from Project</VCardTitle>
        <VCardText>
          <p>
            Remove "{{ t.currentDataset?.dataset_name }}" from this project?
            The dataset will still be available in the organization and can be re-added later.
          </p>
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" @click="t.showRemoveDatasetDialog = false"> Cancel </VBtn>
          <VBtn color="warning" @click="t.confirmRemoveDatasetFromProject"> Remove </VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <QACreateColumnDialog
      v-model="t.showCreateColumnDialog"
      :loading="t.creatingColumn"
      @create="t.createCustomColumn"
    />
    <QADeleteColumnDialog
      v-model="t.showDeleteColumnDialog"
      :column-name="t.columnToDelete?.column_name || ''"
      :loading="t.deletingColumn"
      @confirm="t.deleteCustomColumn"
    />
    <QADeleteTestCaseDialog v-model="t.showDeleteDialog" :loading="t.loading" @confirm="t.deleteSelectedTestCase" />

    <QATestCaseFormDialog
      v-model="t.showAddTestCaseDialog"
      mode="add"
      :messages="t.addTestCaseMessages"
      :additional-fields="t.addTestCaseAdditionalFields"
      :groundtruth="t.addTestCaseGroundtruth"
      :custom-columns="t.addTestCaseCustomColumns"
      :all-custom-columns="t.allCustomColumns"
      :is-column-visible="t.columnVisibility.isColumnVisible"
      :loading="t.addingTestCase"
      @update:messages="t.addTestCaseMessages = $event"
      @update:additional-fields="t.addTestCaseAdditionalFields = $event"
      @update:groundtruth="t.addTestCaseGroundtruth = $event"
      @update:custom-columns="t.addTestCaseCustomColumns = $event"
      @save="t.saveNewTestCase"
    />

    <QATestCaseFormDialog
      v-model="t.showEditTestCaseDialog"
      mode="edit"
      :test-case="t.editingTestCase"
      :messages="t.editTestCaseMessages"
      :additional-fields="t.editTestCaseAdditionalFields"
      groundtruth=""
      :custom-columns="{}"
      :all-custom-columns="t.allCustomColumns"
      :is-column-visible="t.columnVisibility.isColumnVisible"
      :loading="t.editingTestCaseLoading"
      @update:messages="t.editTestCaseMessages = $event"
      @update:additional-fields="t.editTestCaseAdditionalFields = $event"
      @save="t.saveEditedTestCase"
    />

    <QABulkDeleteDialog
      v-model="t.showBulkDeleteDialog"
      :count="t.selected.length"
      :loading="t.bulkDeleteLoading"
      @confirm="t.deleteSelectedTestCases"
    />
    <QADatasetOutputDialog
      v-model="t.showOutputDialog"
      :output-text="t.outputDialogText"
      :expected-output="t.outputDialogExpectedText"
      @update:expected-output="t.onOutputDialogExpectedUpdate"
    />
    <QADatasetEvaluationDialog
      v-model="t.showEvaluationDialog"
      :title="t.evaluationDialogTitle"
      :is-error="t.evaluationDialogIsError"
      :text="t.evaluationDialogText"
      :data="t.evaluationDialogData"
    />
    <QADatasetFloatingEditorDialog
      v-model="t.floatingEditor.open"
      :value="t.floatingEditor.value"
      :field="t.floatingEditor.field"
      @update:value="t.floatingEditor.value = $event"
      @blur="t.onFloatingEditorBlur"
    />

    <!-- Snackbar -->
    <VSnackbar
      v-model="t.showSnackbar"
      :color="
        t.snackbarType === 'error'
          ? 'error'
          : t.snackbarType === 'warning'
            ? 'warning'
            : t.snackbarType === 'success'
              ? 'success'
              : 'info'
      "
      :timeout="t.snackbarTimeout"
      location="bottom"
    >
      <VIcon
        :icon="
          t.snackbarType === 'error'
            ? 'tabler-alert-circle'
            : t.snackbarType === 'success'
              ? 'tabler-check'
              : t.snackbarType === 'warning'
                ? 'tabler-alert-triangle'
                : 'tabler-info-circle'
        "
        class="me-2"
      />
      {{ t.snackbarMessage }}
      <template #actions>
        <VBtn color="white" variant="text" @click="t.closeSnackbar">Close</VBtn>
      </template>
    </VSnackbar>
  </div>
</template>

<style lang="scss" scoped>
.qa-dataset-container {
  .qa-table {
    display: flex;
    flex-direction: column;
    inline-size: 100%;

    :deep(.v-data-table__wrapper) {
      overflow: auto visible;
      flex: 1 1 auto;
      min-block-size: 400px;
      -webkit-overflow-scrolling: touch;
    }

    :deep(.v-data-table-footer) {
      z-index: 10;
      flex-shrink: 0;
      background-color: rgb(var(--v-theme-surface));
      inline-size: 100%;
      overflow-x: visible;
    }

    :deep(.v-data-table-footer__items-per-page),
    :deep(.v-data-table-footer__info),
    :deep(.v-data-table-footer__pagination) {
      white-space: nowrap;
    }

    :deep(.v-textarea) {
      .v-field__input {
        min-block-size: auto;
      }
    }

    :deep(table) {
      inline-size: max-content;
      min-inline-size: 100%;
      table-layout: auto;
    }

    :deep(thead th) {
      white-space: nowrap;
    }

    :deep(tbody td[data-column-key='status']),
    :deep(tbody td[data-column-key='actions']),
    :deep(tbody td[data-column-key^='evaluation-']),
    :deep(thead th[data-column-key='status']),
    :deep(thead th[data-column-key='actions']),
    :deep(thead th[data-column-key^='evaluation-']) {
      white-space: nowrap;
    }

    :deep(thead th:nth-last-child(2)),
    :deep(tbody td:nth-last-child(2)) {
      inline-size: 120px;
    }

    :deep(thead th:last-child),
    :deep(tbody td:last-child) {
      inline-size: 110px;
    }

    :deep(thead th:nth-child(2)),
    :deep(tbody td:nth-child(2)) {
      color: rgba(var(--v-theme-on-surface), 0.6);
      font-variant-numeric: tabular-nums;
      inline-size: 36px;
      max-inline-size: 44px;
      text-align: center;
      white-space: nowrap;
    }
  }

  .text-disabled {
    :deep(.v-field__input) {
      color: rgba(var(--v-theme-on-surface), 0.38) !important;
    }
  }

  .qa-row-number {
    color: rgba(var(--v-theme-on-surface), 0.6);
    font-size: 0.75rem;
    font-variant-numeric: tabular-nums;
    inline-size: 100%;
    line-height: 1;
    padding-inline: 0;
    text-align: center;
    white-space: nowrap;
  }

  :deep(.v-data-table__wrapper) {
    thead tr:first-child th[data-column-key='evaluations-group'] {
      font-size: 0.875rem;
      font-weight: 500;
      text-align: center;
      text-transform: uppercase;
    }

    thead tr:last-child th[data-column-key^='evaluation-'] {
      color: rgba(var(--v-theme-on-surface), 0.7);
      font-size: 0.75rem;
      font-weight: 400;
      text-align: center;
      text-transform: none;
    }
  }

  .evaluations-group-header {
    font-weight: 500;
    text-align: center;
  }

  .evaluation-sub-header {
    color: rgba(var(--v-theme-on-surface), 0.7);
    font-size: 0.75rem;
    font-weight: 400;
    text-align: center;
    text-transform: none;
  }

  .evaluation-chip {
    cursor: pointer;
    inline-size: fit-content;
  }

  .judge-evaluation-cell {
    padding: 0.5rem;
    cursor: pointer;
    min-inline-size: 100px;

    &:hover {
      background-color: rgba(var(--v-theme-primary), 0.05);
    }
  }
}
</style>
