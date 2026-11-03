import { ref } from 'vue'

export type Theme = 'dark' | 'light'

export const theme = ref<Theme>('dark')

export function applyTheme(value: Theme): void {
  theme.value = value
  document.documentElement.dataset.theme = value
}

export function toggleTheme(): Theme {
  const next: Theme = theme.value === 'dark' ? 'light' : 'dark'
  applyTheme(next)
  return next
}
