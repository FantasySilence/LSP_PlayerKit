<!--
  App.vue —— 应用外壳（整页布局与全局交互）

  负责：
  - 启动时通过 pywebview 桥向后端索取 app_state（版本、语言、主题、
    上次使用的工具、工具清单以及数据目录信息）；
  - 左侧工具轨（rail）：列出所有工具，点击切换当前工具；
  - 顶部命令栏（cmdbar）：显示当前工具名称/描述、版本、语言切换、
    主题切换与设置入口；
  - 中间工作区（workspace）：按当前工具 id 动态渲染对应 View；
  - 设置抽屉、关于弹窗与 Toast 容器；
  - 全局快捷键：Ctrl+1..9 切换工具、Ctrl+, 打开设置、Esc 关闭浮层。

  交互关系：
  - platform/bridge.ts 提供 invoke（调后端方法）与 waitReady（等桥就绪）；
  - platform/tools.ts 的 viewFor(id) 按 id 找到工具视图的懒加载函数；
  - platform/i18n.ts、theme.ts、settings.ts、toast.ts 分别管理文案、主题、
    设置缓存与提示消息；
  - shell/SettingsDrawer.vue、shell/AboutDialog.vue、ui/ToastHost.vue
    是本文件直接引用的子组件。
-->

<script setup lang="ts">
// 组合式 API：响应式状态、计算属性、生命周期钩子与异步组件包装
import { computed, defineAsyncComponent, onMounted, onUnmounted, ref } from 'vue'

// 平台层：与 Python 后端通信、i18n、设置缓存、主题、提示与工具视图解析
import { invoke, waitReady } from './platform/bridge'
import { languages, locale, setLocale, t } from './platform/i18n'
// 这里的 settings 是全局设置缓存（按工具 id 存放），为避免同名冲突重命名为 settingsCache
import { settings as settingsCache, loadSettings } from './platform/settings'
import { applyTheme, theme, toggleTheme } from './platform/theme'
import { notify, notifyError } from './platform/toast'
import { viewFor } from './platform/tools'
import type { AppState, ToolDef } from './platform/types'
// 子组件：设置抽屉、关于弹窗、Toast 容器
import AboutDialog from './shell/AboutDialog.vue'
import SettingsDrawer from './shell/SettingsDrawer.vue'
import ToastHost from './ui/ToastHost.vue'

// ------ 状态 ------ //

// 后端返回的应用状态；null 表示还在启动或启动失败
const state = ref<AppState | null>(null)
// 启动失败时的错误文案，会代替加载提示显示在启动卡片里
const bootError = ref('')
// 当前选中的工具 id；空串表示尚未选择
const activeId = ref('')
// 设置抽屉是否打开（从右侧滑出）
const drawer = ref(false)
// 关于弹窗是否打开
const aboutOpen = ref(false)

// 已创建的异步组件缓存：同一工具只解析一次，切回来时不必重新加载
const viewCache = new Map<string, ReturnType<typeof defineAsyncComponent>>()

// ------ 工具视图解析 ------ //

// 按工具 id 取得（并缓存）对应的异步组件；该 id 没有视图时返回 null
function componentFor(id: string) {
  if (!viewCache.has(id)) {
    // viewFor 来自 platform/tools.ts：用 import.meta.glob 收集所有工具 View.vue
    const loader = viewFor(id)
    // 懒加载函数包装成 Vue 异步组件：只有真正渲染时才会去加载这个文件
    if (loader) viewCache.set(id, defineAsyncComponent(loader as never))
  }
  return viewCache.get(id) ?? null
}

// ------ 计算属性 ------ //

// 从工具清单里找出当前工具定义（名称、图标、设置 schema 等）
const activeTool = computed<ToolDef | null>(
  () => state.value?.tools.find((tool) => tool.id === activeId.value) ?? null,
)
// 当前工具对应的组件；没有选中工具时为空，工作区显示占位提示
const activeComponent = computed(() => (activeId.value ? componentFor(activeId.value) : null))

