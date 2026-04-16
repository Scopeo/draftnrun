import { type ComputedRef, computed, ref } from 'vue'
import { scopeoApi } from '@/api'
import { useCurrentProject } from '@/composables/queries/useProjectsQuery'
import { useNotifications } from '@/composables/useNotifications'
import { logger } from '@/utils/logger'

export function useEditSidebarOAuth(componentData: ComputedRef<any>) {
  const { currentProject } = useCurrentProject()
  const { notify } = useNotifications()

  const showGmailConnectDialog = ref(false)
  const showGmailDisconnectDialog = ref(false)
  const gmailConnecting = ref(false)

  const hasIntegration = computed(() => componentData.value?.integration != null)

  const isGmailIntegration = computed(
    () => hasIntegration.value && componentData.value?.integration?.service === 'gmail sender'
  )

  const isIntegrationConnected = computed(
    () => hasIntegration.value && componentData.value?.integration?.id && componentData.value?.integration?.secret_id
  )

  async function connectGmail() {
    if (!componentData.value?.integration?.id || !currentProject.value?.project_id) {
      logger.error('Missing integration ID or project ID')
      return
    }

    gmailConnecting.value = true
    try {
      const authUrl = new URL('https://accounts.google.com/o/oauth2/v2/auth')

      authUrl.searchParams.set('client_id', import.meta.env.VITE_GOOGLE_CLIENT_ID)
      authUrl.searchParams.set('redirect_uri', `${window.location.origin}/auth/callback`)
      authUrl.searchParams.set('response_type', 'code')
      authUrl.searchParams.set(
        'scope',
        'https://www.googleapis.com/auth/gmail.compose https://www.googleapis.com/auth/gmail.modify'
      )
      authUrl.searchParams.set('access_type', 'offline')
      authUrl.searchParams.set('prompt', 'consent')
      authUrl.searchParams.set('state', 'gmail_integration')

      const popup = window.open(authUrl.toString(), 'gmail-auth', 'width=500,height=600')
      if (!popup) throw new Error('Popup blocked. Please allow popups for this site.')

      const authCode = await new Promise<string>((resolve, reject) => {
        const messageHandler = (event: MessageEvent) => {
          if (event.origin !== window.location.origin) return
          if (event.data.type === 'gmail_auth_success' && event.data.code) {
            window.removeEventListener('message', messageHandler)
            popup.close()
            resolve(event.data.code)
          } else if (event.data.type === 'gmail_auth_error') {
            window.removeEventListener('message', messageHandler)
            popup.close()
            reject(new Error(event.data.error || 'Authorization failed'))
          }
        }

        window.addEventListener('message', messageHandler)

        const checkClosed = setInterval(() => {
          if (popup.closed) {
            clearInterval(checkClosed)
            window.removeEventListener('message', messageHandler)
            reject(new Error('Authorization cancelled'))
          }
        }, 1000)
      })

      const tokenResponse = await fetch('https://oauth2.googleapis.com/token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({
          client_id: import.meta.env.VITE_GOOGLE_CLIENT_ID,
          client_secret: import.meta.env.VITE_GOOGLE_CLIENT_SECRET,
          code: authCode,
          grant_type: 'authorization_code',
          redirect_uri: `${window.location.origin}/auth/callback`,
        }),
      })

      if (!tokenResponse.ok) throw new Error('Failed to exchange code for tokens')
      const tokens = await tokenResponse.json()

      const result = await scopeoApi.integration.addOrUpdateIntegration(
        currentProject.value.project_id,
        componentData.value?.integration?.id,
        {
          integration_id: componentData.value?.integration?.id,
          access_token: tokens.access_token,
          refresh_token: tokens.refresh_token || '',
          expires_in: tokens.expires_in || 3600,
          token_last_updated: new Date().toISOString(),
        }
      )

      if (componentData.value?.integration) componentData.value.integration.secret_id = result.secret_id
      showGmailConnectDialog.value = false
    } catch (error) {
      logger.error('Error connecting Gmail', { error })
      notify.error('Failed to connect Gmail. Please try again.')
    } finally {
      gmailConnecting.value = false
    }
  }

  function requestDisconnectGmail() {
    showGmailDisconnectDialog.value = true
  }

  function cancelDisconnectGmail() {
    showGmailDisconnectDialog.value = false
  }

  async function disconnectGmail() {
    if (componentData.value?.integration) componentData.value.integration.secret_id = undefined
    notify.success('Gmail integration disconnected successfully.')
    showGmailDisconnectDialog.value = false
  }

  return {
    showGmailConnectDialog,
    showGmailDisconnectDialog,
    gmailConnecting,
    hasIntegration,
    isGmailIntegration,
    isIntegrationConnected,
    connectGmail,
    disconnectGmail,
    requestDisconnectGmail,
    cancelDisconnectGmail,
  }
}
