<script setup lang="ts">
import { Icon } from '@iconify/vue'
import { computed, nextTick, ref, watch } from 'vue'
import { VTextField } from 'vuetify/components/VTextField'
import { isProviderLogo } from '../utils/node-factory.utils'
import { useCategoryMaps } from '@/composables/useCategoryMaps'
import { useLLMCredits } from '@/composables/useLLMCredits'

interface Props {
  modelValue: boolean
  mode: 'component' | 'tool' | 'agent-tool'
  componentDefinitions?: any[] | null
  categories?: any[] | null
  excludedTools?: Set<string> // Set of component_version_ids to exclude from the list
}

const props = withDefaults(defineProps<Props>(), {
  excludedTools: () => new Set(),
  categories: () => [],
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  'tool-selected': [tool: any]
}>()

const MODAL_MAX_WIDTH = 'var(--dnr-dialog-xl)'
const FALLBACK_CATEGORY_NAME = 'Other' as const

// Composables
const categoriesRef = computed(() => props.categories || [])
const { categoriesMapById, categoriesMapByName } = useCategoryMaps(categoriesRef)
const { getCreditDisplay } = useLLMCredits()

// Dialog model that syncs with parent
const dialog = computed({
  get: () => props.modelValue,
  set: value => emit('update:modelValue', value),
})

// Three-panel carousel navigation state
const selectedCategory = ref<string | null>(null)
const navigationMode = ref<'categories' | 'detail'>('categories')
const selectedToolForDetail = ref<any | null>(null)
const previousCategory = ref<string | null>(null)
const searchQuery = ref('')
const searchInputRef = ref<InstanceType<typeof VTextField> | null>(null)

// Filter components based on mode
const availableComponents = computed(() => {
  const allDefs = props.componentDefinitions || []

  // Always exclude the Start component from the selection dialog
  const startComponentId = import.meta.env.VITE_START_COMPONENT_ID

  const filtered = allDefs.filter(
    comp =>
      comp.id !== startComponentId &&
      comp.component_id !== startComponentId &&
      !props.excludedTools.has(comp.component_version_id)
  )

  if (props.mode === 'component') {
    // For component mode, only show components where is_agent is true
    return filtered.filter(comp => comp.is_agent)
  } else {
    // For tool and agent-tool modes, show only function_callable components
    return filtered.filter(comp => comp.function_callable)
  }
})

// Group tools/components by category using category_ids from backend
const toolsByCategory = computed(() => {
  const filtered = availableComponents.value.filter(tool => {
    if (!searchQuery.value) return true
    const query = searchQuery.value.toLowerCase()

    return tool.name.toLowerCase().includes(query) || tool.description?.toLowerCase().includes(query)
  })

  const categories: Record<string, any[]> = {}

  filtered.forEach(tool => {
    // Use category_ids from backend, with fallback to FALLBACK_CATEGORY_NAME
    const categoryIds = tool.category_ids ?? []

    if (categoryIds.length === 0) {
      // No categories, add to fallback category
      if (!categories[FALLBACK_CATEGORY_NAME]) categories[FALLBACK_CATEGORY_NAME] = []
      categories[FALLBACK_CATEGORY_NAME].push(tool)
    } else {
      // Add tool to each of its categories (tools can appear in multiple categories)
      categoryIds.forEach((categoryId: string) => {
        const category = categoriesMapById.value.get(categoryId)
        if (category) {
          const categoryName = category.name
          if (!categories[categoryName]) categories[categoryName] = []
          categories[categoryName].push(tool)
        }
      })
    }
  })

  return categories
})

// Category metadata with icons and descriptions
const getCategoryMetadata = (key: string) => {
  const category = categoriesMapByName.value.get(key)

  if (category) {
    return {
      name: category.name,
      icon: category.icon || 'tabler-category',
      description: category.description || '',
    }
  }

  // Fallback for categories not in backend (like fallback category)
  if (key === FALLBACK_CATEGORY_NAME) {
    return {
      name: FALLBACK_CATEGORY_NAME,
      icon: 'tabler-dots',
      description: 'Additional components and tools',
    }
  }

  return {
    name: key,
    icon: 'tabler-tool',
    description: '',
  }
}

// When search is active, show tools directly
const isSearchActive = computed(() => !!searchQuery.value?.trim())

// All available tools filtered by search query
const filteredTools = computed(() => {
  const allTools = availableComponents.value

  if (!searchQuery.value) return allTools

  const query = searchQuery.value.toLowerCase()

  return allTools.filter(
    tool => tool.name.toLowerCase().includes(query) || tool.description?.toLowerCase().includes(query)
  )
})

// Tools to display: depends on navigation mode and search state
const displayTools = computed(() => {
  if (isSearchActive.value) {
    // When searching, show all matching tools
    return filteredTools.value
  } else if (navigationMode.value === 'detail' && previousCategory.value) {
    // In detail mode, show tools from the category we came from
    return toolsByCategory.value[previousCategory.value] || []
  } else if (selectedCategory.value) {
    // In category mode with selected category, show tools in that category
    return toolsByCategory.value[selectedCategory.value] || []
  } else {
    // Default: return empty
    return []
  }
})

// Categories to display (only in category mode when not searching)
const displayCategories = computed(() => {
  // Only show categories in category mode
  if (navigationMode.value !== 'categories') return []
  if (isSearchActive.value) return []

  const keys = Object.keys(toolsByCategory.value)

  // Sort category keys by display_order
  return keys.sort((a, b) => {
    const categoryA = categoriesMapByName.value.get(a)
    const categoryB = categoriesMapByName.value.get(b)
    const orderA = categoryA?.display_order ?? 999
    const orderB = categoryB?.display_order ?? 999
    return orderA - orderB
  })
})

// Initialize modal with first available category pre-selected
watch(
  () => props.modelValue,
  async isOpen => {
    if (isOpen) {
      // Pre-select first available category
      selectedCategory.value = displayCategories.value[0] || null
      navigationMode.value = 'categories'
      selectedToolForDetail.value = null
      previousCategory.value = null
      searchQuery.value = ''

      await nextTick()
      searchInputRef.value?.focus()
    }
  }
)

// Auto-select first tool when searching
watch(
  () => searchQuery.value,
  async newQuery => {
    if (newQuery?.trim()) {
      // Search is active - enter detail mode
      navigationMode.value = 'detail'
      previousCategory.value = selectedCategory.value
      selectedCategory.value = null

      await nextTick()

      // Auto-select first filtered tool
      if (filteredTools.value.length > 0) {
        selectedToolForDetail.value = filteredTools.value[0]
      } else {
        selectedToolForDetail.value = null
      }
    } else {
      // Search cleared - return to category mode
      if (navigationMode.value === 'detail' && !selectedCategory.value) {
        navigationMode.value = 'categories'
        selectedCategory.value = previousCategory.value || displayCategories.value[0] || null
        selectedToolForDetail.value = null
      }
    }
  }
)

// Navigation handlers for carousel modal
const handleSelectCategory = (categoryKey: string) => {
  selectedCategory.value = categoryKey
  navigationMode.value = 'categories'
  selectedToolForDetail.value = null
  searchQuery.value = ''
}

const handleBackToCategories = () => {
  if (navigationMode.value === 'detail') {
    // Go back to category mode
    navigationMode.value = 'categories'
    selectedCategory.value = previousCategory.value || displayCategories.value[0] || null
    selectedToolForDetail.value = null
    searchQuery.value = ''
  }
}

const handleCloseModal = () => {
  dialog.value = false
  selectedCategory.value = null
  selectedToolForDetail.value = null
  navigationMode.value = 'categories'
  previousCategory.value = null
  searchQuery.value = ''
}

// Handle clicking on a tool - enter detail mode
const handleClickTool = async (tool: any) => {
  // Enter detail mode
  previousCategory.value = selectedCategory.value
  navigationMode.value = 'detail'
  selectedToolForDetail.value = tool
}

// Confirm selection (called from "Add Tool/Component" button in detail view)
const confirmSelection = async (tool: any) => {
  emit('tool-selected', tool)
  handleCloseModal()
}

// Get release stage chip configuration
const getReleaseStageChip = (releaseStage?: string) => {
  if (!releaseStage) return null

  const stage = releaseStage.toLowerCase()

  if (stage === 'beta') {
    return {
      text: 'Beta',
      color: 'warning',
    }
  } else if (stage === 'internal') {
    return {
      text: 'Alpha',
      color: 'error',
    }
  }

  return null
}

// Get the button text based on mode
const getButtonText = computed(() => {
  if (props.mode === 'component') {
    return 'Add Component'
  }
  return 'Add Tool'
})

// Get the dialog title based on mode
const getDialogTitle = computed(() => {
  if (selectedToolForDetail.value) {
    return selectedToolForDetail.value.name
  }
  if (props.mode === 'component') {
    return 'Add Component'
  }
  return 'Add Tool'
})

// Get the search placeholder based on mode
const getSearchPlaceholder = computed(() => {
  if (props.mode === 'component') {
    return 'Search components...'
  }
  return 'Search tools...'
})
</script>

<template>
  <VDialog v-model="dialog" :max-width="MODAL_MAX_WIDTH" content-class="tool-dialog-content">
    <VCard>
      <VCardTitle class="d-flex align-center justify-space-between pa-4">
        <div class="d-flex align-center">
          <VBtn
            v-if="navigationMode === 'detail'"
            icon
            variant="text"
            size="small"
            class="me-2"
            @click="handleBackToCategories"
          >
            <VIcon icon="tabler-arrow-left" />
          </VBtn>
          <span class="text-h5">
            {{ getDialogTitle }}
          </span>
        </div>
        <VBtn icon variant="text" size="small" @click="handleCloseModal">
          <VIcon icon="tabler-x" />
        </VBtn>
      </VCardTitle>

      <VDivider />

      <VCardText class="pa-4">
        <VTextField
          ref="searchInputRef"
          v-model="searchQuery"
          :placeholder="getSearchPlaceholder"
          prepend-inner-icon="tabler-search"
          variant="outlined"
          density="comfortable"
          clearable
          hide-details
        />
      </VCardText>

      <VCardText class="pa-0">
        <div class="modal-content-container">
          <div class="carousel-wrapper" :class="{ 'show-detail': navigationMode === 'detail' }">
            <!-- Panel 1: Categories -->
            <div class="carousel-panel pa-4">
              <div v-if="!isSearchActive">
                <VList v-if="displayCategories.length > 0" class="pa-0">
                  <VListItem
                    v-for="categoryKey in displayCategories"
                    :key="categoryKey"
                    class="modal-list-item mb-2 pa-3"
                    :class="{ 'selected-category': selectedCategory === categoryKey }"
                    @click="handleSelectCategory(categoryKey)"
                  >
                    <template #prepend>
                      <VAvatar size="40" color="primary" variant="tonal">
                        <VIcon :icon="getCategoryMetadata(categoryKey).icon" size="20" />
                      </VAvatar>
                    </template>

                    <VListItemTitle class="font-weight-medium mb-1">
                      {{ getCategoryMetadata(categoryKey).name }}
                    </VListItemTitle>
                    <VListItemSubtitle class="text-body-2 modal-item-description">
                      {{ getCategoryMetadata(categoryKey).description }}
                    </VListItemSubtitle>

                    <template #append>
                      <VIcon icon="tabler-chevron-right" size="20" class="text-medium-emphasis" />
                    </template>
                  </VListItem>
                </VList>

                <EmptyState v-else icon="tabler-puzzle" title="No categories available" size="sm" />
              </div>
            </div>

            <!-- Panel 2: Tools List (visible in both modes) -->
            <div class="carousel-panel pa-4">
              <VList v-if="displayTools.length > 0" class="pa-0">
                <VListItem
                  v-for="tool in displayTools"
                  :key="tool.component_version_id"
                  class="modal-list-item mb-2 pa-3"
                  :class="{
                    'selected-tool':
                      selectedToolForDetail && tool.component_version_id === selectedToolForDetail.component_version_id,
                  }"
                  @click="handleClickTool(tool)"
                >
                  <template #prepend>
                    <VAvatar
                      size="40"
                      :color="isProviderLogo(tool.icon) ? undefined : 'primary'"
                      :variant="isProviderLogo(tool.icon) ? 'flat' : 'tonal'"
                    >
                      <Icon v-if="isProviderLogo(tool.icon)" :icon="tool.icon" :width="20" :height="20" />
                      <VIcon v-else :icon="tool.icon || 'tabler-tool'" size="20" />
                    </VAvatar>
                  </template>

                  <VListItemTitle class="font-weight-medium mb-1 d-flex align-center gap-2">
                    <span>{{ tool.name }}</span>
                    <VChip
                      v-if="getReleaseStageChip(tool.release_stage)"
                      :color="getReleaseStageChip(tool.release_stage)?.color"
                      size="x-small"
                      variant="tonal"
                      class="release-stage-chip"
                    >
                      {{ getReleaseStageChip(tool.release_stage)?.text }}
                    </VChip>
                  </VListItemTitle>
                  <VListItemSubtitle class="text-body-2 modal-item-description">
                    {{ tool.description || 'No description available' }}
                  </VListItemSubtitle>
                </VListItem>
              </VList>

              <EmptyState
                v-else
                icon="tabler-search-off"
                :title="`${mode === 'component' ? 'No components' : 'No tools'} found${isSearchActive ? ' matching your search' : ''}`"
                size="sm"
              />
            </div>

            <!-- Panel 3: Tool/Component Details -->
            <div class="carousel-panel pa-4">
              <div v-if="selectedToolForDetail" class="d-flex flex-column h-100">
                <!-- Tool content scroll area -->
                <div class="tool-detail-scroll-content flex-grow-1">
                  <!-- Tool header -->
                  <div class="d-flex align-center mb-8">
                    <VAvatar
                      size="64"
                      :color="isProviderLogo(selectedToolForDetail.icon) ? undefined : 'primary'"
                      :variant="isProviderLogo(selectedToolForDetail.icon) ? 'flat' : 'tonal'"
                      class="me-5"
                    >
                      <Icon
                        v-if="isProviderLogo(selectedToolForDetail.icon)"
                        :icon="selectedToolForDetail.icon || ''"
                        :width="32"
                        :height="32"
                      />
                      <VIcon v-else :icon="selectedToolForDetail.icon || 'tabler-tool'" size="32" />
                    </VAvatar>
                    <div class="flex-grow-1">
                      <h2 class="text-h4 font-weight-bold mb-1 d-flex align-center gap-2">
                        <span>{{ selectedToolForDetail.name }}</span>
                        <VChip
                          v-if="getReleaseStageChip(selectedToolForDetail.release_stage)"
                          :color="getReleaseStageChip(selectedToolForDetail.release_stage)?.color"
                          size="small"
                          variant="tonal"
                        >
                          {{ getReleaseStageChip(selectedToolForDetail.release_stage)?.text }}
                        </VChip>
                      </h2>
                      <VChip size="small" color="info" variant="tonal" class="font-weight-medium">
                        {{ getCreditDisplay(selectedToolForDetail) }}
                      </VChip>
                    </div>
                  </div>

                  <!-- Description -->
                  <div class="mb-8">
                    <h3 class="detail-section-label mb-3">Description</h3>
                    <p class="text-body-1 detail-description-text">
                      {{ selectedToolForDetail.description || 'No description available' }}
                    </p>
                  </div>

                  <!-- Version -->
                  <div v-if="selectedToolForDetail.version_tag" class="mb-8">
                    <h3 class="detail-section-label mb-3">Version</h3>
                    <p class="text-body-1">
                      {{ selectedToolForDetail.version_tag }}
                    </p>
                  </div>

                  <!-- Categories -->
                  <div
                    v-if="selectedToolForDetail.category_ids && selectedToolForDetail.category_ids.length > 0"
                    class="mb-8"
                  >
                    <h3 class="detail-section-label mb-3">Categories</h3>
                    <div class="d-flex flex-wrap gap-2">
                      <VChip
                        v-for="categoryId in selectedToolForDetail.category_ids"
                        :key="categoryId"
                        size="small"
                        color="primary"
                        variant="tonal"
                        class="px-3"
                      >
                        <VIcon
                          v-if="categoriesMapById.get(categoryId)?.icon"
                          :icon="categoriesMapById.get(categoryId)?.icon || 'tabler-category'"
                          size="16"
                          class="me-1"
                        />
                        {{ categoriesMapById.get(categoryId)?.name || 'Unknown' }}
                      </VChip>
                    </div>
                  </div>
                </div>

                <!-- Add Tool/Component Button fixed at bottom -->
                <div class="tool-detail-footer pt-0 d-flex justify-end">
                  <VBtn
                    color="primary"
                    size="large"
                    height="52"
                    class="px-8"
                    @click="confirmSelection(selectedToolForDetail)"
                  >
                    <VIcon icon="tabler-plus" class="me-2" size="20" />
                    {{ getButtonText }}
                  </VBtn>
                </div>
              </div>
            </div>
          </div>
        </div>
      </VCardText>
    </VCard>
  </VDialog>
