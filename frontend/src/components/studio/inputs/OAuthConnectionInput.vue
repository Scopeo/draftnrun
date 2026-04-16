<script setup lang="ts">
import { Icon } from '@iconify/vue'
import { computed, ref, watch } from 'vue'
import { VAlert } from 'vuetify/components/VAlert'
import { VBtn } from 'vuetify/components/VBtn'
import { VCard, VCardActions, VCardText, VCardTitle } from 'vuetify/components/VCard'
import { VChip } from 'vuetify/components/VChip'
import { VDialog } from 'vuetify/components/VDialog'
import { VDivider } from 'vuetify/components/VDivider'
import { VProgressCircular } from 'vuetify/components/VProgressCircular'
import { VSpacer } from 'vuetify/components/VGrid'
import { VSelect } from 'vuetify/components/VSelect'
import {
  type VariableDefinition,
  useOrgVariableDefinitionsQuery,
} from '@/composables/queries/useVariableDefinitionsQuery'
import { useOAuthFlow } from '@/composables/useOAuthFlow'
import { useSelectedOrg } from '@/composables/useSelectedOrg'

interface Props {
  modelValue: string | null
  provider: string
  icon?: string
  label?: string
  description?: string
  readonly?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  icon: 'mdi-connection',
  label: 'OAuth Connection',
  description: 'Connect your account to continue',
  readonly: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: string | null]
}>()

// Composables
const { selectedOrgId } = useSelectedOrg()

// Query oauth definitions filtered by provider
const { data: oauthDefinitions, isLoading: isLoadingDefinitions } = useOrgVariableDefinitionsQuery(selectedOrgId, {
  type: 'oauth',
})

// Filter by provider_config_key in metadata
const providerDefinitions = computed(() =>
  (oauthDefinitions.value ?? []).filter(
    (d: VariableDefinition) => (d.metadata as Record<string, unknown>)?.provider_config_key === props.provider
  )
)

// OAuth flow composable
const {
  state: oauthState,
  errorMessage,
  startOAuthFlow,
  confirmConnection,
  cancelFlow,
} = useOAuthFlow(() => selectedOrgId.value)

// Computed
const providerDisplayName = computed(() => props.provider.charAt(0).toUpperCase() + props.provider.slice(1))

const hasDefinitions = computed(() => providerDefinitions.value.length > 0)

const selectedDefinition = computed(() => {
  if (!props.modelValue) return null
  return providerDefinitions.value.find((d: VariableDefinition) => d.id === props.modelValue) ?? null
})

// Dropdown items: definition names + "Create new" option
const definitionItems = computed(() => {
  const items = providerDefinitions.value.map((d: VariableDefinition) => ({
    title: d.name,
    value: d.id,
    subtitle: d.description || undefined,
  }))

  items.push({
    title: '+ Create new connection',
    value: '__create_new__',
    subtitle: undefined,
  })

  return items
})

const showDialog = computed(() => ['waiting_oauth', 'error'].includes(oauthState.value))
const isConfirming = ref(false)

// Auto-select if only one definition exists and no selection yet
watch(
  [providerDefinitions, isLoadingDefinitions],
  ([defs, loading]) => {
    const firstDefinitionId = defs?.[0]?.id
    if (!loading && defs && defs.length === 1 && !props.modelValue && firstDefinitionId) {
      emit('update:modelValue', firstDefinitionId)
    }
  },
  { immediate: true }
)

// Methods
const handleSelection = (value: string) => {
  if (value === '__create_new__') {
    startOAuthFlow(props.provider)
  } else {
    emit('update:modelValue', value)
  }
}

const handleConfirmClick = async () => {
  isConfirming.value = true
  try {
    const response = await confirmConnection(props.provider)
    if (response?.definition_id) {
      emit('update:modelValue', response.definition_id)
    }
  } finally {
    isConfirming.value = false
  }
}

const disconnect = () => {
  emit('update:modelValue', null)
}
</script>

