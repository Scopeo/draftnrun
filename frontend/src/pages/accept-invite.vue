<script setup lang="ts">
import { useRoute, useRouter } from 'vue-router'
import { logger } from '@/utils/logger'
import { useSelectedOrg } from '@/composables/useSelectedOrg'
import type { UserData } from '@/services/auth'
import { supabase } from '@/services/auth'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const token = ref((route.query.token as string) || '')
const status = ref('checking') // 'checking', 'invalid', 'needs_auth', 'processing', 'success', 'error'
const errorMessage = ref('')
const authStore = useAuthStore()
const userData = computed(() => authStore.userData)
const { setSelectedOrg } = useSelectedOrg()

// Invitation details
const invitationData = ref<{
  email: string
  orgName: string
  role: string
  inviterEmail: string
} | null>(null)

// Fetch invitation details to show context
const fetchInvitationDetails = async () => {
  try {
    const { data, error } = await supabase
      .from('organization_invitations')
      .select(
        `
        email,
        role,
        org_id,
        organizations!inner(name),
        invited_by
      `
      )
      .eq('token', token.value)
      .eq('accepted', false)
      .single()

    if (error) throw error

    const organizations = (data as any).organizations

    invitationData.value = {
      email: data.email,
      orgName: Array.isArray(organizations) ? organizations[0]?.name : organizations?.name || 'Unknown Organization',
      role: data.role,
      inviterEmail: 'Team Member', // Simplified since we can't access user emails directly
    }
  } catch (error) {
    logger.error('Error fetching invitation details', { error })
    // Don't fail the whole flow if we can't get details
  }
}

// Check if user is already logged in
onMounted(async () => {
  // If the user was just redirected from the registration page, the work is done.
  if (route.query.registered === 'true') {
    status.value = 'success'

    // Redirect to home which will handle org selection
    setTimeout(() => {
      router.push('/')
    }, 2000)
    return
  }

  // This is the original flow for existing users or those who need to log in.
  if (!token.value) {
    status.value = 'invalid'
    errorMessage.value = 'Invalid invitation link'
    return
  }

  await fetchInvitationDetails()

  // Check if user is logged in (cookie or session).
  const {
    data: { session },
  } = await supabase.auth.getSession()

  if (session?.user) {
    // User is logged in, try to accept the invitation for them.
    if (!userData.value?.id) {
      const mappedUserData: UserData = {
        id: session.user.id,
        fullName: session.user.user_metadata.full_name || session.user.email?.split('@')[0] || '',
        username: session.user.user_metadata.username || session.user.email?.split('@')[0] || '',
        email: session.user.email,
        avatar: session.user.user_metadata.avatar_url,
        role: session.user.user_metadata.role || 'client',
      }

      authStore.updateUserData(mappedUserData)
    }
    await verifyInvitation()
  } else {
    // User is not logged in, prompt them to sign in or register.
    status.value = 'needs_auth'
  }
})

// Function to handle after user logs in or signs up
const handleAuth = async () => {
  if (userData.value?.id) {
    await verifyInvitation()
  }
}

// Verify the invitation token
const verifyInvitation = async () => {
  status.value = 'processing'

  try {
    // Ensure we have necessary data
    if (!userData.value?.id || !token.value) {
      errorMessage.value = 'User session or invitation token is missing.'
      status.value = 'error'
      logger.error('Missing userId or token for verifyInvitation')
      return
    }

    const { data: verificationResult, error: functionError } = await supabase.functions.invoke('verify-invitation', {
      body: {
        token: token.value,
        userId: userData.value.id,
      },
    })

    if (functionError) {
      // Handle errors from the function invocation itself
      logger.error('Error invoking verify-invitation', { error: functionError })
      status.value = 'error'
      errorMessage.value = functionError.message || 'An error occurred while processing the invitation.'
      return
    }

    // Check if verification was successful and has required data
    if (verificationResult && verificationResult.success && verificationResult.data && verificationResult.data.orgId) {
      // === CRITICAL: Update the selected organization ===
      setSelectedOrg(verificationResult.data.orgId, verificationResult.data.role)
      logger.info(
        `[accept-invite] setSelectedOrg called with orgId: ${verificationResult.data.orgId}, role: ${verificationResult.data.role}`
      )
      // ===============================================

      status.value = 'success'

      // Determine the appropriate redirect based on user role
      let redirectPath = '/'
      const userRole = verificationResult.data.role?.toLowerCase()
      const orgId = verificationResult.data.orgId

      logger.info(`[accept-invite] User role: ${userRole}`)

      // Only redirect to /organization if user is admin
      if (userRole === 'admin') {
        redirectPath = orgId ? `/org/${orgId}/organization` : '/'
      } else {
        // Non-admin users go to projects in their org
        redirectPath = orgId ? `/org/${orgId}/projects` : '/'
      }

      logger.info(`[accept-invite] Will redirect to: ${redirectPath}`)

      // Redirect after short delay
      setTimeout(() => {
        router.push(redirectPath)
      }, 2000)
    } else {
      // Handle cases where the function returned success:false or data was missing
      logger.error('Verification response not successful or data missing', { error: verificationResult })
      status.value = 'error'
      errorMessage.value =
        (verificationResult as any)?.error || 'Invitation verification failed. Unexpected response format.'
    }
  } catch (error: unknown) {
    logger.error('Unexpected error in verifyInvitation', { error })
    status.value = 'error'
    errorMessage.value = error instanceof Error ? error.message : 'Failed to verify invitation. Please try again.'
  }
}

