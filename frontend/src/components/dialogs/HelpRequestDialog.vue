<script setup lang="ts">
import { logger } from '@/utils/logger'
import { supabase } from '@/services/auth'
import { useAuthStore } from '@/stores/auth'

interface Props {
  isDialogVisible: boolean
}

interface Emit {
  (e: 'update:isDialogVisible', value: boolean): void
  (e: 'submitted'): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emit>()

// Form data - only description now
const form = ref({
  issueDescription: '',
})

// Background data - captured automatically
const backgroundData = ref({
  url: '',
  projectId: '',
})

const isSubmitting = ref(false)
const isValid = ref(false)

// Notification messages
const successMessage = ref<string | null>(null)
const errorMessage = ref<string | null>(null)

const authStore = useAuthStore()
const userData = computed(() => authStore.userData)

// Capture current URL and extract project ID when dialog opens
watchEffect(() => {
  if (props.isDialogVisible && typeof window !== 'undefined') {
    backgroundData.value.url = window.location.href

    // Extract project ID from URL (adjust this regex based on your URL structure)
    const projectMatch = window.location.pathname.match(/\/projects?\/([^/]+)/)

    backgroundData.value.projectId = projectMatch ? projectMatch[1] : ''
  }
})

const updateModelValue = (val: boolean) => {
  emit('update:isDialogVisible', val)
}

const onCancel = () => {
  // Reset form and messages
  form.value = {
    issueDescription: '',
  }
  successMessage.value = null
  errorMessage.value = null
  updateModelValue(false)
}

const onSubmit = async () => {
  // Clear previous messages
  successMessage.value = null
  errorMessage.value = null

  if (!userData.value?.id) {
    errorMessage.value = 'User not authenticated'
    return
  }

  isSubmitting.value = true

  try {
    // Simple insert without title
    const { data, error } = await supabase
      .from('help_requests')
      .insert({
        user_id: userData.value.id,
        url: backgroundData.value.url,
        project_id: backgroundData.value.projectId || null,
        issue_description: form.value.issueDescription,
        created_at: new Date().toISOString(),
      })
      .select()

    if (error) {
      logger.error('Insert error details', { error })
      throw new Error(error.message || 'Failed to insert help request')
    }

    // Show success message
    successMessage.value = 'Help request submitted successfully! Our team will get back to you soon.'

    emit('submitted')

    // Close dialog after a short delay to let user see success message
    setTimeout(() => {
      onCancel()
    }, 2000)
  } catch (error: unknown) {
    logger.error('Error submitting help request', { error })

    let errorMsg = 'Failed to submit help request.'

    if (error instanceof Error) {
      errorMsg += ` ${error.message}`

      if (error.message.includes('relation "help_requests" does not exist')) {
        errorMsg = 'Database table not found. Please contact support.'
      }
    }

    errorMessage.value = errorMsg
  } finally {
    isSubmitting.value = false
  }
}

// Validation rules
const rules = {
  required: (value: string) => !!value || 'This field is required',
  minLength: (min: number) => (value: string) => value.length >= min || `Minimum ${min} characters required`,
}
</script>

<template>
  <VDialog
    :model-value="props.isDialogVisible"
    max-width="var(--dnr-dialog-md)"
    persistent
    @update:model-value="updateModelValue"
  >
    <VCard>
      <VCardTitle class="text-h6 d-flex align-center">
        <VIcon icon="tabler-help" class="me-2" />
        Request Help
      </VCardTitle>

      <VCardText>
        <!-- Success/Error Messages -->
        <VAlert
          v-if="successMessage"
          type="success"
          variant="tonal"
          closable
          class="mb-4"
          @click:close="successMessage = null"
        >
          {{ successMessage }}
        </VAlert>

        <VAlert
          v-if="errorMessage"
          type="error"
          variant="tonal"
          closable
          class="mb-4"
          @click:close="errorMessage = null"
        >
          {{ errorMessage }}
        </VAlert>

        <VForm v-model="isValid" @submit.prevent="onSubmit">
          <!-- Issue Description (only field now) -->
          <div class="mb-4">
            <VLabel class="text-body-2 text-medium-emphasis mb-1"> Describe your issue * </VLabel>
            <VTextarea
              v-model="form.issueDescription"
              :rules="[rules.required, rules.minLength(10)]"
              variant="outlined"
              rows="6"
              placeholder="Please describe the issue you're experiencing in detail..."
              counter="1000"
              maxlength="1000"
              :disabled="isSubmitting"
            />
          </div>

          <VAlert type="info" variant="tonal" class="mb-4">
            <template #prepend>
              <VIcon icon="tabler-info-circle" />
            </template>
            Your request will be sent to our support team with the current page context to help us assist you better.
          </VAlert>
        </VForm>
      </VCardText>

      <VCardActions>
        <VSpacer />
        <VBtn color="grey" variant="outlined" :disabled="isSubmitting" @click="onCancel"> Cancel </VBtn>
        <VBtn color="primary" :disabled="!isValid || isSubmitting" :loading="isSubmitting" @click="onSubmit">
          Submit Request
        </VBtn>
      </VCardActions>
    </VCard>
  </VDialog>
</template>