<template>
  <div class="oauth-connection-input">
    <!-- Loading State -->
    <VCard v-if="isLoadingDefinitions" variant="outlined" class="pa-4">
      <div class="d-flex align-center">
        <VProgressCircular indeterminate size="24" width="2" class="me-3" />
        <div>
          <div class="text-subtitle-2">{{ label }}</div>
          <div class="text-caption text-medium-emphasis">Loading connections...</div>
        </div>
      </div>
    </VCard>

    <!-- Has definitions: show dropdown -->
    <VCard v-else-if="hasDefinitions" variant="outlined" class="pa-4">
      <div class="d-flex align-center justify-space-between">
        <div class="d-flex align-center flex-grow-1 me-4">
          <Icon :icon="icon" class="me-3" width="24" height="24" />
          <div class="flex-grow-1">
            <div class="text-subtitle-2">{{ label }}</div>
            <VSelect
              :model-value="modelValue"
              :items="definitionItems"
              item-title="title"
              item-value="value"
              placeholder="Select a connection"
              variant="outlined"
              density="compact"
              hide-details
              class="mt-2"
              :disabled="readonly"
              @update:model-value="handleSelection"
            >
              <template #selection>
                <span>{{ selectedDefinition?.name || modelValue || 'Select...' }}</span>
              </template>
            </VSelect>
            <div v-if="selectedDefinition" class="text-caption text-medium-emphasis mt-1">
              <VChip size="x-small" color="success" variant="tonal" class="me-1">
                <Icon icon="mdi-check-circle" class="me-1" width="12" height="12" />
                Active
              </VChip>
              {{ selectedDefinition.description }}
            </div>
          </div>
        </div>
        <div v-if="selectedDefinition && !readonly">
          <VBtn color="error" variant="text" size="small" @click="disconnect"> Clear </VBtn>
        </div>
      </div>
    </VCard>

    <!-- No definitions: show connect button -->
    <VCard v-else variant="outlined" class="pa-4">
      <div class="d-flex align-center justify-space-between">
        <div class="d-flex align-center">
          <Icon :icon="icon" class="me-3" width="24" height="24" />
          <div>
            <div class="text-subtitle-2">{{ label }}</div>
            <div class="text-caption text-medium-emphasis">{{ description }}</div>
          </div>
        </div>
        <div>
          <VBtn
            :disabled="readonly"
            color="primary"
            variant="tonal"
            size="small"
            prepend-icon="mdi-link-plus"
            :loading="oauthState === 'authorizing'"
            @click="startOAuthFlow(provider)"
          >
            Connect {{ providerDisplayName }}
          </VBtn>
        </div>
      </div>
    </VCard>

    <!-- OAuth Dialog -->
    <VDialog v-model="showDialog" max-width="var(--dnr-dialog-sm)" persistent>
      <VCard>
        <!-- Waiting for OAuth -->
        <template v-if="oauthState === 'waiting_oauth'">
          <VCardTitle>
            <div class="d-flex align-center">
              <Icon icon="mdi-clock-outline" class="me-2" width="24" height="24" />
              Waiting for Authorization
            </div>
          </VCardTitle>

          <VDivider />

          <VCardText class="pt-6">
            <VAlert type="info" variant="tonal" density="compact" class="mb-4">
              Complete the authorization in the opened browser tab, then click "I've authorized, continue" below.
            </VAlert>

            <div class="text-center py-4">
              <Icon icon="mdi-open-in-new" width="48" height="48" class="text-medium-emphasis mb-3" />
              <div class="text-body-2 text-medium-emphasis">Authorization window opened</div>
            </div>
          </VCardText>

          <VDivider />

          <VCardActions class="pa-4">
            <VSpacer />
            <VBtn variant="text" @click="cancelFlow">Cancel</VBtn>
            <VBtn color="primary" :loading="isConfirming" @click="handleConfirmClick">I've authorized, continue</VBtn>
          </VCardActions>
        </template>

        <!-- Error -->
        <template v-else-if="oauthState === 'error'">
          <VCardTitle>
            <div class="d-flex align-center">
              <Icon icon="mdi-alert-circle" class="me-2" width="24" height="24" color="error" />
              Connection Failed
            </div>
          </VCardTitle>

          <VDivider />

          <VCardText class="pt-6">
            <VAlert type="error" variant="tonal" density="compact">
              {{ errorMessage }}
            </VAlert>
          </VCardText>

          <VDivider />

          <VCardActions class="pa-4">
            <VSpacer />
            <VBtn variant="text" @click="cancelFlow">Close</VBtn>
          </VCardActions>
        </template>
      </VCard>
    </VDialog>
  </div>
</template>

<style scoped lang="scss">
.oauth-connection-input {
  width: 100%;
}
</style>
