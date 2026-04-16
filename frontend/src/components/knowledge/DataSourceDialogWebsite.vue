<script setup lang="ts">
import { Icon } from '@iconify/vue'
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { logger } from '@/utils/logger'
import { useCreateIngestionTaskMutation } from '@/composables/queries/useDataSourcesQuery'
import { getErrorMessage } from '@/composables/useDataSources'
import { useNotifications } from '@/composables/useNotifications'
import { useTracking } from '@/composables/useTracking'

const props = defineProps<{
  modelValue: boolean
  orgId: string | undefined
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  created: []
}>()

const { notify } = useNotifications()
const { trackButtonClick, trackModalOpen, trackModalClose } = useTracking()
const createIngestionTaskMutation = useCreateIngestionTaskMutation()

const isConnecting = ref(false)
const showAdvancedOptions = ref(false)

const form = ref({
  source_name: '',
  url: '',
  follow_links: true,
  max_depth: 3,
  limit: 100,
  include_paths: [] as string[],
  exclude_paths: [] as string[],
  include_tags: [] as string[],
  exclude_tags: [] as string[],
})

const formErrors = ref<Record<string, string>>({})

const includePathInputs = ref<string[]>([''])
const excludePathInputs = ref<string[]>([''])
const includeTagInputs = ref<string[]>([''])
const excludeTagInputs = ref<string[]>([''])
const includePathsComboboxRef = ref()
const excludePathsComboboxRef = ref()
const includeTagsComboboxRef = ref()
const excludeTagsComboboxRef = ref()

const spaceKeyCleanups: Array<() => void> = []

onBeforeUnmount(() => {
  spaceKeyCleanups.forEach(cleanup => cleanup())
  spaceKeyCleanups.length = 0
})

const attachSpaceKeyHandler = (
  comboboxRef: any,
  inputValuesRef: { value: string[] },
  formKey: 'include_paths' | 'exclude_paths' | 'include_tags' | 'exclude_tags'
) => {
  if (!comboboxRef) return
  const input = comboboxRef.$el?.querySelector('input')
  if (!input) return

  const handler = (e: KeyboardEvent) => {
    if (e.key === ' ' || e.key === 'Space') {
      e.preventDefault()
      e.stopPropagation()
      e.stopImmediatePropagation()

      const value = inputValuesRef.value[0]?.trim()
      if (value && !form.value[formKey].includes(value)) {
        form.value[formKey] = [...form.value[formKey], value]
        inputValuesRef.value[0] = ''
        input.value = ''
        input.dispatchEvent(new InputEvent('input', { bubbles: true, cancelable: true }))
        input.dispatchEvent(new Event('change', { bubbles: true }))
        input.blur()
        nextTick(() => input?.focus())
      }
    }
  }

  input.addEventListener('keydown', handler, true)
  spaceKeyCleanups.push(() => input.removeEventListener('keydown', handler, true))
}

const reset = () => {
  form.value = {
    source_name: '',
    url: '',
    follow_links: true,
    max_depth: 3,
    limit: 100,
    include_paths: [],
    exclude_paths: [],
    include_tags: [],
    exclude_tags: [],
  }
  formErrors.value = {}
  showAdvancedOptions.value = false
  includePathInputs.value = ['']
  excludePathInputs.value = ['']
  includeTagInputs.value = ['']
  excludeTagInputs.value = ['']
}

watch(
  () => props.modelValue,
  open => {
    if (open) {
      reset()
      trackModalOpen('website-ingestion-dialog', 'data-sources-header')
      nextTick(() => {
        attachSpaceKeyHandler(includePathsComboboxRef.value, includePathInputs, 'include_paths')
        attachSpaceKeyHandler(excludePathsComboboxRef.value, excludePathInputs, 'exclude_paths')
        attachSpaceKeyHandler(includeTagsComboboxRef.value, includeTagInputs, 'include_tags')
        attachSpaceKeyHandler(excludeTagsComboboxRef.value, excludeTagInputs, 'exclude_tags')
      })
    }
  }
)

