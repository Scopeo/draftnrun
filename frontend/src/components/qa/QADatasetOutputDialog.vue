<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { logger } from '@/utils/logger'

interface JsonObject {
  [key: string]: JsonValue
}

interface JsonArray extends Array<JsonValue> {}

type JsonValue = string | number | boolean | null | JsonObject | JsonArray

// Props & Emits
interface Props {
  modelValue: boolean
  outputText: string
  expectedOutput: string
}

const props = defineProps<Props>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  'update:expectedOutput': [value: string]
}>()

const expectedCopied = ref(false)
const actualCopied = ref(false)
const isEditing = ref(false)
const editValue = ref('')

watch(
  () => props.modelValue,
  open => {
    if (open) {
      isEditing.value = false
      editValue.value = props.expectedOutput || ''
    }
  }
)

const tryParseJson = (text: string): JsonValue | null => {
  if (!text) return null
  try {
    return JSON.parse(text)
  } catch (error: unknown) {
    return null
  }
}

const parsedExpected = computed(() => tryParseJson(props.expectedOutput))
const parsedActual = computed(() => tryParseJson(props.outputText))
const bothAreJson = computed(() => parsedExpected.value !== null && parsedActual.value !== null)

const formattedExpected = computed(() =>
  parsedExpected.value !== null ? JSON.stringify(parsedExpected.value, null, 2) : props.expectedOutput
)

const formattedActual = computed(() =>
  parsedActual.value !== null ? JSON.stringify(parsedActual.value, null, 2) : props.outputText
)

// --- JSON diff rendering with inline styles ---
const escapeHtml = (str: string): string => {
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}

const deepEqual = (a: unknown, b: unknown): boolean => {
  return JSON.stringify(a) === JSON.stringify(b)
}

const renderPrimitive = (val: JsonValue): string => {
  if (val === null) return 'null'
  if (typeof val === 'string') return `"${escapeHtml(val)}"`
  return String(val)
}

const S_MATCH = 'background-color:rgba(var(--v-theme-success),0.15);border-radius:2px;padding:1px 2px'
const S_MISMATCH = 'background-color:rgba(var(--v-theme-warning),0.2);border-radius:2px;padding:1px 2px'
const S_KEY_MISSING = S_MISMATCH

const wrap = (style: string, content: string) => `<span style="${style}">${content}</span>`

