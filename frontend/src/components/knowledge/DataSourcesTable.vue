<script setup lang="ts">
import { useAbility } from '@casl/vue'
import type { Source } from '@/composables/queries/useDataSourcesQuery'
import { formatSourceDateTime } from '@/composables/useDataSources'

defineProps<{
  items: Source[]
  totalItems: number
  headers: any[]
  itemsPerPage: number
  page: number
  search: string
  loading: boolean
  error: Error | null
  isInitialLoad: boolean
  highlightedSourceId: string | null
}>()

const emit = defineEmits<{
  'update:itemsPerPage': [value: number]
  'update:page': [value: number]
  'update:search': [value: string]
  'update:options': [options: any]
  view: [item: Source]
  delete: [item: Source]
  update: [item: Source]
  addFiles: [item: Source]
  openUpload: []
  openDatabase: []
  openWebsite: []
  retry: []
}>()

const ability = useAbility()
</script>

<template>
  <VCard class="mt-0 rounded-t-0">
    <VCardText class="d-flex align-center justify-space-between flex-wrap gap-4 pt-4">
      <VTextField
        :model-value="search"
        placeholder="Search Sources"
        style="max-inline-size: 250px"
        clearable
        density="compact"
        @update:model-value="emit('update:search', ($event as string) ?? '')"
      />
      <VMenu>
        <template #activator="{ props }">
          <VBtn v-bind="props" prepend-icon="tabler-plus" :disabled="!ability.can('create', 'DataSource')">
            Add Data Source
          </VBtn>
        </template>
        <VList>
          <VListItem prepend-icon="tabler-upload" @click="emit('openUpload')">
            <VListItemTitle>Upload Files</VListItemTitle>
          </VListItem>
          <VListItem prepend-icon="tabler-database" @click="emit('openDatabase')">
            <VListItemTitle>Connect Database</VListItemTitle>
          </VListItem>
          <VListItem prepend-icon="tabler-world" @click="emit('openWebsite')">
            <VListItemTitle>Website Ingestion</VListItemTitle>
          </VListItem>
        </VList>
      </VMenu>
    </VCardText>
    <VDivider />

    <VCardText v-if="isInitialLoad && loading" class="d-flex justify-center align-center pa-4">
      <VProgressCircular indeterminate color="primary" />
    </VCardText>
    <VCardText v-else-if="error" class="d-flex justify-center align-center pa-4">
      <VAlert type="error" title="Error loading sources" prominent>
        <p>{{ error?.message || 'An unknown error occurred while fetching sources.' }}</p>
        <template #append>
          <VBtn variant="text" @click="emit('retry')">Retry</VBtn>
        </template>
      </VAlert>
    </VCardText>

    <VDataTableServer
      v-else
      :items-per-page="itemsPerPage"
      :page="page"
      :headers="headers"
      :items="items"
      :items-length="totalItems"
      class="text-no-wrap"
      @update:items-per-page="emit('update:itemsPerPage', $event)"
      @update:page="emit('update:page', $event)"
      @update:options="emit('update:options', $event)"
    >
      <template #item="{ item, columns }">
        <tr :class="{ 'highlighted-source-row': item.id === highlightedSourceId }">
          <td v-for="column in columns" :key="column.key || ''">
            <template v-if="column.key === 'source_type'">
              <div class="d-flex align-center">
                <VIcon
                  v-if="item.source_type === 'google_drive'"
                  icon="tabler-brand-google-drive"
                  size="18"
                  class="me-2"
                />
                <VIcon v-else-if="item.source_type === 'pdf'" icon="tabler-file-text" size="18" class="me-2" />
                <VIcon
                  v-else-if="item.source_type === 'postgresql' || item.source_type === 'database'"
                  icon="tabler-database"
                  size="18"
                  class="me-2"
                />
                <VIcon v-else-if="item.source_type === 'api'" icon="tabler-api" size="18" class="me-2" />
                <VIcon v-else-if="item.source_type === 'local'" icon="tabler-upload" size="18" class="me-2" />
                <VIcon v-else-if="item.source_type === 'website'" icon="tabler-world" size="18" class="me-2" />
                <VIcon v-else icon="tabler-file" size="18" class="me-2" />
                {{ item.source_type }}
              </div>
            </template>
            <template v-else-if="column.key === 'source_name'">
              <button
                v-if="item.source_type === 'local' || item.source_type === 'website'"
                type="button"
                class="source-name-button"
                @click="emit('view', item)"
              >
                {{ item.source_name || item.id }}
              </button>
              <span v-else>{{ item.source_name || item.id }}</span>
            </template>
            <template v-else-if="column.key === 'actions'">
              <VMenu>
                <template #activator="{ props }">
                  <IconBtn v-bind="props">
                    <VIcon icon="tabler-dots-vertical" />
                  </IconBtn>
                </template>
                <VList density="compact">
                  <VListItem
                    v-if="item.source_type === 'local' || item.source_type === 'website'"
                    @click="emit('view', item)"
                  >
                    <template #prepend><VIcon icon="tabler-eye" size="18" /></template>
                    <VListItemTitle>View</VListItemTitle>
                  </VListItem>
                  <VListItem
                    v-if="
                      (item.source_type === 'postgresql' || item.source_type === 'database') &&
                      ability.can('update', 'DataSource')
                    "
                    @click="emit('update', item)"
                  >
                    <template #prepend><VIcon icon="tabler-refresh" size="18" /></template>
                    <VListItemTitle>Update</VListItemTitle>
                  </VListItem>
                  <VListItem
                    v-if="item.source_type === 'local' && ability.can('update', 'DataSource')"
                    @click="emit('addFiles', item)"
                  >
                    <template #prepend><VIcon icon="tabler-file-plus" size="18" /></template>
                    <VListItemTitle>Add Files</VListItemTitle>
                  </VListItem>
                  <VListItem v-if="ability.can('delete', 'DataSource')" @click="emit('delete', item)">
                    <template #prepend><VIcon icon="tabler-trash" size="18" color="error" /></template>
                    <VListItemTitle class="text-error">Delete</VListItemTitle>
                  </VListItem>
                </VList>
              </VMenu>
            </template>
            <template v-else-if="column.key === 'created_at' || column.key === 'updated_at'">
              {{ formatSourceDateTime(item[column.key as keyof Source]) }}
            </template>
            <template v-else>
              {{ item[column.key as keyof Source] }}
            </template>
          </td>
        </tr>
      </template>

      <template #no-data>
        <EmptyState
          icon="tabler-database-off"
          title="No Data Sources Found"
          description="Add a data source to start building your knowledge base."
        />
      </template>
    </VDataTableServer>
  </VCard>
</template>

<style lang="scss" scoped>
.highlighted-source-row {
  background-color: rgba(var(--v-theme-primary), 0.1) !important;
  transition: background-color 0.5s ease-in-out;
}

.highlighted-source-row:hover td {
  background-color: rgba(var(--v-theme-primary), 0.15) !important;
}

.source-name-button {
  padding: 0;
  border: none;
  background: transparent;
  color: rgb(var(--v-theme-primary));
  cursor: pointer;
  font: inherit;
}

.source-name-button:hover,
.source-name-button:focus {
  text-decoration: underline;
}
</style>
