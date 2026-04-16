/**
 * Composable to detect if user is in an organization invite flow
 * Used to conditionally hide Google authentication options
 */
export function useInviteFlow() {
  const route = useRoute()

  const isInviteFlow = computed(() => {
    // Check for invite token in query params
    if (route.query.invite_token) return true

    // Check for redirect_to parameter (usually used with invites)
    if (route.query.redirect_to) {
      const redirectTo = String(route.query.redirect_to)
      // Check if redirect_to contains invite-related paths
      return redirectTo.includes('accept-invite') || redirectTo.includes('invite')
    }

    // Check if current path is invite-related
    if (route.path.includes('accept-invite') || route.path.includes('invite')) {
      return true
    }

    return false
  })

  const inviteToken = computed(() => (route.query.invite_token as string) || '')
  const redirectTo = computed(() => (route.query.redirect_to as string) || '')

  return {
    isInviteFlow,
    inviteToken,
    redirectTo,
    showSocialAuth: computed(() => !isInviteFlow.value),
  }
}
