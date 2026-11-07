/**
 * 设置缓存（settings.ts）
 *
 * 每个工具的设置都由后端持久化为一份 JSON；本模块在内存里缓存这些值，
 * 供设置抽屉和各工具视图读取，避免重复请求。
 *
 * 交互关系：
 * - 通过 platform/bridge.ts 的 invoke 调后端 settings_get / settings_save /
 *   settings_reset（后端把数据存在数据目录的 settings/ 下）；
 * - 每次读/写成功后递增 revision[tool]，需要感知“设置变了”的组件可以 watch 它；
 * - App.vue 切换工具时调用 loadSettings 预加载该工具设置；
 * - SettingsDrawer.vue 直接读写 settings，clone 用来复制草稿而不改动缓存。
 */

import { reactive } from 'vue'

import { invoke } from './bridge'

// 设置缓存：工具 id → 该工具当前的设置对象；reactive 让模板能自动更新
export const settings = reactive<Record<string, Record<string, any>>>({})

// 版本号：工具 id → 递增计数。后端每次返回新设置后 +1，供 watch 使用
export const revision = reactive<Record<string, number>>({})

// 递增某个工具的版本号，标记“设置已更新”
function bump(tool: string) {
  revision[tool] = (revision[tool] ?? 0) + 1
}

// 从后端加载某工具的设置并写入缓存（启动、切换工具、导入后都会用到）
export async function loadSettings(tool: string): Promise<Record<string, any>> {
  const data = await invoke<Record<string, any>>('settings_get', tool)
  settings[tool] = data
  bump(tool)
  return data
}

// 读缓存；还没加载过时返回空对象，避免调用方处理 undefined
export function getSettings(tool: string): Record<string, any> {
  return settings[tool] ?? {}
}

// 把整份设置交给后端校验并保存，成功后用后端返回的规范化结果覆盖缓存
export async function saveSettings(
  tool: string,
  values: Record<string, any>,
): Promise<Record<string, any>> {
  const saved = await invoke<Record<string, any>>('settings_save', tool, values)
  settings[tool] = saved
  bump(tool)
  return saved
}

// 恢复默认设置：后端按 schema 的 default 重新生成，再覆盖缓存
export async function resetSettings(tool: string): Promise<Record<string, any>> {
  const data = await invoke<Record<string, any>>('settings_reset', tool)
  settings[tool] = data
  bump(tool)
  return data
}

// 深拷贝（JSON 往返）：把缓存复制成可随意编辑的草稿，避免改到缓存里的原对象
export function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}
