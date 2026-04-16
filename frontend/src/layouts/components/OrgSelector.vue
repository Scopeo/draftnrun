<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useOrgStore } from '@/stores/org'
import { logger } from '@/utils/logger'

const emit = defineEmits<{
  (e: 'org-changed', id: string): void
}>()

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const orgStore = useOrgStore()
const { selectedOrgId, organizations } = storeToRefs(orgStore)
const userData = computed(() => authStore.userData)

const menuOpen = ref(false)

// Call fetch on mount - store handles deduplication and change detection
onMounted(async () => {
  if (userData.value?.id) {
    logger.info('OrgSelector fetching organizations on mount')
    await orgStore.fetchOrganizations(userData.value.id)
  } else {
    logger.warn('OrgSelector: no user ID found on mount')
  }
})

// If no org selected after fetch, show message
const needsSelection = computed(() => {
  return !selectedOrgId.value && organizations.value.length > 0
})

const orgs = computed(() => {
  return organizations.value
    .map(org => ({
      org_id: org.id,
      title: org.name,
      role: org.role,
    }))
    .sort((a, b) => a.title.localeCompare(b.title))
})

const selectedOrgName = computed(() => {
  const org = organizations.value.find(o => o.id === selectedOrgId.value)
  return org?.name
})

const handleOrgChange = (orgId: string) => {
  const org = organizations.value.find(o => o.id === orgId)
  if (!org) {
    logger.error('OrgSelector: org not found', { orgId })
    return
  }

  // Guard: Don't navigate if already on this org in URL
  const currentOrgInUrl = route.params.orgId as string
  if (currentOrgInUrl === orgId) {
    logger.info('OrgSelector: already on org', { orgId })
    menuOpen.value = false
    return
  }

  logger.info('OrgSelector: navigating to org', { orgId })

  // For org-scoped routes: Update URL with new org
  if (route.path.startsWith('/org/')) {
    const pathWithoutOrg = route.path.replace(/^\/org\/[^/]+/, '')

    router.push({
      path: `/org/${orgId}${pathWithoutOrg || '/projects'}`,
      query: route.query,
      hash: route.hash,
    })
  } else {
    // For non-org routes: Navigate to projects with org
    router.push(`/org/${orgId}/projects`)
  }

  menuOpen.value = false
  emit('org-changed', orgId)
}
</script>

<template>
  <div class="px-3 py-1">
    <VMenu v-model="menuOpen" :close-on-content-click="false" location="bottom start" offset="4">
      <template #activator="{ props: menuProps }">
        <button v-bind="menuProps" class="org-switcher">
          <VAvatar size="24" color="primary" variant="tonal" rounded="lg" class="flex-shrink-0">
            <span class="text-caption font-weight-bold">{{ selectedOrgName?.charAt(0)?.toUpperCase() || '?' }}</span>
          </VAvatar>
          <span class="org-switcher__name text-body-2 font-weight-medium text-truncate">
            {{ selectedOrgName || 'Select org' }}
          </span>
          <VIcon icon="tabler-selector" size="14" class="org-switcher__chevron flex-shrink-0" />
        </button>
      </template>

      <VList density="compact" min-width="200" max-width="280">
        <VListItem
          v-for="org in orgs"
          :key="org.org_id"
          :active="org.org_id === selectedOrgId"
          color="primary"
          @click="handleOrgChange(org.org_id)"
        >
          <template #prepend>
            <VAvatar size="24" color="primary" variant="tonal" rounded="lg" class="me-2">
              <span class="text-caption font-weight-bold">{{ org.title?.charAt(0)?.toUpperCase() }}</span>
            </VAvatar>
          </template>
          <VListItemTitle class="text-body-2">{{ org.title }}</VListItemTitle>
          <VListItemSubtitle class="text-caption">{{ org.role }}</VListItemSubtitle>
        </VListItem>
      </VList>
    </VMenu>

    <VAlert v-if="needsSelection" type="info" variant="tonal" density="compact" class="mt-2">
      Select an organization
    </VAlert>
  </div>
</template>

<style lang="scss" scoped>
.org-switcher {
  display: flex;
  align-items: center;
  gap: 8px;
  inline-size: 100%;
  padding: 6px 8px;
  border: none;
  border-radius: 8px;
  background: transparent;
  cursor: pointer;
  transition: background-color 0.15s ease;
  text-align: start;

  &:hover {
    background-color: rgba(var(--v-theme-on-surface), 0.04);
  }

  &__name {
    flex: 1;
    min-inline-size: 0;
  }

  &__chevron {
    opacity: 0.5;
  }
}
</style>
