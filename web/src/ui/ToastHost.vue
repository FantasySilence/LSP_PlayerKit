<!--
  ToastHost.vue —— 全局提示容器

  负责：把 platform/toast.ts 里 toasts 队列中的提示渲染成右下角浮层，
  并用 TransitionGroup 做进出场动画；点击某条提示立即移除。
  交互关系：
  - 只读取 toasts、调用 remove，自己不创建提示；
  - 由 App.vue 挂载一次，任何模块通过 notify/notifyError 添加的提示都会出现在这里。
-->

<script setup lang="ts">
// 直接复用全局提示队列与移除函数，本组件没有自己的状态
import { remove, toasts } from '../platform/toast'
</script>

<template>
  <!-- 区块：Toast 容器（固定在右下角，按加入顺序纵向排列） -->
  <div class="toast-host">
    <!-- name="toast" 对应下方 .toast-enter-* / .toast-leave-* 过渡类名 -->
    <TransitionGroup name="toast">
      <div
        v-for="item in toasts"
        :key="item.id"
        class="toast"
        :class="item.type"
        @click="remove(item.id)"
      >
        <!-- 主文案；item.type 对应的 success/error 只影响边框配色 -->
        <div class="toast-msg">{{ item.message }}</div>
        <!-- 可选补充说明，例如后端错误信封里的 detail -->
        <div v-if="item.detail" class="toast-detail">{{ item.detail }}</div>
      </div>
    </TransitionGroup>
  </div>
</template>

<style scoped>
/* 区块：容器定位（右下角，最多 380px 宽） */
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

/* 区块：单条提示 */
.toast {
  padding: 10px 14px;
  border-radius: 10px;
  background: var(--surface-2);
  border: 1px solid var(--line-strong);
  box-shadow: var(--shadow);
  cursor: pointer;
}

/* 区块：按类型调整边框颜色 */
.toast.success {
  border-color: rgba(89, 212, 153, 0.5);
}

.toast.error {
  border-color: rgba(255, 95, 109, 0.55);
}

/* 区块：文字（主文案 + 补充说明） */
.toast-msg {
  font-size: 13px;
}

.toast-detail {
  margin-top: 4px;
  color: var(--muted);
  font-size: 11px;
  word-break: break-all;
}

/* 区块：进出场动画 */
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
