<script setup lang="ts">
import { storeToRefs } from 'pinia'
import AppButton from '@/components/base/AppButton.vue'
import AppIcon from '@/components/base/AppIcon.vue'
import { useToastStore } from '@/stores/toast_store'

/**
 * The app's toasts (`toast_store`), near the window's top right beneath the frame's header, over every view and the verdict
 * panel: a polite status a screen reader says when it can, never stealing the focus. Each holds while pointed at or focused,
 * and closes on its ×. Form, then word: a done toast's tick, a failed one's error mark, each with its words.
 */
const store = useToastStore()
const { toasts } = storeToRefs(store)
</script>

<template>
  <div class="toasts" role="status" aria-live="polite" data-part="toasts">
    <div
      v-for="toast in toasts"
      :key="toast.id"
      class="toast"
      :class="{ failed: toast.failed }"
      :data-toast="toast.id"
      @mouseenter="store.hold(toast.id)"
      @mouseleave="store.release(toast.id)"
      @focusin="store.hold(toast.id)"
      @focusout="store.release(toast.id)"
    >
      <AppIcon :name="toast.failed ? 'status-error' : 'status-ok'" class="toast-mark" />
      <span class="toast-words">
        <span class="toast-text" data-part="toast-text">{{ toast.text }}</span>
        <span v-if="toast.detail" class="toast-detail" data-part="toast-detail">{{ toast.detail }}</span>
      </span>
      <AppButton variant="quiet" size="compact" glyph aria-label="Close" data-part="toast-close" @click="store.dismiss(toast.id)">×</AppButton>
    </div>
  </div>
</template>

<style scoped>
/* the region stands at the top right, beneath the frame's header, whose hourglass a toast may point to, and lets the pointer
   through where no toast is */
.toasts {
  position: fixed;
  top: calc(var(--frame-header-height, 3rem) + var(--space-sm));
  right: var(--space-md);
  z-index: var(--z-toast);
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: var(--space-xs);
  max-width: min(28rem, calc(100vw - 2 * var(--space-md)));
  pointer-events: none;
}

.toast {
  display: flex;
  align-items: flex-start;
  gap: var(--space-sm);
  padding: var(--space-sm) var(--space-md);
  background-color: var(--color-bg-surface);
  border: 1px solid var(--color-border-overlay);
  box-shadow: var(--shadow-overlay);
  pointer-events: auto;
}

.toast-mark {
  color: var(--color-positive);
  flex: none;
  margin-top: 2px;
}

.toast.failed .toast-mark {
  color: var(--color-error);
}

.toast-words {
  display: flex;
  flex-direction: column;
}

.toast-detail {
  color: var(--color-text-secondary);
}
</style>
