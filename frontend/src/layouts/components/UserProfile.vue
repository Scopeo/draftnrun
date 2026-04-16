<script setup lang="ts">
import { computed } from 'vue'
import { logout } from '@/services/auth'
import { useAuthStore } from '@/stores/auth'

const authStore = useAuthStore()
const userData = computed(() => authStore.userData)

const handleLogout = async () => {
  await logout()
}
</script>

<template>
  <VBadge v-if="userData" dot bordered location="bottom right" offset-x="1" offset-y="2" color="success">
    <VAvatar
      size="38"
      class="cursor-pointer"
      :color="!(userData && userData.avatar) ? 'primary' : undefined"
      :variant="!(userData && userData.avatar) ? 'tonal' : undefined"
    >
      <VImg v-if="userData && userData.avatar" :src="userData.avatar" />
      <VIcon v-else icon="tabler-user" size="20" />

      <VMenu activator="parent" width="240" location="bottom end" offset="12px">
        <VList>
          <VListItem>
            <div class="d-flex gap-2 align-center">
              <VListItemAction>
                <VBadge dot location="bottom right" offset-x="3" offset-y="3" color="success" bordered>
                  <VAvatar
                    :color="!(userData && userData.avatar) ? 'primary' : undefined"
                    :variant="!(userData && userData.avatar) ? 'tonal' : undefined"
                  >
                    <VImg v-if="userData && userData.avatar" :src="userData.avatar" />
                    <VIcon v-else icon="tabler-user" />
                  </VAvatar>
                </VBadge>
              </VListItemAction>

              <div>
                <h6 class="text-h6 font-weight-medium">
                  {{ userData.fullName || userData.username }}
                </h6>
                <VListItemSubtitle class="text-capitalize text-disabled">
                  {{ userData.role }}
                </VListItemSubtitle>
              </div>
            </div>
          </VListItem>

          <VDivider class="my-2" />

          <div class="px-4 py-2">
            <VBtn block size="small" color="error" append-icon="tabler-logout" @click="handleLogout"> Logout </VBtn>
          </div>
        </VList>
      </VMenu>
    </VAvatar>
  </VBadge>
</template>
