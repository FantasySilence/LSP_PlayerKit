import { reactive } from 'vue'

export type ToastType = 'info' | 'success' | 'error'

export interface ToastItem {
  id: number
  type: ToastType
  message: string
  detail?: string
}

export const toasts = reactive<ToastItem[]>([])

let seq = 0

export function notify(type: ToastType, message: string, detail?: string): void {
  const id = ++seq
  toasts.push({ id, type, message, detail })
  window.setTimeout(() => remove(id), type === 'error' ? 6000 : 3000)
}

export function remove(id: number): void {
  const index = toasts.findIndex((item) => item.id === id)
  if (index >= 0) toasts.splice(index, 1)
}

export function notifyError(error: unknown): void {
  if (error && typeof error === 'object' && 'message' in error) {
    const err = error as { message: string; detail?: string }
    notify('error', err.message, err.detail)
  } else {
    notify('error', String(error))
  }
}
