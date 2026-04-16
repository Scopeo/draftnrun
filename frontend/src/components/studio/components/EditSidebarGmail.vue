<script setup lang="ts">
import GenericConfirmDialog from '@/components/dialogs/GenericConfirmDialog.vue'

interface Props {
  isIntegrationConnected: boolean
  isReadOnlyMode: boolean
  isWorker: boolean
  gmailConnecting: boolean
}

defineProps<Props>()

const emit = defineEmits<{
  'connect-gmail': []
  'disconnect-gmail': []
  'cancel-disconnect': []
}>()

const showGmailConnectDialog = defineModel<boolean>('showGmailConnectDialog', { default: false })
const showGmailDisconnectDialog = defineModel<boolean>('showGmailDisconnectDialog', { default: false })
</script>

<template>
  <div class="mt-6">
    <div class="text-h6 mb-4">Integration</div>
    <VCard variant="outlined" class="pa-4">
      <div class="d-flex align-center justify-space-between">
        <div>
          <div class="text-subtitle-1 d-flex align-center">
            <VIcon icon="tabler-mail" class="me-2" />
            Gmail Integration
          </div>
          <div class="text-caption text-medium-emphasis">
            {{
              isIntegrationConnected
                ? 'Connected and ready to save email drafts'
                : 'Connect your Gmail account to save email drafts'
            }}
          </div>
        </div>
        <div>
          <VChip v-if="isIntegrationConnected" color="success" size="small" variant="tonal" class="me-2">
            Connected
          </VChip>
          <VBtn
            v-if="!isIntegrationConnected && !isReadOnlyMode"
            :color="isWorker ? 'secondary' : 'primary'"
            variant="outlined"
            size="small"
            @click="showGmailConnectDialog = true"
          >
            Connect Gmail
          </VBtn>
          <VBtn
            v-else-if="isIntegrationConnected && !isReadOnlyMode"
            color="error"
            variant="outlined"
            size="small"
            @click="showGmailDisconnectDialog = true"
          >
            Disconnect
          </VBtn>
        </div>
      </div>
    </VCard>
  </div>

  <!-- Gmail Connection Dialog -->
  <VDialog v-model="showGmailConnectDialog" max-width="var(--dnr-dialog-sm)" persistent>
    <VCard>
      <VCardItem>
        <VCardTitle class="d-flex align-center">
          <VIcon icon="tabler-mail" class="me-2" />
          Connect Gmail
        </VCardTitle>
      </VCardItem>
      <VDivider />

      <VCardText class="pa-6">
        <div class="text-body-1 mb-4">Connect your Gmail account to save email drafts through this component.</div>
        <div class="text-body-2 text-medium-emphasis mb-4">
          We'll request permission to compose and save drafts in your Gmail account. Your credentials will be securely
          stored and encrypted.
        </div>
        <VAlert type="info" variant="tonal" class="mb-4">
          <div class="text-caption">
            <strong>Permissions requested:</strong><br />
            • Compose emails<br />
            • Save drafts<br />
            • Modify Gmail data
          </div>
        </VAlert>
      </VCardText>

      <VDivider />
      <VCardActions class="pa-6">
        <VSpacer />
        <VBtn variant="outlined" :disabled="gmailConnecting" @click="showGmailConnectDialog = false">Cancel</VBtn>
        <VBtn :color="isWorker ? 'secondary' : 'primary'" :loading="gmailConnecting" @click="emit('connect-gmail')">
          Connect Gmail
        </VBtn>
      </VCardActions>
    </VCard>
  </VDialog>

  <GenericConfirmDialog
    v-model:is-dialog-visible="showGmailDisconnectDialog"
    title="Disconnect Gmail Integration"
    message="Are you sure you want to disconnect Gmail integration for this component?"
    confirm-text="Disconnect"
    cancel-text="Cancel"
    confirm-color="error"
    @confirm="emit('disconnect-gmail')"
    @cancel="emit('cancel-disconnect')"
  />
</template>