</template>

<style lang="scss" scoped>
// Mixin for consistent custom scrollbar styling
@mixin custom-scrollbar($thumb-opacity: 0.2) {
  &::-webkit-scrollbar {
    inline-size: 6px;
  }

  &::-webkit-scrollbar-track {
    background: transparent;
  }

  &::-webkit-scrollbar-thumb {
    border-radius: 3px;
    background: rgba(var(--v-theme-on-surface), $thumb-opacity);

    &:hover {
      background: rgba(var(--v-theme-on-surface), calc($thumb-opacity + 0.1));
    }
  }
}

// Carousel container (viewport)
.modal-content-container {
  width: 100%;
  height: 70vh;
  max-height: 700px;
  overflow: hidden;
  position: relative;
}

// Carousel wrapper containing 3 panels
// Math: Show 2 panels at a time (each 50% of viewport), with 3 panels total
// Wrapper width: 3 panels / 2 visible × 100% = 150% of viewport
// Panel width: 100% / 3 panels × 2 visible = 33.333% of wrapper = 50% of viewport
.carousel-wrapper {
  display: flex;
  width: 150%;
  height: 100%;
  transition: transform 0.5s cubic-bezier(0.4, 0, 0.2, 1);
  transform: translateX(0);

  &.show-detail {
    transform: translateX(-33.333%);
  }
}

