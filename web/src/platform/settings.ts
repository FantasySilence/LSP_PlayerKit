import { reactive } from 'vue'

import { invoke } from './bridge'

export const settings = reactive<Record<string, Record<string, any>>>({})
export const revision = reactive<Record<string, number>>({})

function bump(tool: string) {
  revision[tool] = (revision[tool] ?? 0) + 1
}

export async function loadSettings(tool: string): Promise<Record<string, any>> {
  const data = await invoke<Record<string, any>>('settings_get', tool)
  settings[tool] = data
  bump(tool)
  return data
}

export function getSettings(tool: string): Record<string, any> {
  return settings[tool] ?? {}
}

export async function saveSettings(
  tool: string,
  values: Record<string, any>,
): Promise<Record<string, any>> {
  const saved = await invoke<Record<string, any>>('settings_save', tool, values)
  settings[tool] = saved
  bump(tool)
  return saved
}

export async function resetSettings(tool: string): Promise<Record<string, any>> {
  const data = await invoke<Record<string, any>>('settings_reset', tool)
  settings[tool] = data
  bump(tool)
  return data
}

export function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}
