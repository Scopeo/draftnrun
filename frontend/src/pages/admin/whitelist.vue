<script setup lang="ts">
import { logger } from '@/utils/logger'
import { supabase } from '@/services/auth'
import GenericConfirmDialog from '@/components/dialogs/GenericConfirmDialog.vue'

const whitelist = ref<any[]>([])
const loading = ref(false)
const newEmail = ref('')
const addingEmail = ref(false)
const removingEmail = ref(false)
const deleteDialog = ref(false)
const emailIdToDelete = ref<string | null>(null)
const { notify } = useNotifications()

const fetchWhitelist = async () => {
  loading.value = true
  try {
    const { data, error } = await supabase.from('user_whitelist').select('*').order('created_at', { ascending: false })

    if (error) throw error
    whitelist.value = data || []
  } catch (error) {
    logger.error('Error fetching whitelist', { error })
    notify.error('Failed to load whitelist')
  } finally {
    loading.value = false
  }
}

const addEmail = async () => {
  if (!newEmail.value.trim()) return

  addingEmail.value = true
  try {
    const { error } = await supabase.from('user_whitelist').insert({ email: newEmail.value.trim() })

    if (error) throw error

    newEmail.value = ''
    notify.success('Email added to whitelist')
    await fetchWhitelist()
  } catch (error: unknown) {
    logger.error('Error adding email', { error })
    notify.error(error instanceof Error ? error.message : 'Failed to add email')
  } finally {
    addingEmail.value = false
  }
}

const requestRemoveEmail = (id: string) => {
  emailIdToDelete.value = id
  deleteDialog.value = true
}

const removeEmail = async () => {
  if (!emailIdToDelete.value) return

  try {
    removingEmail.value = true

    const { error } = await supabase.from('user_whitelist').delete().eq('id', emailIdToDelete.value)

    if (error) throw error
    notify.success('Email removed from whitelist')
    await fetchWhitelist()
    deleteDialog.value = false
    emailIdToDelete.value = null
  } catch (error) {
    logger.error('Error removing email', { error })
    notify.error('Failed to remove email')
  } finally {
    removingEmail.value = false
  }
}

onMounted(() => {
  fetchWhitelist()
})

definePage({
  meta: {
    requiresSuperAdmin: true,
  },
})
</script>

<template>
  <AppPage>
    <AppPageHeader title="Whitelist" description="Manage email whitelist for account registration." />

    <VCard title="Email Whitelist Management">
      <VCardText>
        <VAlert type="info" class="mb-4">
          Only whitelisted emails can register for accounts. Remove this whitelist when opening to public.
        </VAlert>

        <!-- Add Email Form -->
        <VRow class="mb-4">
          <VCol cols="12" md="8">
            <VTextField
              v-model="newEmail"
              label="Email Address"
              placeholder="user@example.com"
              type="email"
              :disabled="addingEmail"
              @keyup.enter="addEmail"
            />
          </VCol>
          <VCol cols="12" md="4" class="d-flex align-center">
            <VBtn color="primary" :loading="addingEmail" :disabled="!newEmail.trim()" @click="addEmail">
              Add Email
            </VBtn>
          </VCol>
        </VRow>

        <!-- Whitelist Table -->
        <VProgressLinear v-if="loading" indeterminate color="primary" class="mb-4" />

        <VTable v-else-if="whitelist.length">
          <thead>
            <tr>
              <th>Email</th>
              <th>Added</th>
              <th>Notes</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="entry in whitelist" :key="entry.id">
              <td>{{ entry.email }}</td>
              <td>{{ new Date(entry.created_at).toLocaleDateString() }}</td>
              <td>{{ entry.notes || '-' }}</td>
              <td>
                <VBtn
                  size="small"
                  variant="text"
                  color="error"
                  icon="tabler-trash"
                  @click="requestRemoveEmail(entry.id)"
                />
              </td>
            </tr>
          </tbody>
        </VTable>

        <div v-else class="text-center pa-4">No emails in whitelist</div>

        <!-- Instructions for Going Public -->
        <VCard variant="outlined" class="mt-6">
          <VCardTitle class="text-h6">To Remove Whitelist (Go Public)</VCardTitle>
          <VCardText>
            <ol>
              <li>
                Comment out the whitelist check block in
                <code>supabase/functions/register-regular-user/index.ts</code>
              </li>
              <li>Drop the <code>user_whitelist</code> table in your database</li>
              <li>Remove this admin whitelist page</li>
            </ol>
          </VCardText>
        </VCard>
      </VCardText>
    </VCard>

    <GenericConfirmDialog
      :is-dialog-visible="deleteDialog"
      title="Remove Whitelist Entry"
      message="Remove this email from the whitelist?"
      confirm-text="Remove"
      confirm-color="error"
      :loading="removingEmail"
      @update:is-dialog-visible="deleteDialog = $event"
      @confirm="removeEmail"
      @cancel="deleteDialog = false"
    />
  </AppPage>
</template>