// Generate login/register URLs with token
const getAuthUrl = (page: 'login' | 'register') => {
  return `/${page}?invite_token=${token.value}&redirect_to=${encodeURIComponent(`/accept-invite?token=${token.value}`)}`
}

// Set up auth state listener
const unsubscribe = supabase.auth.onAuthStateChange((event, session) => {
  if (event === 'SIGNED_IN' && session?.user?.id) {
    handleAuth()
  }
})

// Clean up listener on component unmount
onUnmounted(() => {
  unsubscribe.data.subscription.unsubscribe()
})

definePage({
  meta: {
    public: true,
    layout: 'blank',
  },
})
</script>

<template>
  <VContainer>
    <VRow justify="center">
      <VCol cols="12" md="6">
        <VCard>
          <VCardTitle class="text-center pt-6">Organization Invitation</VCardTitle>

          <VCardText>
            <!-- Loading state -->
            <div v-if="status === 'checking'" class="text-center">
              <VProgressCircular indeterminate color="primary" />
              <p class="mt-4">Checking invitation...</p>
            </div>

            <!-- Invalid token -->
            <div v-else-if="status === 'invalid'" class="text-center">
              <VIcon icon="tabler-alert-circle" size="large" color="error" />
              <p class="text-error mt-2">{{ errorMessage }}</p>
            </div>

            <!-- Needs authentication -->
            <div v-else-if="status === 'needs_auth'" class="text-center">
              <!-- Invitation Context -->
              <div class="mb-6">
                <VAlert type="info" variant="tonal" class="mb-4">
                  <VIcon icon="tabler-mail" class="me-2" />
                  You have been invited to join an organization. Please sign in or create an account to continue.
                </VAlert>

                <VCard v-if="invitationData" variant="outlined" class="text-start">
                  <VCardText>
                    <div><strong>Organization:</strong> {{ invitationData.orgName }}</div>
                    <div><strong>Role:</strong> {{ invitationData.role }}</div>
                    <div><strong>Invited Email:</strong> {{ invitationData.email }}</div>
                  </VCardText>
                </VCard>
              </div>

              <p class="mb-4">Please sign in or create an account to accept this invitation.</p>

              <!-- Existing User -->
              <div class="mb-4">
                <h4 class="text-h6 mb-2">Already have an account?</h4>
                <VBtn color="primary" size="large" :to="getAuthUrl('login')" prepend-icon="tabler-login">
                  Sign In
                </VBtn>
              </div>

              <VDivider class="my-4" />

              <!-- New User -->
              <div>
                <h4 class="text-h6 mb-2">New to our platform?</h4>
                <VBtn
                  color="success"
                  variant="outlined"
                  size="large"
                  :to="getAuthUrl('register')"
                  prepend-icon="tabler-user-plus"
                >
                  Create Account
                </VBtn>
              </div>
            </div>

            <!-- Processing -->
            <div v-else-if="status === 'processing'" class="text-center">
              <VProgressCircular indeterminate color="primary" />
              <p class="mt-4">Processing invitation...</p>
            </div>

            <!-- Success -->
            <div v-else-if="status === 'success'" class="text-center">
              <VIcon icon="tabler-check-circle" size="large" color="success" />
              <p class="text-success mt-2">You have successfully joined the organization!</p>
              <p>Redirecting...</p>
            </div>

            <!-- Error -->
            <div v-else-if="status === 'error'" class="text-center">
              <VIcon icon="tabler-alert-circle" size="large" color="error" />
              <p class="text-error mt-2">{{ errorMessage }}</p>
              <VBtn color="primary" class="mt-4" @click="verifyInvitation"> Try Again </VBtn>
            </div>
          </VCardText>
        </VCard>
      </VCol>
    </VRow>
  </VContainer>
</template>