const clearExcludePaths = () => {
  form.value.exclude_paths = []
  excludePathInputs.value = ['']
}

const clearIncludePaths = () => {
  form.value.include_paths = []
  includePathInputs.value = ['']
}

const clearExcludeTags = () => {
  form.value.exclude_tags = []
  excludeTagInputs.value = ['']
}

const clearIncludeTags = () => {
  form.value.include_tags = []
  includeTagInputs.value = ['']
}

const validate = () => {
  const errors: Record<string, string> = {}
  if (!form.value.source_name.trim()) errors.source_name = 'Source name is required'
  if (!form.value.url.trim()) {
    errors.url = 'URL is required'
  } else {
    try {
      new URL(form.value.url)
    } catch {
      errors.url = 'Please enter a valid URL'
    }
  }
  if (form.value.max_depth !== undefined && form.value.max_depth < 1) errors.max_depth = 'Max depth must be at least 1'
  if (form.value.max_depth !== undefined && form.value.max_depth > 10) errors.max_depth = 'Max depth must be at most 10'
  if (form.value.limit !== undefined && form.value.limit < 1) errors.limit = 'Limit must be at least 1'
  if (form.value.limit !== undefined && form.value.limit > 1000) errors.limit = 'Limit must be at most 1000'
  formErrors.value = errors
  return Object.keys(errors).length === 0
}

const close = () => {
  emit('update:modelValue', false)
  reset()
}

const submit = async () => {
  if (!validate() || !props.orgId) return
  try {
    isConnecting.value = true

    const attrs: any = { url: form.value.url.trim() }
    if (form.value.follow_links !== true) attrs.follow_links = form.value.follow_links
    if (form.value.follow_links) {
      attrs.max_depth = form.value.max_depth !== 3 ? form.value.max_depth : 3
      attrs.limit = form.value.limit !== 100 ? form.value.limit : 100
    }
    const filterNonEmpty = (arr: string[]) => arr.filter(s => s.trim())
    if (form.value.include_paths.length > 0) attrs.include_paths = filterNonEmpty(form.value.include_paths)
    if (form.value.exclude_paths.length > 0) attrs.exclude_paths = filterNonEmpty(form.value.exclude_paths)
    if (form.value.include_tags.length > 0) attrs.include_tags = filterNonEmpty(form.value.include_tags)
    if (form.value.exclude_tags.length > 0) attrs.exclude_tags = filterNonEmpty(form.value.exclude_tags)

    const payload = {
      source_name: form.value.source_name,
      source_type: 'website',
      status: 'pending',
      source_attributes: attrs,
    }

    await createIngestionTaskMutation.mutateAsync({ orgId: props.orgId, payload })
    trackButtonClick('website-source-created', 'website-form', {
      source_type: 'website',
      follow_links: form.value.follow_links,
      max_depth: form.value.max_depth,
      limit: form.value.limit,
    })
    emit('update:modelValue', false)
    trackModalClose('website-ingestion-dialog')
    reset()
    emit('created')
  } catch (error: unknown) {
    logger.error('Error connecting website', { error })
    notify.error(getErrorMessage(error, 'Failed to connect website. Please try again.'))
  } finally {
    isConnecting.value = false
  }
}
</script>

