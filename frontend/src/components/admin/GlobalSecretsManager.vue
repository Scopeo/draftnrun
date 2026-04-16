<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { format } from 'date-fns'
import GenericConfirmDialog from '@/components/dialogs/GenericConfirmDialog.vue'
import { settingsSecretsApi } from '@/api'

interface Props {
  successMessage: string
  errorMessage: string
}

const emit = defineEmits<{
  'update:successMessage': [value: string]
  'update:errorMessage': [value: string]
}>()

const items = ref<{ key: string; created_at?: string; updated_at?: string; is_set: boolean }[]>([])
const isLoading = ref(false)
const upsertDialog = ref(false)
const isSaving = ref(false)
const form = reactive<{ key: string; secret: string }>({ key: '', secret: '' })
const showDeleteDialog = ref(false)
const keyToDelete = ref<string | null>(null)

async function load() {
  try {
    isLoading.value = true
    items.value = await settingsSecretsApi.list()
  } catch (e: any) {
    emit('update:errorMessage', e?.message || 'Failed to load global secrets')
  } finally {
    isLoading.value = false
  }
}

function openCreate() {
  form.key = ''
  form.secret = ''
  upsertDialog.value = true
}

function openUpdate(key: string) {
  form.key = key
  form.secret = ''
  upsertDialog.value = true
}

async function submit() {
  try {
    isSaving.value = true
    await settingsSecretsApi.upsert({ key: form.key, secret: form.secret })
    upsertDialog.value = false
    emit('update:successMessage', 'Secret saved')
    setTimeout(() => emit('update:successMessage', ''), 3000)
    await load()
  } catch (e: any) {
    emit('update:errorMessage', e?.message || 'Failed to save secret')
  } finally {
    isSaving.value = false
  }
}

function requestRemoveKey(key: string) {
  keyToDelete.value = key
  showDeleteDialog.value = true
}

function cancelRemoveKey() {
  showDeleteDialog.value = false
  keyToDelete.value = null
}

async function confirmRemoveKey() {
  if (!keyToDelete.value) return

  const key = keyToDelete.value
  try {
    await settingsSecretsApi.delete(key)
    emit('update:successMessage', 'Secret deleted')
    setTimeout(() => emit('update:successMessage', ''), 3000)
    await load()
  } catch (e: any) {
    emit('update:errorMessage', e?.message || 'Failed to delete secret')
  } finally {
    cancelRemoveKey()
  }
}

onMounted(load)
</script>

<template>
  <VCard>
    <VCardTitle class="d-flex align-center justify-space-between">
      <span>Global Secrets</span>
      <VBtn color="primary" @click="openCreate">
        <VIcon icon="tabler-plus" class="me-2" />
        Add Secret
      </VBtn>
    </VCardTitle>
    <VDivider />
    <VCardText>
      <VDataTable
        :items="items"
        :loading="isLoading"
        item-value="key"
        :headers="[
          { title: 'Key', key: 'key' },
          { title: 'Updated', key: 'updated_at' },
          { title: 'Status', key: 'is_set' },
          { title: 'Actions', key: 'actions', sortable: false },
        ]"
      >
        <template #item.key="{ item }">
          <code>{{ item.key }}</code>
        </template>
        <template #item.updated_at="{ item }">
          {{ item.updated_at ? format(new Date(item.updated_at), 'MMM dd, yyyy HH:mm') : '—' }}
        </template>
        <template #item.is_set="{ item }">
          <VChip :color="item.is_set ? 'success' : 'default'" size="small">{{ item.is_set ? 'Set' : 'Not set' }}</VChip>
        </template>
        <template #item.actions="{ item }">
          <VBtn size="small" variant="text" @click="openUpdate(item.key)">Update</VBtn>
          <VBtn size="small" variant="text" color="error" @click="requestRemoveKey(item.key)">Delete</VBtn>
        </template>
        <template #no-data>
          <EmptyState size="sm" icon="tabler-lock" title="No global secrets found" />
        </template>
      </VDataTable>
    </VCardText>
  </VCard>

  <VDialog v-model="upsertDialog" max-width="var(--dnr-dialog-sm)">
    <VCard>
      <VCardTitle>Upsert Global Secret</VCardTitle>
      <VDivider />
      <VCardText>
        <div class="d-flex flex-column gap-4">
          <VTextField v-model="form.key" label="Key" placeholder="BLABLA_API_KEY" />
          <VTextField v-model="form.secret" type="password" label="Secret" placeholder="••••••" />
        </div>
      </VCardText>
      <VCardActions>
        <VSpacer />
        <VBtn variant="text" @click="upsertDialog = false">Cancel</VBtn>
        <VBtn color="primary" :loading="isSaving" @click="submit">Save</VBtn>
      </VCardActions>
    </VCard>
  </VDialog>

  <GenericConfirmDialog
    v-model:is-dialog-visible="showDeleteDialog"
    title="Delete Global Secret"
    :message="
      keyToDelete ? `Are you sure you want to delete global secret '${keyToDelete}'? This action cannot be undone.` : ''
    "
    confirm-text="Delete"
    cancel-text="Cancel"
    confirm-color="error"
    @confirm="confirmRemoveKey"
    @cancel="cancelRemoveKey"
  />
</template>
