<script setup lang="ts">
import { computed, defineAsyncComponent, onMounted, onUnmounted, ref } from 'vue'

import { invoke, waitReady } from './platform/bridge'
import { languages, locale, setLocale, t } from './platform/i18n'
import { settings as settingsCache, loadSettings } from './platform/settings'
import { applyTheme, theme, toggleTheme } from './platform/theme'
import { notify, notifyError } from './platform/toast'
import { viewFor } from './platform/tools'
import type { AppState, ToolDef } from './platform/types'
import AboutDialog from './shell/AboutDialog.vue'
import SettingsDrawer from './shell/SettingsDrawer.vue'
import ToastHost from './ui/ToastHost.vue'

const state = ref<AppState | null>(null)
const bootError = ref('')
const activeId = ref('')
const drawer = ref(false)
const aboutOpen = ref(false)

const viewCache = new Map<string, ReturnType<typeof defineAsyncComponent>>()

function componentFor(id: string) {
  if (!viewCache.has(id)) {
    const loader = viewFor(id)
    if (loader) viewCache.set(id, defineAsyncComponent(loader as never))
  }
  return viewCache.get(id) ?? null
}

const activeTool = computed<ToolDef | null>(
  () => state.value?.tools.find((tool) => tool.id === activeId.value) ?? null,
)
const activeComponent = computed(() => (activeId.value ? componentFor(activeId.value) : null))

const ICONS: Record<string, string> = {
  pearl: '<circle cx="12" cy="12" r="7" fill="none" stroke="currentColor" stroke-width="1.8"/><circle cx="9" cy="9" r="1.6" fill="currentColor"/><circle cx="15" cy="13" r="1.1" fill="currentColor"/>',
  border: '<rect x="4" y="4" width="16" height="16" rx="3" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M8 15 L12 8 L16 15" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>',
  spark: '<path d="M12 3 L14 9 L20 11 L14 13 L12 19 L10 13 L4 11 L10 9 Z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/>',
  gear: '<circle cx="12" cy="12" r="3.4" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M18.4 5.6l-2.1 2.1M7.7 16.3l-2.1 2.1" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>',
  info: '<circle cx="12" cy="12" r="8.6" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M12 11v5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><circle cx="12" cy="8" r="1.1" fill="currentColor"/>',
  clock: '<circle cx="12" cy="12" r="8.6" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M12 7.2v5l3.2 1.9" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
}

function icon(name: string): string {
  return ICONS[name] ?? ICONS.spark
}

const languageLabels: Record<string, string> = {
  zh_CN: '简体中文',
  zh_TW: '繁體中文',
  en: 'English',
}

async function selectTool(id: string) {
  if (!state.value?.tools.some((tool) => tool.id === id)) return
  activeId.value = id
  if (!settingsCache[id]) {
    try {
      await loadSettings(id)
    } catch (error) {
      notifyError(error)
    }
  }
  void invoke('app_set_pref', 'lastTool', id).catch(() => undefined)
}

async function changeLanguage(event: Event) {
  const value = (event.target as HTMLSelectElement).value
  setLocale(value)
  try {
    await invoke('app_set_pref', 'language', value)
  } catch (error) {
    notifyError(error)
  }
}

async function onToggleTheme() {
  const next = toggleTheme()
  try {
    await invoke('app_set_pref', 'theme', next)
  } catch (error) {
    notifyError(error)
  }
}

function onKeydown(event: KeyboardEvent) {
  if (!state.value) return
  if (event.ctrlKey && event.key >= '1' && event.key <= '9') {
    const index = Number(event.key) - 1
    const tool = state.value.tools[index]
    if (tool) {
      event.preventDefault()
      void selectTool(tool.id)
    }
  }
  if (event.ctrlKey && event.key === ',') {
    event.preventDefault()
    drawer.value = true
  }
  if (event.key === 'Escape') {
    drawer.value = false
    aboutOpen.value = false
  }
}

onMounted(async () => {
  try {
    await waitReady()
    const data = await invoke<AppState>('app_state')
    state.value = data
    setLocale(data.language)
    applyTheme(data.theme === 'light' ? 'light' : 'dark')
    const preferred = data.tools.find((tool) => tool.id === data.lastTool)
    await selectTool(preferred?.id ?? data.tools[0]?.id ?? '')
  } catch (error) {
    bootError.value = error instanceof Error ? error.message : String(error)
  }
  window.addEventListener('keydown', onKeydown)
})

onUnmounted(() => window.removeEventListener('keydown', onKeydown))
</script>

