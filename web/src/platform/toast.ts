/**
 * 全局提示（toast.ts）
 *
 * 维护一个提示队列，任何模块都可以调用 notify 弹出短暂消息；
 * 真正的渲染在 ui/ToastHost.vue，它直接读取这里的 toasts 数组。
 *
 * 交互关系：
 * - notifyError 把 BridgeError 或其他异常转成 error 类型的提示，常用于 catch 分支；
 * - ToastHost 遍历 toasts 渲染，点击提示会调用 remove 立即移除；
 * - 每条提示按类型自动消失：error 停留 6 秒，其余 3 秒。
 */

import { reactive } from 'vue'

// 提示类型：info 普通消息、success 成功、error 失败
export type ToastType = 'info' | 'success' | 'error'

// 一条提示：id 用于列表 key 与删除；detail 是可选的第二行补充说明
export interface ToastItem {
  id: number
  type: ToastType
  message: string
  detail?: string
}

// 当前显示的提示队列；reactive 让 ToastHost 自动增删
export const toasts = reactive<ToastItem[]>([])

// 自增序号：保证每条提示的 id 唯一，即使文案完全相同也不会串
let seq = 0

// 新增一条提示，并按类型安排自动消失的时间
export function notify(type: ToastType, message: string, detail?: string): void {
  const id = ++seq
  toasts.push({ id, type, message, detail })
  window.setTimeout(() => remove(id), type === 'error' ? 6000 : 3000)
}

// 按 id 移除一条提示；已被移除时下标为 -1，直接忽略
export function remove(id: number): void {
  const index = toasts.findIndex((item) => item.id === id)
  if (index >= 0) toasts.splice(index, 1)
}

// 把任意异常转成 error 提示：优先取 message/detail，取不到就转成字符串
export function notifyError(error: unknown): void {
  if (error && typeof error === 'object' && 'message' in error) {
    const err = error as { message: string; detail?: string }
    notify('error', err.message, err.detail)
  } else {
    notify('error', String(error))
  }
}
