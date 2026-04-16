<script lang="ts" setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAbility } from '@casl/vue'
import { useDisplay } from 'vuetify'
import { useSuperAdminQuery } from '@/composables/queries/useReleaseStagesQuery'
import DraftnrunLogo from '@/components/DraftnrunLogo.vue'
import HelpRequestDialog from '@/components/dialogs/HelpRequestDialog.vue'
import NavbarThemeSwitcher from '@/layouts/components/NavbarThemeSwitcher.vue'
import OrgSelector from '@/layouts/components/OrgSelector.vue'
import UserProfile from '@/layouts/components/UserProfile.vue'
import { type NavItem, initializeNavItems } from '@/navigation/vertical/others'

const route = useRoute()
const router = useRouter()
const ability = useAbility()
const { mdAndDown } = useDisplay()

const navItems = ref<NavItem[]>([])
const mobileDrawerOpen = ref(false)
const { data: isSuperAdmin } = useSuperAdminQuery()

function onDrawerUpdate(val: boolean) {
  if (mdAndDown.value) mobileDrawerOpen.value = val
}

let stopNavItemsWatch: (() => void) | undefined

onMounted(async () => {
  const othersItemsRef = await initializeNavItems()

  stopNavItemsWatch = watch(
    othersItemsRef,
    newItems => {
      const items = newItems || []

      navItems.value = items.filter(item => item.title !== 'Super Admin')
    },
    { immediate: true, deep: true }
  )
})

onUnmounted(() => {
  stopNavItemsWatch?.()
})

const handleOrgChange = (_orgId: string) => {}

watch(
  () => route.fullPath,
  () => {
    if (mdAndDown.value) {
      mobileDrawerOpen.value = false
    }
  }
)

const visibleNavItems = computed(() =>
  navItems.value.filter(item => {
    if (item.heading) return false
    if (!item.action || !item.subject) return true
    const actions = Array.isArray(item.action) ? item.action : [item.action]
    return actions.some(action => ability.can(action, item.subject!))
  })
)

function isActive(item: NavItem): boolean {
  if (!item.to) return false
  const resolved = router.resolve(typeof item.to === 'string' ? { name: item.to } : item.to)
  return route.path.startsWith(resolved.path)
}

const isHelpDialogVisible = ref(false)
</script>

<template>
  <VBtn v-if="mdAndDown" icon color="default" class="sidebar-toggle" elevation="2" @click="mobileDrawerOpen = true">
    <VIcon icon="tabler-menu-2" />
  </VBtn>

  <VNavigationDrawer
    v-bind="mdAndDown ? { modelValue: mobileDrawerOpen } : {}"
    :permanent="!mdAndDown"
    :temporary="mdAndDown"
    :width="190"
    class="app-sidebar"
    @update:model-value="onDrawerUpdate"
  >
    <template #prepend>
      <div class="sidebar-header d-flex justify-center pa-5 pb-3">
        <RouterLink to="/" class="d-flex align-center text-decoration-none">
          <DraftnrunLogo style="width: 120px; height: 120px" />
        </RouterLink>
      </div>

      <OrgSelector @org-changed="handleOrgChange" />

      <VDivider class="mx-4 mt-1 mb-2" />
    </template>

    <VList nav density="compact" class="px-2">
      <VListItem
        v-for="item in visibleNavItems"
        :key="item.title"
        :to="item.to as any"
        :prepend-icon="item.icon?.icon"
        :active="isActive(item)"
        color="primary"
        class="nav-item"
        :class="{ 'nav-item--active': isActive(item) }"
      >
        <VListItemTitle class="text-body-2">{{ item.title }}</VListItemTitle>
        <template v-if="item.badgeContent" #append>
          <VBadge :content="item.badgeContent" :class="item.badgeClass" inline />
        </template>
      </VListItem>
    </VList>

    <template #append>
      <div v-if="isSuperAdmin" class="px-4 pb-2">
        <VBtn
          :to="{ name: 'admin-super-admin' }"
          variant="text"
          class="w-100 justify-start text-caption"
          color="default"
          prepend-icon="tabler-shield-check"
          size="x-small"
        >
          Super-admin
        </VBtn>
      </div>

      <VDivider class="mx-4 mb-2" />

      <div class="sidebar-footer pa-3 d-flex align-center justify-space-between">
        <UserProfile />
        <div class="d-flex align-center gap-1">
          <VBtn
            variant="text"
            size="small"
            color="default"
            prepend-icon="tabler-lifebuoy"
            @click="isHelpDialogVisible = true"
          >
            Help
          </VBtn>
          <NavbarThemeSwitcher />
        </div>
      </div>
    </template>
  </VNavigationDrawer>

  <HelpRequestDialog v-model:is-dialog-visible="isHelpDialogVisible" />
</template>

<style lang="scss" scoped>
.sidebar-toggle {
  position: fixed;
  inset-block-start: 14px;
  inset-inline-start: 14px;
  z-index: 1200;
}

.app-sidebar {
  position: fixed !important;
  block-size: 100dvh !important;
  border-inline-end: var(--dnr-border-default);
  box-shadow: var(--dnr-elevation-1);
}

.nav-item {
  border-radius: var(--dnr-radius-md);
  margin-block: 1px;
  font-weight: 400;

  &--active {
    font-weight: 500;
    background-color: rgba(var(--v-theme-on-surface), 0.06);
  }
}
</style>
