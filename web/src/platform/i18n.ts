import { computed, ref } from 'vue'

type Dict = Record<string, string>

const shellModules = import.meta.glob('../i18n/*.json', { eager: true }) as Record<string, any>
const toolModules = import.meta.glob('../tools/*/i18n/*.json', { eager: true }) as Record<string, any>

const messages: Record<string, Dict> = {}

function merge(lang: string, dict: Dict) {
  messages[lang] = { ...(messages[lang] ?? {}), ...dict }
}

for (const [path, mod] of Object.entries(shellModules)) {
  const lang = path.split('/').pop()?.replace('.json', '') ?? 'zh_CN'
  merge(lang, (mod.default ?? mod) as Dict)
}
for (const [path, mod] of Object.entries(toolModules)) {
  const lang = path.split('/').pop()?.replace('.json', '') ?? 'zh_CN'
  merge(lang, (mod.default ?? mod) as Dict)
}

export const locale = ref('zh_CN')
export const languages = computed(() => Object.keys(messages).sort())

export function t(key: string, params?: Record<string, string | number>): string {
  const dict = messages[locale.value] ?? {}
  let text = dict[key] ?? messages.zh_CN?.[key] ?? key
  if (params) {
    for (const [name, value] of Object.entries(params)) {
      text = text.replaceAll(`{${name}}`, String(value))
    }
  }
  return text
}

export function setLocale(lang: string): void {
  if (!messages[lang]) return
  locale.value = lang
  document.documentElement.lang = lang.replace('_', '-')
}

export function hasLanguage(lang: string): boolean {
  return Boolean(messages[lang])
}