// Individual carousel panels
.carousel-panel {
  width: 33.333%;
  flex-shrink: 0;
  overflow-y: auto;
  height: 100%;
  box-sizing: border-box;

  &:nth-child(1) {
    border-right: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  }

  &:nth-child(2) {
    border-right: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  }

  &:nth-child(3) {
    background-color: rgba(var(--v-theme-on-surface), 0.01);
  }

  @include custom-scrollbar(0.2);
}

.tool-detail-scroll-content {
  overflow-y: auto;
  width: 100%;
  @include custom-scrollbar(0.1);
}

.tool-detail-footer {
  width: 100%;
}

// List items (used for both categories and tools)
.modal-list-item {
  position: relative;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 16px !important;
  cursor: pointer;
  transition: all 0.2s ease;
  min-height: 60px !important;
  align-items: flex-start !important;

  :deep(.v-list-item__prepend) {
    align-self: flex-start;
  }

  :deep(.v-list-item__content) {
    flex: 1;
  }

  &:hover {
    border-color: rgb(var(--v-theme-primary));
    background-color: rgba(var(--v-theme-primary), 0.05);
  }

  &.selected-category,
  &.selected-tool {
    border-color: rgb(var(--v-theme-primary));
    background-color: rgba(var(--v-theme-primary), 0.08);

    &::after {
      content: '';
      position: absolute;
      left: -1px;
      top: 20%;
      bottom: 20%;
      width: 3px;
      background-color: rgb(var(--v-theme-primary));
      border-radius: 0 4px 4px 0;
    }
  }
}

.modal-item-description {
  display: -webkit-box;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  line-height: 1;
  min-block-size: 2em;
  text-overflow: ellipsis;
}

.detail-section-label {
  font-size: 0.875rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: rgba(var(--v-theme-on-surface), 0.7);
}

.detail-description-text {
  line-height: 1.7;
  color: rgba(var(--v-theme-on-surface), 0.87);
}

.release-stage-chip {
  font-size: 0.65rem !important;
  font-weight: 600 !important;
  height: 18px !important;
  padding: 0 6px !important;
}
</style>