<template>
  <VDialog :model-value="modelValue" max-width="var(--dnr-dialog-md)" persistent @update:model-value="close">
    <VCard>
      <VCardTitle class="text-h6 pa-4 d-flex align-center">
        <VIcon icon="tabler-world" class="me-2" />
        Website Ingestion
      </VCardTitle>

      <VCardText class="pa-4 dnr-form-compact">
        <VForm @submit.prevent="submit">
          <VRow>
            <VCol cols="12">
              <VTextField
                v-model="form.source_name"
                label="Source Name *"
                placeholder="e.g. Company Website"
                :error-messages="formErrors.source_name"
              />
            </VCol>
            <VCol cols="12">
              <VTextField
                v-model="form.url"
                label="URL *"
                placeholder="https://example.com"
                :error-messages="formErrors.url"
                hint="Enter the URL of the website to scrape"
                persistent-hint
              />
            </VCol>
            <VCol cols="12">
              <div
                class="advanced-toggle-section mb-4"
                :class="{ 'advanced-toggle-expanded': showAdvancedOptions }"
                role="button"
                @click="showAdvancedOptions = !showAdvancedOptions"
              >
                <VIcon icon="tabler-settings" size="20" color="primary" class="me-2" />
                <span class="text-subtitle-1 font-weight-medium">Advanced Parameters</span>
                <VChip size="x-small" color="primary" variant="tonal" class="ms-2">Optional</VChip>
                <VSpacer />
                <VIcon icon="mdi-chevron-down" size="24" color="primary" :class="{ rotated: showAdvancedOptions }" />
              </div>

              <VExpandTransition>
                <div v-show="showAdvancedOptions" class="mt-2">
                  <VRow>
                    <VCol cols="12">
                      <div class="d-flex align-center path-label-wrapper">
                        <VSwitch v-model="form.follow_links" color="primary" hide-details inset />
                        <span class="ms-3 path-label-text">Follow links on the page</span>
                        <VTooltip location="top" open-on-hover>
                          <template #activator="{ props: tp }">
                            <span v-bind="tp" class="path-help-icon-wrapper">
                              <Icon icon="mdi:help-circle" :width="16" :height="16" style="color: #6b7280" />
                            </span>
                          </template>
                          <span>If enabled, the scraper will follow links found on the page</span>
                        </VTooltip>
                      </div>
                    </VCol>

                    <VCol v-if="form.follow_links" cols="12" md="6">
                      <div class="d-flex align-center mb-1 path-label-wrapper">
                        <span class="path-label-text">Maximum Depth</span>
                        <VTooltip location="top" open-on-hover>
                          <template #activator="{ props: tp }">
                            <span v-bind="tp" class="path-help-icon-wrapper">
                              <Icon icon="mdi:help-circle" :width="16" :height="16" style="color: #6b7280" />
                            </span>
                          </template>
                          <span>Maximum depth for link following (default: 3, max: 10)</span>
                        </VTooltip>
                      </div>
                      <VTextField
                        v-model.number="form.max_depth"
                        type="number"
                        placeholder="3"
                        min="1"
                        max="10"
                        :error-messages="formErrors.max_depth"
                      />
                    </VCol>

                    <VCol v-if="form.follow_links" cols="12" md="6">
                      <div class="d-flex align-center mb-1 path-label-wrapper">
                        <span class="path-label-text">Page Limit</span>
                        <VTooltip location="top" open-on-hover>
                          <template #activator="{ props: tp }">
                            <span v-bind="tp" class="path-help-icon-wrapper">
                              <Icon icon="mdi:help-circle" :width="16" :height="16" style="color: #6b7280" />
                            </span>
                          </template>
                          <span>Maximum number of pages to crawl (default: 100, max: 1000)</span>
                        </VTooltip>
                      </div>
                      <VTextField
                        v-model.number="form.limit"
                        type="number"
                        placeholder="100"
                        min="1"
                        max="1000"
                        :error-messages="formErrors.limit"
                      />
                    </VCol>

                    <VCol cols="12">
                      <div class="d-flex align-center mb-1 path-label-wrapper">
                        <Icon
                          icon="mdi:close-circle-outline"
                          class="me-2"
                          :width="18"
                          :height="18"
                          style="flex-shrink: 0; color: rgb(var(--v-theme-primary))"
                        />
                        <span class="path-label-text">Exclude paths</span>
                        <VTooltip location="top" open-on-hover>
                          <template #activator="{ props: tp }">
                            <span v-bind="tp" class="path-help-icon-wrapper">
                              <Icon icon="mdi:help-circle" :width="16" :height="16" style="color: #6b7280" />
                            </span>
                          </template>
                          <span>URL patterns to exclude from scraping (e.g. blog/.+ to exclude all blog pages)</span>
                        </VTooltip>
                        <VSpacer />
                        <VBtn
                          v-if="form.exclude_paths.length > 0 || excludePathInputs.some(p => p.trim())"
                          size="small"
                          variant="text"
                          color="error"
                          @click="clearExcludePaths"
                          >Clear</VBtn
                        >
                      </div>
                      <VCombobox
                        ref="excludePathsComboboxRef"
                        v-model="form.exclude_paths"
                        :search="excludePathInputs[0]"
                        placeholder="blog/.+(about/.+)"
                        variant="outlined"
                        chips
                        closable-chips
                        multiple
                        hide-selected
                        @update:search="
                          v => {
                            excludePathInputs[0] = v || ''
                          }
                        "
                        @keydown.enter.prevent.stop
                      />
                      <VCardText class="text-caption text-medium-emphasis pa-0 mt-1"
                        >Press Space to add the current pattern to the list</VCardText
                      >
                    </VCol>

                    <VCol cols="12">
                      <div class="d-flex align-center mb-1 path-label-wrapper">
                        <Icon
                          icon="mdi:check-circle-outline"
                          class="me-2"
                          :width="18"
                          :height="18"
                          style="flex-shrink: 0; color: rgb(var(--v-theme-primary))"
                        />
                        <span class="path-label-text">Include only paths</span>
                        <VTooltip location="top" open-on-hover>
                          <template #activator="{ props: tp }">
                            <span v-bind="tp" class="path-help-icon-wrapper">
                              <Icon icon="mdi:help-circle" :width="16" :height="16" style="color: #6b7280" />
                            </span>
                          </template>
                          <span
                            >Only scrape URLs matching these patterns (e.g. docs/.+ to only include documentation
                            pages)</span
                          >
                        </VTooltip>
                        <VSpacer />
                        <VBtn
                          v-if="form.include_paths.length > 0 || includePathInputs.some(p => p.trim())"
                          size="small"
                          variant="text"
                          color="error"
                          @click="clearIncludePaths"
                          >Clear</VBtn
                        >
                      </div>
                      <VCombobox
                        ref="includePathsComboboxRef"
                        v-model="form.include_paths"
                        :search="includePathInputs[0]"
                        placeholder="blog/.+(about/.+)"
                        variant="outlined"
                        chips
                        closable-chips
                        multiple
                        hide-selected
                        @update:search="
                          v => {
                            includePathInputs[0] = v || ''
                          }
                        "
                        @keydown.enter.prevent.stop
                      />
                      <VCardText class="text-caption text-medium-emphasis pa-0 mt-1"
                        >Press Space to add the current pattern to the list</VCardText
                      >
                    </VCol>

                    <VCol cols="12">
                      <div class="d-flex align-center mb-1 path-label-wrapper">
                        <Icon
                          icon="tabler:tags"
                          class="me-2"
                          :width="18"
                          :height="18"
                          style="flex-shrink: 0; color: rgb(var(--v-theme-primary))"
                        />
                        <span class="path-label-text">Exclude HTML tags</span>
                        <VTooltip location="top" open-on-hover>
                          <template #activator="{ props: tp }">
                            <span v-bind="tp" class="path-help-icon-wrapper">
                              <Icon icon="mdi:help-circle" :width="16" :height="16" style="color: #6b7280" />
                            </span>
                          </template>
                          <span>HTML tags to exclude from content extraction (e.g. nav, footer, script)</span>
                        </VTooltip>
                        <VSpacer />
                        <VBtn
                          v-if="form.exclude_tags.length > 0 || excludeTagInputs.some(t => t.trim())"
                          size="small"
                          variant="text"
                          color="error"
                          @click="clearExcludeTags"
                          >Clear</VBtn
                        >
                      </div>
                      <VCombobox
                        ref="excludeTagsComboboxRef"
                        v-model="form.exclude_tags"
                        :search="excludeTagInputs[0]"
                        placeholder="nav, footer, script..."
                        variant="outlined"
                        chips
                        closable-chips
                        multiple
                        hide-selected
                        @update:search="
                          v => {
                            excludeTagInputs[0] = v || ''
                          }
                        "
                        @keydown.enter.prevent.stop
                      />
                      <VCardText class="text-caption text-medium-emphasis pa-0 mt-1"
                        >Press Space to add the current tag to the list</VCardText
                      >
                    </VCol>

                    <VCol cols="12">
                      <div class="d-flex align-center mb-1 path-label-wrapper">
                        <Icon
                          icon="tabler:tags"
                          class="me-2"
                          :width="18"
                          :height="18"
                          style="flex-shrink: 0; color: rgb(var(--v-theme-primary))"
                        />
                        <span class="path-label-text">Include only HTML tags</span>
                        <VTooltip location="top" open-on-hover>
                          <template #activator="{ props: tp }">
                            <span v-bind="tp" class="path-help-icon-wrapper">
                              <Icon icon="mdi:help-circle" :width="16" :height="16" style="color: #6b7280" />
                            </span>
                          </template>
                          <span>Only extract content from these HTML tags (e.g. article, main, section)</span>
                        </VTooltip>
                        <VSpacer />
                        <VBtn
                          v-if="form.include_tags.length > 0 || includeTagInputs.some(t => t.trim())"
                          size="small"
                          variant="text"
                          color="error"
                          @click="clearIncludeTags"
                          >Clear</VBtn
                        >
                      </div>
                      <VCombobox
                        ref="includeTagsComboboxRef"
                        v-model="form.include_tags"
                        :search="includeTagInputs[0]"
                        placeholder="article, main, section..."
                        variant="outlined"
                        chips
                        closable-chips
                        multiple
                        hide-selected
                        @update:search="
                          v => {
                            includeTagInputs[0] = v || ''
                          }
                        "
                        @keydown.enter.prevent.stop
                      />
                      <VCardText class="text-caption text-medium-emphasis pa-0 mt-1"
                        >Press Space to add the current tag to the list</VCardText
                      >
                    </VCol>
                  </VRow>
                </div>
              </VExpandTransition>
            </VCol>
          </VRow>
        </VForm>
      </VCardText>

      <VCardActions class="pa-4">
        <VSpacer />
        <VBtn variant="tonal" @click="close">Cancel</VBtn>
        <VBtn color="primary" :loading="isConnecting" @click="submit">Ingest Website</VBtn>
      </VCardActions>
    </VCard>
  </VDialog>
