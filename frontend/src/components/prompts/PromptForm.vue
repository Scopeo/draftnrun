<script setup lang="ts">
import type { RouteLocationRaw } from 'vue-router'
import { computed } from 'vue'

const name = defineModel<string>('name', { required: true })
const content = defineModel<string>('content', { required: true })
const commitMessage = defineModel<string>('commitMessage', { required: true })

defineProps<{
  title: string
  subtitle: string
  backTo: RouteLocationRaw
  submitLabel: string
  isSubmitting: boolean
  formError: string | null
  nameReadonly?: boolean
}>()

const emit = defineEmits<{ submit: [] }>()

const isValid = computed(() => name.value.trim().length > 0 && content.value.trim().length > 0)
</script>

<template>
  <div class="prompt-form">
    <div class="prompt-form__header">
      <div class="d-flex align-center gap-3">
        <VBtn icon variant="text" size="small" :to="backTo">
          <VIcon icon="tabler-arrow-left" />
        </VBtn>
        <h2 class="text-h5">{{ title }}</h2>
      </div>
      <p class="text-body-2 text-medium-emphasis mt-1 ms-11">{{ subtitle }}</p>
    </div>

    <VDivider class="my-5" />

    <div class="prompt-form__body">
      <div class="prompt-form__section">
        <h3 class="text-subtitle-1 font-weight-medium mb-1">Name</h3>
        <p class="text-body-2 text-medium-emphasis mb-3">A short, descriptive name for this prompt.</p>
        <VTextField
          v-model="name"
          variant="outlined"
          density="comfortable"
          placeholder="e.g. Customer Support Agent"
          autofocus
          :readonly="nameReadonly"
          :error-messages="formError ? [formError] : []"
        />
      </div>

      <div class="prompt-form__section">
        <h3 class="text-subtitle-1 font-weight-medium mb-1">Prompt</h3>
        <p class="text-body-2 text-medium-emphasis mb-3">Define your prompt template.</p>
        <VTextarea
          v-model="content"
          class="prompt-form__textarea"
          variant="outlined"
          density="comfortable"
          rows="12"
          auto-grow
          placeholder="Write your prompt here..."
          spellcheck="false"
        />
      </div>

      <div class="prompt-form__section mb-0">
        <h3 class="text-subtitle-1 font-weight-medium mb-1">Commit message</h3>
        <p class="text-body-2 text-medium-emphasis mb-3">
          Provide information about the changes made in this version. Helps maintain a clear history of prompt iterations.
        </p>
        <VTextarea
          v-model="commitMessage"
          variant="outlined"
          density="comfortable"
          rows="3"
          placeholder="Add commit message..."
        />
      </div>
    </div>

    <div class="d-flex justify-end gap-3 py-6">
      <VBtn variant="text" :to="backTo">Cancel</VBtn>
      <VBtn color="primary" :disabled="!isValid" :loading="isSubmitting" @click="emit('submit')">
        {{ submitLabel }}
      </VBtn>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.prompt-form {
  width: 100%;

  &__header {
    padding-block-end: 0;
  }

  &__body {
    background: rgb(var(--v-theme-surface));
    border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
    border-radius: 12px;
    padding: 32px;
  }

  &__section {
    margin-block-end: 28px;
  }

  &__textarea :deep(textarea) {
    font-family: 'DM Mono', 'Fira Code', monospace;
    font-size: 0.875rem;
    line-height: 1.7;
  }
}
</style>
