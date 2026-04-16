import { useQueryClient } from '@tanstack/vue-query'
import { ref } from 'vue'
import { invalidateOAuthConnectionsQuery } from '@/composables/queries/useOAuthConnectionsQuery'
import { supabase } from '@/services/auth'
import { scopeoApi } from '@/api'
import { logger } from '@/utils/logger'

export type OAuthFlowState = 'idle' | 'authorizing' | 'waiting_oauth' | 'confirming' | 'connected' | 'error'

export function useOAuthFlow(orgId: () => string | undefined) {
  const state = ref<OAuthFlowState>('idle')
  const errorMessage = ref<string | null>(null)
  const oauthTab = ref<Window | null>(null)
  const pendingConnectionId = ref<string | null>(null)
  const queryClient = useQueryClient()

  const startOAuthFlow = async (provider: string) => {
    const org = orgId()
    if (!org) {
      errorMessage.value = 'No organization selected'
      state.value = 'error'
      return
    }

    // Open popup IMMEDIATELY (before async call) to avoid popup blocker
    const width = 600
    const height = 700
    const left = window.screenX + (window.outerWidth - width) / 2
    const top = window.screenY + (window.outerHeight - height) / 2

    oauthTab.value = window.open(
      'about:blank',
      '_blank',
      `width=${width},height=${height},left=${left},top=${top},popup=yes`
    )

    if (!oauthTab.value) {
      errorMessage.value = 'Failed to open authorization window. Please allow popups for this site.'
      state.value = 'error'
      return
    }

    state.value = 'authorizing'
    errorMessage.value = null

    try {
      const requestData: { provider_config_key: string; end_user_email?: string } = {
        provider_config_key: provider,
      }

      try {
        const {
          data: { user },
        } = await supabase.auth.getUser()

        if (user?.email) {
          requestData.end_user_email = user.email
        }
      } catch (error: unknown) {
        logger.warn('Failed to fetch user email for OAuth flow', { error })
      }

      const response = await scopeoApi.oauthConnections.authorize(org, requestData)

      if (!response?.oauth_url || !response?.pending_connection_id) {
        if (oauthTab.value && !oauthTab.value.closed) oauthTab.value.close()
        throw new Error('Invalid response from server (missing oauth_url or pending_connection_id)')
      }

      pendingConnectionId.value = response.pending_connection_id

      if (oauthTab.value && !oauthTab.value.closed) {
        oauthTab.value.location.href = response.oauth_url
      }

      state.value = 'waiting_oauth'
    } catch (error: unknown) {
      if (oauthTab.value && !oauthTab.value.closed) oauthTab.value.close()
      oauthTab.value = null
      logger.error('OAuth authorization error', { error })
      errorMessage.value = error instanceof Error ? error.message : 'Failed to start authorization. Please try again.'
      state.value = 'error'
    }
  }

  const confirmConnection = async (provider: string, name?: string) => {
    const org = orgId()
    if (!org) {
      errorMessage.value = 'No organization selected'
      state.value = 'error'
      return null
    }

    if (!pendingConnectionId.value) {
      errorMessage.value = 'Missing pending_connection_id. Please restart the OAuth flow.'
      state.value = 'error'
      return null
    }

    state.value = 'confirming'
    errorMessage.value = null

    try {
      const response = await scopeoApi.oauthConnections.confirm(org, {
        provider_config_key: provider,
        pending_connection_id: pendingConnectionId.value,
        name: name || '',
      })

      if (!response?.connection_id) {
        throw new Error(
          'Authorization not completed yet. Please make sure you completed the authorization in the opened tab.'
        )
      }

      // Close OAuth tab
      if (oauthTab.value && !oauthTab.value.closed) oauthTab.value.close()
      oauthTab.value = null
      pendingConnectionId.value = null

      // Invalidate queries so both connections and definitions lists refresh
      invalidateOAuthConnectionsQuery(queryClient, org)
      queryClient.invalidateQueries({ queryKey: ['org-variable-definitions', org] })

      state.value = 'connected'
      return response
    } catch (error: unknown) {
      logger.error('OAuth confirmation error', { error })

      const errMsg = error instanceof Error ? error.message : ''
      if (errMsg.includes('not found')) {
        errorMessage.value =
          'Authorization not found. Please complete the authorization in the opened tab, then try again.'
      } else {
        errorMessage.value = errMsg || 'Failed to confirm authorization. Please try again.'
      }
      state.value = 'error'
      return null
    }
  }

  const cancelFlow = () => {
    if (oauthTab.value && !oauthTab.value.closed) oauthTab.value.close()
    oauthTab.value = null
    pendingConnectionId.value = null
    errorMessage.value = null
    state.value = 'idle'
  }

  const resetState = () => {
    state.value = 'idle'
    errorMessage.value = null
  }

  return {
    state,
    errorMessage,
    startOAuthFlow,
    confirmConnection,
    cancelFlow,
    resetState,
  }
}
