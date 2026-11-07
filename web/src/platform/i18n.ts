/**
 * 多语言（i18n）模块
 *
 * 负责把外壳与各工具的 JSON 词典按语言合并成内存表，并提供 t() 取文案、
 * setLocale() 切语言。
 * 词典来源（构建时由 Vite 的 import.meta.glob 收集，无需手工 import）：
 * - web/src/i18n/*.json：外壳文案（应用名、导航、设置抽屉、关于等）；
 * - web/src/tools/<id>/i18n/*.json：各工具自己的文案。
 * 文件名即语言代码（如 zh_CN.json → zh_CN），两种来源按语言合并。
 *
 * 交互关系：
 * - App.vue 启动时用后端返回的 language 调 setLocale，并渲染语言下拉框；
 * - 所有组件的 t(key) 都走这里；当前语言变化会让依赖 locale 的模板重新渲染。
 */

import { computed, ref } from 'vue'

// 一套词典：键为文案 key，值为对应语言的文本
type Dict = Record<string, string>

// eager: true 表示构建时就把所有 JSON 打进包里，而不是按需异步加载
// 外壳词典：../i18n/*.json（相对本文件，即 web/src/i18n/）
const shellModules = import.meta.glob('../i18n/*.json', { eager: true }) as Record<string, any>
// 工具词典：../tools/*/i18n/*.json，每个工具可以有自己的一套 json
const toolModules = import.meta.glob('../tools/*/i18n/*.json', { eager: true }) as Record<string, any>

// 合并后的词典表：语言代码 → 该语言的全部 key
const messages: Record<string, Dict> = {}

// 把一份词典并入指定语言；同名 key 后写入的覆盖先写入的（工具词典可覆盖外壳词典）
function merge(lang: string, dict: Dict) {
  messages[lang] = { ...(messages[lang] ?? {}), ...dict }
}

// 先合并外壳词典：path 形如 ../i18n/zh_CN.json，取文件名去掉 .json 得到语言代码
for (const [path, mod] of Object.entries(shellModules)) {
  const lang = path.split('/').pop()?.replace('.json', '') ?? 'zh_CN'
  // JSON 模块在 Vite 里可能有 default 包装，两种形态都兼容
  merge(lang, (mod.default ?? mod) as Dict)
}
// 再合并各工具词典（结构相同，key 前缀通常是工具 id，避免冲突）
for (const [path, mod] of Object.entries(toolModules)) {
  const lang = path.split('/').pop()?.replace('.json', '') ?? 'zh_CN'
  merge(lang, (mod.default ?? mod) as Dict)
}

// 当前语言，默认简体中文；组件模板里读取它会建立响应式依赖
export const locale = ref('zh_CN')
// 可选语言列表：直接取词典表里的语言代码并排序
export const languages = computed(() => Object.keys(messages).sort())

/**
 * 取文案：按 key 在当前语言里查找，找不到时回退到简体中文，再找不到返回 key 本身。
 * params 用于简单的占位符替换，如 t('x', { n: 3 }) 会把文案里的 {n} 换成 3。
 */
export function t(key: string, params?: Record<string, string | number>): string {
  const dict = messages[locale.value] ?? {}
  // 两级回退：当前语言 → 简体中文 → 原样返回 key（便于发现漏翻）
  let text = dict[key] ?? messages.zh_CN?.[key] ?? key
  if (params) {
    for (const [name, value] of Object.entries(params)) {
      text = text.replaceAll(`{${name}}`, String(value))
    }
  }
  return text
}

// 切换语言：只有词典里存在的语言才生效；同时同步 <html lang>（zh_CN → zh-CN）
export function setLocale(lang: string): void {
  if (!messages[lang]) return
  locale.value = lang
  document.documentElement.lang = lang.replace('_', '-')
}

// 判断某语言是否已有词典（可用于校验外部传入的语言代码）
export function hasLanguage(lang: string): boolean {
  return Boolean(messages[lang])
}
