<script setup lang="ts">
import termsConditionsContent from '@/content/terms-conditions.md?raw'
import { parseMarkdown } from '@/utils/markdownParser'

const parsedContent = parseMarkdown(termsConditionsContent)

definePage({
  meta: {
    layout: 'blank',
    public: true,
  },
})
</script>

<template>
  <div class="terms-conditions-wrapper">
    <div class="text-center mb-8">
      <h1 class="text-h3 font-weight-bold mb-4">Terms & Conditions</h1>
    </div>

    <VContainer max-width="800">
      <VCard class="pa-8" elevation="0" variant="outlined">
        <div class="terms-content" v-html="parsedContent" />
      </VCard>

      <div class="text-center mt-8 mb-4">
        <VBtn to="/" color="primary" variant="outlined" size="large">
          <VIcon start icon="tabler-arrow-left" />
          Back to Home
        </VBtn>
      </div>
    </VContainer>
  </div>
</template>

<style lang="scss" scoped>
.terms-conditions-wrapper {
  position: relative;
  min-block-size: 100vh;
  padding-block: 2rem;
  padding-inline: 1rem;
}

:deep(.terms-content) {
  line-height: 1.7;

  h1,
  h2,
  h3 {
    color: rgb(var(--v-theme-on-surface));
  }

  p {
    color: rgb(var(--v-theme-on-surface));
  }

  ul {
    list-style-type: disc;
    padding-inline-start: 1.5rem;
  }

  li {
    margin-block-end: 0.5rem;
  }

  strong {
    color: rgb(var(--v-theme-primary));
    font-weight: 600;
  }

  hr {
    border: none;
    border-block-start: 1px solid rgb(var(--v-theme-outline));
    margin-block: 2rem;
    margin-inline: 0;
  }
}

@media (max-width: 600px) {
  .terms-conditions-wrapper {
    padding-block: 1rem;
    padding-inline: 0.5rem;
  }
}
</style>