// ------ 图标与语言标签 ------ //

// 工具图标库：值是 24x24 viewBox 内的 SVG 片段，模板里通过 v-html 注入
const ICONS: Record<string, string> = {
  pearl: '<circle cx="12" cy="12" r="7" fill="none" stroke="currentColor" stroke-width="1.8"/><circle cx="9" cy="9" r="1.6" fill="currentColor"/><circle cx="15" cy="13" r="1.1" fill="currentColor"/>',
  border: '<rect x="4" y="4" width="16" height="16" rx="3" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M8 15 L12 8 L16 15" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>',
  box: '<path d="M12 3 L20 7.5 V16.5 L12 21 L4 16.5 V7.5 Z" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/><path d="M4 7.5 L12 12 L20 7.5 M12 12 V21" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/>',
  spark: '<path d="M12 3 L14 9 L20 11 L14 13 L12 19 L10 13 L4 11 L10 9 Z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/>',
  route: '<circle cx="5.5" cy="18.5" r="2.4" fill="none" stroke="currentColor" stroke-width="1.8"/><circle cx="18.5" cy="5.5" r="2.4" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M7.9 18.5h5.6a3.2 3.2 0 0 0 0-6.4h-3a3.2 3.2 0 0 1 0-6.4h5.5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
  slime: '<path d="M12 4c-3.6 0-6.6 2.6-6.6 6 0 1.3.4 2.5 1.1 3.5-1 .8-1.7 2-1.7 3.4 0 2.4 1.9 4.3 4.3 4.3h6.4c2.4 0 4.3-1.9 4.3-4.3 0-1.4-.6-2.6-1.7-3.4.7-1 1.1-2.2 1.1-3.5 0-3.4-3-6-6.6-6Z" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/><circle cx="9.6" cy="11" r="1.1" fill="currentColor"/><circle cx="14.4" cy="11" r="1.1" fill="currentColor"/>',
  gear: '<circle cx="12" cy="12" r="3.4" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M18.4 5.6l-2.1 2.1M7.7 16.3l-2.1 2.1" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>',
  info: '<circle cx="12" cy="12" r="8.6" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M12 11v5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><circle cx="12" cy="8" r="1.1" fill="currentColor"/>',
  clock: '<circle cx="12" cy="12" r="8.6" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M12 7.2v5l3.2 1.9" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
}

// 取图标片段；后端下发了未登记的图标名时回退到 spark（星星）
function icon(name: string): string {
  return ICONS[name] ?? ICONS.spark
}

// 语言代码 → 下拉框里的显示名；不在表里的代码直接显示代码本身
const languageLabels: Record<string, string> = {
  zh_CN: '简体中文',
  zh_TW: '繁體中文',
  en: 'English',
}

// ------ 事件处理 ------ //

// 切换工具：校验 id、更新选中项、按需加载该工具设置，并记住上次选择
async function selectTool(id: string) {
  // 只接受工具清单里存在的 id，避免非法值污染状态
  if (!state.value?.tools.some((tool) => tool.id === id)) return
  activeId.value = id
  // 设置缓存里没有该工具时再向后端取，避免每次切换都请求
  if (!settingsCache[id]) {
    try {
      await loadSettings(id)
    } catch (error) {
      notifyError(error)
    }
  }
  // 把“上次使用的工具”写回后端偏好；失败不影响界面，所以静默忽略
  void invoke('app_set_pref', 'lastTool', id).catch(() => undefined)
}

// 语言下拉框变化：先立即切换前端文案，再把偏好写回后端
async function changeLanguage(event: Event) {
  const value = (event.target as HTMLSelectElement).value
  setLocale(value)
  try {
    await invoke('app_set_pref', 'language', value)
  } catch (error) {
    notifyError(error)
  }
}