<template>
  <div v-if="state && activeTool" class="app">
    <aside class="rail">
      <div class="mark" :title="t('app.name')">◆</div>
      <button
        v-for="tool in state.tools"
        :key="tool.id"
        class="rail-item"
        :class="{ active: tool.id === activeId }"
        :title="t(tool.nameKey)"
        @click="selectTool(tool.id)"
      >
        <svg viewBox="0 0 24 24" class="rail-icon" v-html="icon(tool.icon)" />
        <span class="rail-label">{{ t(tool.nameKey) }}</span>
      </button>

      <button
        class="rail-item coming"
        type="button"
        :title="t('nav.comingSoon')"
        @click="notify('info', t('nav.comingSoonHint'))"
      >
        <svg viewBox="0 0 24 24" class="rail-icon" v-html="icon('clock')" />
        <span class="rail-label">{{ t('nav.comingSoon') }}</span>
      </button>

      <div class="rail-spacer" />
      <button class="rail-item" :title="t('nav.about')" @click="aboutOpen = true">
        <svg viewBox="0 0 24 24" class="rail-icon" v-html="icon('info')" />
        <span class="rail-label">{{ t('nav.about') }}</span>
      </button>
    </aside>

    <div class="main">
      <header class="cmdbar">
        <div class="titles">
          <strong>{{ t(activeTool.nameKey) }}</strong>
          <span class="muted">{{ t(activeTool.descriptionKey) }}</span>
        </div>
        <div class="cmd-actions">
          <span class="badge">v{{ state.version }}</span>
          <select class="input lang" :value="locale" @change="changeLanguage">
            <option v-for="lang in languages" :key="lang" :value="lang">
              {{ languageLabels[lang] ?? lang }}
            </option>
          </select>
          <button class="btn ghost" :title="t('nav.theme')" @click="onToggleTheme">
            {{ theme === 'dark' ? '☾' : '☀' }}
          </button>
          <button class="btn ghost settings-btn" :title="t('nav.settings')" @click="drawer = true">
            ⚙
          </button>
        </div>
      </header>

      <main class="workspace">
        <component :is="activeComponent" v-if="activeComponent" :key="activeId" :tool="activeTool" />
        <div v-else class="panel">
          <div class="empty">{{ t('app.noView') }}</div>
        </div>
      </main>
    </div>

    <SettingsDrawer v-if="drawer" :tool="activeTool" @close="drawer = false" />
    <AboutDialog v-if="aboutOpen" :version="state.version" @close="aboutOpen = false" />
    <ToastHost />
  </div>

  <div v-else class="boot">
    <div class="boot-card">
      <div class="boot-title">LSP PlayerKit</div>
      <div class="muted">{{ bootError || t('app.loading') }}</div>
    </div>
  </div>
</template>

<style scoped>
.app {
  display: flex;
  height: 100vh;
  overflow: hidden;
}

.rail {
  width: 88px;
  flex: 0 0 88px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 12px 8px;
  background: var(--surface);
  border-right: 1px solid var(--line);
}

.mark {
  width: 34px;
  height: 34px;
  display: grid;
  place-items: center;
  margin-bottom: 10px;
  border-radius: 10px;
  background: var(--brand-soft);
  color: var(--brand);
  font-size: 16px;
}

.rail-item {
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 5px;
  padding: 9px 4px;
  border: 1px solid transparent;
  border-radius: 10px;
  background: transparent;
  color: var(--muted);
  cursor: pointer;
}

.rail-item:hover {
  background: var(--surface-2);
  color: var(--text);
}

.rail-item.active {
  background: var(--surface-2);
  border-color: var(--line-strong);
  color: var(--brand);
}

.rail-item.coming {
  border-style: dashed;
  border-color: var(--line-strong);
  opacity: 0.65;
}

.rail-item.coming:hover {
  opacity: 1;
  color: var(--muted);
}

.rail-icon {
  width: 22px;
  height: 22px;
}

.rail-label {
  font-size: 10px;
  line-height: 1.2;
  text-align: center;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
}

.rail-spacer {
  flex: 1;
}

.main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.cmdbar {
  height: 56px;
  flex: 0 0 56px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 0 16px;
  border-bottom: 1px solid var(--line);
  background: var(--surface);
}

.titles {
  display: flex;
  align-items: baseline;
  gap: 10px;
  min-width: 0;
}

.titles strong {
  font-size: 14px;
}

.titles .muted {
  font-size: 12px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.cmd-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.lang {
  width: 118px;
  height: 30px;
}

.workspace {
  flex: 1;
  min-height: 0;
  min-width: 0;
  padding: 14px;
  overflow: hidden;
}

.boot {
  height: 100vh;
  display: grid;
  place-items: center;
}

.boot-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  align-items: center;
}

.boot-title {
  font-size: 18px;
  letter-spacing: 0.08em;
  color: var(--brand);
}
</style>