const buildDiffHtml = (value: JsonValue, reference: JsonValue | undefined, indent: number): string => {
  const pad = '  '.repeat(indent)
  const innerPad = '  '.repeat(indent + 1)

  if (value === null || typeof value !== 'object') {
    return renderPrimitive(value)
  }

  if (Array.isArray(value)) {
    if (value.length === 0) return '[]'
    const refArr = Array.isArray(reference) ? reference : undefined

    const items = value.map((item, i) => {
      const hasRef = refArr !== undefined && i < refArr.length
      const refItem = hasRef ? refArr![i] : undefined
      const matched = hasRef && deepEqual(item, refItem)
      let itemHtml: string

      if (typeof item === 'object' && item !== null) {
        const serialized = escapeHtml(JSON.stringify(item, null, 2).replace(/\n/g, `\n${innerPad}`))

        itemHtml = matched ? wrap(S_MATCH, serialized) : wrap(S_MISMATCH, serialized)
      } else {
        const str = renderPrimitive(item)

        itemHtml = matched ? wrap(S_MATCH, str) : wrap(S_MISMATCH, str)
      }

      const comma = i < value.length - 1 ? ',' : ''

      return `${innerPad}${itemHtml}${comma}`
    })

    return `[\n${items.join('\n')}\n${pad}]`
  }

  const keys = Object.keys(value)
  if (keys.length === 0) return '{}'

  const refObj =
    typeof reference === 'object' && reference !== null && !Array.isArray(reference)
      ? (reference as Record<string, JsonValue>)
      : undefined

  const lines = keys.map((key, i) => {
    const comma = i < keys.length - 1 ? ',' : ''
    const keyInRef = refObj !== undefined && key in refObj

    const childValue = value[key]

    if (typeof childValue === 'object' && childValue !== null) {
      const keySpan = keyInRef ? wrap(S_MATCH, `"${escapeHtml(key)}"`) : wrap(S_KEY_MISSING, `"${escapeHtml(key)}"`)

      let childHtml: string
      if (!keyInRef) {
        childHtml = escapeHtml(JSON.stringify(childValue, null, 2).replace(/\n/g, `\n${innerPad}`))
      } else if (Array.isArray(childValue)) {
        childHtml = buildDiffHtml(childValue, refObj![key], indent + 1)
      } else if (deepEqual(childValue, refObj![key])) {
        childHtml = wrap(S_MATCH, escapeHtml(JSON.stringify(childValue, null, 2).replace(/\n/g, `\n${innerPad}`)))
      } else {
        childHtml = buildDiffHtml(childValue, refObj![key], indent + 1)
      }

      return `${innerPad}${keySpan}: ${childHtml}${comma}`
    }

    const primStr = renderPrimitive(childValue)
    let keyStyle: string
    let valStyle: string
    if (!keyInRef) {
      keyStyle = S_KEY_MISSING
      valStyle = ''
    } else if (deepEqual(childValue, refObj![key])) {
      keyStyle = S_MATCH
      valStyle = S_MATCH
    } else {
      keyStyle = S_MATCH
      valStyle = S_MISMATCH
    }

    const keySpan = wrap(keyStyle, `"${escapeHtml(key)}"`)
    const valSpan = valStyle ? wrap(valStyle, primStr) : primStr
    return `${innerPad}${keySpan}: ${valSpan}${comma}`
  })

  return `{\n${lines.join('\n')}\n${pad}}`
}

const expectedDiffHtml = computed(() => {
  if (!bothAreJson.value) return ''
  return buildDiffHtml(parsedExpected.value!, parsedActual.value!, 0)
})

const actualDiffHtml = computed(() => {
  if (!bothAreJson.value) return ''
  return buildDiffHtml(parsedActual.value!, parsedExpected.value!, 0)
})

const copyExpected = async () => {
  try {
    await navigator.clipboard.writeText(formattedExpected.value)
    expectedCopied.value = true
    setTimeout(() => {
      expectedCopied.value = false
    }, 2000)
  } catch (err) {
    logger.error('Failed to copy text', { error: err })
  }
}

const copyActual = async () => {
  try {
    await navigator.clipboard.writeText(formattedActual.value)
    actualCopied.value = true
    setTimeout(() => {
      actualCopied.value = false
    }, 2000)
  } catch (err) {
    logger.error('Failed to copy text', { error: err })
  }
}

const startEditing = () => {
  editValue.value = props.expectedOutput || ''
  isEditing.value = true
}

const cancelEditing = () => {
  isEditing.value = false
  editValue.value = props.expectedOutput || ''
}

const saveExpectedOutput = () => {
  emit('update:expectedOutput', editValue.value)
  isEditing.value = false
}

const close = () => {
  isEditing.value = false
  emit('update:modelValue', false)
}
</script>

