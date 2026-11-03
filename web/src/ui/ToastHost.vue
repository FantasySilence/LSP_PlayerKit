<script setup lang="ts">
import { remove, toasts } from '../platform/toast'
</script>

<template>
  <div class="toast-host">
    <TransitionGroup name="toast">
      <div
        v-for="item in toasts"
        :key="item.id"
        class="toast"
        :class="item.type"
        @click="remove(item.id)"
      >
        <div class="toast-msg">{{ item.message }}</div>
        <div v-if="item.detail" class="toast-detail">{{ item.detail }}</div>
      </div>
    </TransitionGroup>
  </div>
</template>

<style scoped>
.toast-host {
  position: fixed;
  right: 18px;
  bottom: 18px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  z-index: 80;
  max-width: 380px;
}

.toast {
  padding: 10px 14px;
  border-radius: 10px;
  background: var(--surface-2);
  border: 1px solid var(--line-strong);
  box-shadow: var(--shadow);
  cursor: pointer;
}

.toast.success {
  border-color: rgba(89, 212, 153, 0.5);
}

.toast.error {
  border-color: rgba(255, 95, 109, 0.55);
}

.toast-msg {
  font-size: 13px;
}

.toast-detail {
  margin-top: 4px;
  color: var(--muted);
  font-size: 11px;
  word-break: break-all;
}

.toast-enter-active,
.toast-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translateY(6px);
}
</style>
