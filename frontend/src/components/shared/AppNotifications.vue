<script setup lang="ts">
import { useNotifications } from '@/composables/useNotifications'

const { notifications, remove } = useNotifications()
</script>

<template>
  <div class="app-notifications">
    <TransitionGroup name="notif">
      <VSnackbar
        v-for="(notif, index) in notifications"
        :key="notif.id"
        :model-value="true"
        :color="notif.color"
        :timeout="notif.persistent ? -1 : notif.timeout"
        location="bottom center"
        :style="{ '--notif-offset': `${index * 60}px` }"
        class="app-notifications__item"
        @update:model-value="remove(notif.id)"
      >
        {{ notif.message }}
        <template #actions>
          <VBtn
            v-if="notif.action"
            variant="text"
            density="comfortable"
            @click="
              () => {
                notif.action?.onClick()
                remove(notif.id)
              }
            "
          >
            {{ notif.action.text }}
          </VBtn>
          <VBtn
            v-if="notif.persistent"
            icon="tabler-x"
            variant="text"
            density="comfortable"
            size="small"
            @click="remove(notif.id)"
          />
        </template>
      </VSnackbar>
    </TransitionGroup>
  </div>
</template>

<style lang="scss" scoped>
.app-notifications__item {
  margin-block-end: var(--notif-offset, 0px);
}

.notif-enter-active,
.notif-leave-active {
  transition:
    opacity 0.2s ease,
    transform 0.2s ease;
}

.notif-enter-from {
  opacity: 0;
  transform: translateY(8px);
}

.notif-leave-to {
  opacity: 0;
  transform: translateX(16px);
}
</style>