<template>
  <VDialog
    :model-value="modelValue"
    max-width="90vw"
    @update:model-value="emit('update:modelValue', $event)"
    @click:outside="close"
    @keydown.esc="close"
  >
    <VCard style="max-block-size: 90vh">
      <VCardTitle class="d-flex align-center">
        <VIcon icon="tabler-columns" class="me-2" />
        Output Comparison
      </VCardTitle>
      <VDivider />
      <VCardText class="output-scroll-area">
        <VRow no-gutters class="align-stretch">
          <!-- Expected Output -->
          <VCol cols="12" md="6" class="pe-md-2 pb-4 pb-md-0">
            <div class="output-panel">
              <div class="output-panel__header">
                <span class="text-subtitle-2 font-weight-medium">Expected Output</span>
                <div class="d-flex align-center gap-1">
                  <template v-if="isEditing">
                    <VBtn
                      icon
                      variant="text"
                      size="x-small"
                      density="compact"
                      color="success"
                      @click="saveExpectedOutput"
                    >
                      <VIcon icon="tabler-check" size="16" />
                      <VTooltip activator="parent">Save</VTooltip>
                    </VBtn>
                    <VBtn icon variant="text" size="x-small" density="compact" @click="cancelEditing">
                      <VIcon icon="tabler-x" size="16" />
                      <VTooltip activator="parent">Cancel</VTooltip>
                    </VBtn>
                  </template>
                  <template v-else>
                    <VBtn icon variant="text" size="x-small" density="compact" @click="startEditing">
                      <VIcon icon="tabler-edit" size="16" />
                      <VTooltip activator="parent">Edit</VTooltip>
                    </VBtn>
                    <VBtn
                      v-if="expectedOutput"
                      icon
                      variant="text"
                      size="x-small"
                      density="compact"
                      @click="copyExpected"
                    >
                      <VIcon :icon="expectedCopied ? 'tabler-check' : 'tabler-copy'" size="16" />
                      <VTooltip activator="parent">{{ expectedCopied ? 'Copied!' : 'Copy' }}</VTooltip>
                    </VBtn>
                  </template>
                </div>
              </div>
              <div class="output-panel__content">
                <VTextarea
                  v-if="isEditing"
                  v-model="editValue"
                  variant="outlined"
                  auto-grow
                  hide-details
                  class="expected-editor"
                />
                <!-- eslint-disable-next-line vue/no-v-html -->
                <pre v-else-if="bothAreJson && expectedOutput" v-html="expectedDiffHtml" />
                <pre v-else-if="expectedOutput">{{ formattedExpected }}</pre>
                <span v-else class="text-disabled text-body-2">No expected output</span>
              </div>
            </div>
          </VCol>

          <!-- Actual Output -->
          <VCol cols="12" md="6" class="ps-md-2">
            <div class="output-panel">
              <div class="output-panel__header">
                <span class="text-subtitle-2 font-weight-medium">Actual Output</span>
                <VBtn v-if="outputText" icon variant="text" size="x-small" density="compact" @click="copyActual">
                  <VIcon :icon="actualCopied ? 'tabler-check' : 'tabler-copy'" size="16" />
                  <VTooltip activator="parent">{{ actualCopied ? 'Copied!' : 'Copy' }}</VTooltip>
                </VBtn>
              </div>
              <div class="output-panel__content">
                <!-- eslint-disable-next-line vue/no-v-html -->
                <!-- eslint-disable-next-line vue/no-v-html -->
                <pre v-if="bothAreJson && outputText" v-html="actualDiffHtml" />
                <pre v-else-if="outputText">{{ formattedActual }}</pre>
                <span v-else class="text-disabled text-body-2">No actual output</span>
              </div>
            </div>
          </VCol>
        </VRow>
      </VCardText>
      <VCardActions>
        <VSpacer />
        <VBtn variant="text" @click="close"> Close </VBtn>
      </VCardActions>
    </VCard>
  </VDialog>
</template>

<style lang="scss" scoped>
$font-mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace;

.output-scroll-area {
  overflow: auto;
  max-block-size: 82vh;
}

.align-stretch {
  align-items: stretch;
}

.output-panel {
  display: flex;
  flex-direction: column;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 8px;
  block-size: 100%;

  &__header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    border-block-end: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
    background: rgba(var(--v-theme-surface-variant), 0.3);
    border-start-end-radius: 8px;
    border-start-start-radius: 8px;
    padding-block: 8px;
    padding-inline: 12px;
  }

  &__content {
    padding: 12px;

    pre {
      margin: 0;
      font-family: $font-mono;
      font-size: 0.85rem;
      line-height: 1.5;
      white-space: pre-wrap;
      word-break: break-word;
    }
  }
}

.expected-editor {
  font-family: $font-mono;
  font-size: 0.85rem;

  :deep(.v-field__input) {
    line-height: 1.5;
  }
}
</style>
