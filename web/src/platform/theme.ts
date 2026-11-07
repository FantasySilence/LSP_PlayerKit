/**
 * 主题（theme.ts）
 *
 * 管理深色/浅色主题，并把它写到 <html data-theme="..."> 上；
 * 具体颜色定义在 styles/tokens.css 的 :root 与 [data-theme='light'] 里。
 *
 * 交互关系：
 * - App.vue 启动时用 app_state 返回的 theme 调 applyTheme；
 * - 命令栏的主题按钮调用 toggleTheme，随后把新主题通过 app_set_pref 存回后端；
 * - theme 是响应式 ref，模板读它就能跟着切换显示。
 */

import { ref } from 'vue'

// 只有两套主题；字符串同时用作 data-theme 的属性值
export type Theme = 'dark' | 'light'

// 当前主题，初始为深色（与 index.html 上的 data-theme="dark" 一致）
export const theme = ref<Theme>('dark')

// 应用主题：更新响应式状态，并同步到根元素，让 CSS 变量随之切换
export function applyTheme(value: Theme): void {
  theme.value = value
  // dataset.theme = 'light' 等价于 <html data-theme="light">
  document.documentElement.dataset.theme = value
}

// 在深色/浅色之间切换，立即生效并返回新主题，方便调用方保存偏好
export function toggleTheme(): Theme {
  const next: Theme = theme.value === 'dark' ? 'light' : 'dark'
  applyTheme(next)
  return next
}