// 主题按钮：toggleTheme 会立即切换并返回新主题，再把偏好写回后端
async function onToggleTheme() {
  const next = toggleTheme()
  try {
    await invoke('app_set_pref', 'theme', next)
  } catch (error) {
    notifyError(error)
  }
}

// 全局快捷键（onMounted 时注册到 window，onUnmounted 时移除）
// Ctrl+1..9：按工具清单顺序切换到第 1..9 个工具
// Ctrl+,：打开设置抽屉
// Esc：关闭设置抽屉与关于弹窗
function onKeydown(event: KeyboardEvent) {
  if (!state.value) return
  // event.key 是字符 '1'..'9'，转成数字后减 1 得到清单下标
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

// ------ 生命周期 ------ //

// 挂载后启动：等桥就绪 → 取应用状态 → 应用语言/主题 → 恢复上次工具 → 注册快捷键
onMounted(async () => {
  try {
    // 等待 pywebview 注入 window.pywebview.api；超时会抛 BridgeError
    await waitReady()
    // app_state 返回 AppState：版本、语言、主题、上次工具、工具清单、数据目录
    const data = await invoke<AppState>('app_state')
    state.value = data
    // 后端语言代码形如 zh_CN；setLocale 会同步 <html lang>
    setLocale(data.language)
    // 主题只接受 light/dark，其他值一律回落到 dark
    applyTheme(data.theme === 'light' ? 'light' : 'dark')
    // 优先恢复上次使用的工具；找不到就退回清单第一个；都没有则传空串
    const preferred = data.tools.find((tool) => tool.id === data.lastTool)
    await selectTool(preferred?.id ?? data.tools[0]?.id ?? '')
  } catch (error) {
    // 启动阶段的失败直接显示在启动卡片上，不弹 Toast
    bootError.value = error instanceof Error ? error.message : String(error)
  }
  // 无论启动是否成功都注册快捷键；启动失败时 onKeydown 会因 state 为空直接返回
  window.addEventListener('keydown', onKeydown)
})

// 卸载时移除全局监听，避免离开页面后仍然响应按键
onUnmounted(() => window.removeEventListener('keydown', onKeydown))
</script>

<template>
  <!-- 外壳整体：左侧工具轨 + 右侧主区域；state 与 activeTool 都就绪后才渲染 -->
  <div v-if="state && activeTool" class="app">
    <!-- 区块：工具轨（品牌标记、工具按钮、占位入口、关于入口） -->
    <aside class="rail">
      <!-- 品牌标记 -->
      <div class="mark" :title="t('app.name')">◆</div>
      <!-- 遍历后端下发的工具清单（已按 order 升序）；点击即切换当前工具 -->
      <button
        v-for="tool in state.tools"
        :key="tool.id"
        class="rail-item"
        :class="{ active: tool.id === activeId }"
        :title="t(tool.nameKey)"
        @click="selectTool(tool.id)"
      >
        <!-- icon(tool.icon) 返回 SVG 片段，用 v-html 注入到 24x24 视口 -->
        <svg viewBox="0 0 24 24" class="rail-icon" v-html="icon(tool.icon)" />
        <span class="rail-label">{{ t(tool.nameKey) }}</span>
      </button>

      <!-- 尚未实现的工具占位：点击只弹一条提示，不切换视图 -->
      <button
        class="rail-item coming"
        type="button"
        :title="t('nav.comingSoon')"
        @click="notify('info', t('nav.comingSoonHint'))"
      >
        <svg viewBox="0 0 24 24" class="rail-icon" v-html="icon('clock')" />
        <span class="rail-label">{{ t('nav.comingSoon') }}</span>
      </button>

      <!-- 弹性占位：把下面的“关于”按钮推到工具轨底部 -->
      <div class="rail-spacer" />
      <!-- 关于入口：点击打开 AboutDialog -->
      <button class="rail-item" :title="t('nav.about')" @click="aboutOpen = true">
        <svg viewBox="0 0 24 24" class="rail-icon" v-html="icon('info')" />
        <span class="rail-label">{{ t('nav.about') }}</span>
      </button>
    </aside>

    <!-- 区块：主区域（命令栏 + 工作区） -->
    <div class="main">
      <!-- 区块：命令栏（当前工具标题/描述、版本、语言、主题、设置） -->
      <header class="cmdbar">
        <div class="titles">
          <strong>{{ t(activeTool.nameKey) }}</strong>
          <span class="muted">{{ t(activeTool.descriptionKey) }}</span>
        </div>
        <div class="cmd-actions">
          <!-- 后端下发的应用版本号 -->
          <span class="badge">v{{ state.version }}</span>
          <!-- 语言下拉：选项来自 i18n 已加载的词典；切换后写回后端偏好 -->
          <select class="input lang" :value="locale" @change="changeLanguage">
            <option v-for="lang in languages" :key="lang" :value="lang">
              {{ languageLabels[lang] ?? lang }}
            </option>
          </select>
          <!-- 主题按钮：按当前主题显示月亮或太阳，点击切换并保存偏好 -->
          <button class="btn ghost" :title="t('nav.theme')" @click="onToggleTheme">
            {{ theme === 'dark' ? '☾' : '☀' }}
          </button>
          <!-- 设置按钮：打开右侧 schema 驱动的设置抽屉 -->
          <button class="btn ghost settings-btn" :title="t('nav.settings')" @click="drawer = true">
            ⚙
          </button>
        </div>
      </header>

      <!-- 区块：工作区（按当前工具 id 懒加载 View，并通过 props 注入 tool 定义） -->
      <main class="workspace">
        <!-- key=activeId：切换工具时销毁旧视图、重建新视图 -->
        <component :is="activeComponent" v-if="activeComponent" :key="activeId" :tool="activeTool" />
        <div v-else class="panel">
          <!-- 当前工具没有登记 View.vue 时的兜底提示 -->
          <div class="empty">{{ t('app.noView') }}</div>
        </div>
      </main>
    </div>

    <!-- 区块：浮层（设置抽屉与关于弹窗按需渲染，Toast 容器常驻） -->
    <SettingsDrawer v-if="drawer" :tool="activeTool" @close="drawer = false" />
    <AboutDialog v-if="aboutOpen" :version="state.version" @close="aboutOpen = false" />
    <ToastHost />
  </div>

  <div v-else class="boot">
    <!-- 启动中或启动失败：整页启动卡片，bootError 非空时显示失败原因 -->
    <div class="boot-card">
      <div class="boot-title">LSP PlayerKit</div>
      <div class="muted">{{ bootError || t('app.loading') }}</div>
    </div>
  </div>
</template>

<style scoped>
/* 区块：整体布局（左右两栏，占满视口） */
.app {
  display: flex;
  height: 100vh;
  overflow: hidden;
}

/* 区块：左侧工具轨 */
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

/* 图标与文字标签 */
.rail-icon {
  width: 22px;
  height: 22px;
}

.rail-label {
  font-size: 10px;
  line-height: 1.25;
  text-align: center;
  max-width: 100%;
  overflow-wrap: break-word;
}

/* 弹性占位：把“关于”按钮推到工具轨底部 */
.rail-spacer {
  flex: 1;
}

/* 区块：右侧主区域（命令栏在上，工作区占满剩余空间） */
.main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

/* 区块：命令栏（固定高度，左右两端对齐） */
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

/* 左侧标题与描述；描述过长时省略号截断 */
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

/* 语言下拉框宽度固定，避免切换语言时命令栏抖动 */
.lang {
  width: 118px;
  height: 30px;
}

/* 区块：工作区（占满剩余高度，内部视图自行滚动） */
.workspace {
  flex: 1;
  min-height: 0;
  min-width: 0;
  padding: 14px;
  overflow: hidden;
}

/* 区块：启动卡片（加载中 / 启动失败） */
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