</template>

<style lang="scss" scoped>
.advanced-toggle-section {
  display: flex;
  align-items: center;
  border: 1.5px dashed rgba(var(--v-theme-primary), 0.3);
  border-radius: 0.5rem;
  background-color: rgba(var(--v-theme-primary), 0.06);
  cursor: pointer;
  padding-block: 0.875rem;
  padding-inline: 1rem;
  transition: all 0.2s ease;
  user-select: none;

  &:hover {
    border-color: rgba(var(--v-theme-primary), 0.5);
    background-color: rgba(var(--v-theme-primary), 0.12);
    box-shadow: 0 2px 8px rgba(var(--v-theme-primary), 0.15);
    transform: translateY(-1px);
  }

  &.advanced-toggle-expanded {
    border-style: solid;
    border-color: rgba(var(--v-theme-primary), 0.4);
    background-color: rgba(var(--v-theme-primary), 0.1);
  }

  .rotated {
    transform: rotate(180deg);
  }

  .v-icon {
    transition: transform 0.2s ease;
  }
}

.path-label-wrapper {
  .path-label-text {
    color: rgba(var(--v-theme-on-background), var(--v-high-emphasis-opacity));
    font-size: 0.875rem;
    line-height: 1.5;
  }

  .path-help-icon-wrapper {
    display: inline-flex;
    align-items: center;
    cursor: help;
    margin-inline-start: 6px;
  }
}
</style>
