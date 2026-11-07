<!--
  SettingsDrawer.vue —— 设置抽屉（schema 驱动）

  负责：从右侧滑出的设置面板，包含三个标签页：
  - 工具参数：按当前工具 settingsSchema 的 groups/fields 动态渲染表单；
  - 数据与存储：显示当前数据目录，提供更改位置、打开目录、导入导出配置包；
  - 关于：显示版本、简介与“打开说明文件”。

  表单是 schema 驱动的：字段类型 int/float 渲染数字输入框，bool 渲染勾选框，
  enum 渲染下拉框，string 渲染文本框，path 渲染文本框 + “选择目录”按钮；
  字段的 label/unit/hint/options/step/digits 等元数据都来自后端 FieldDef，
  抽屉不写死任何字段；min/max 的范围校验由后端在保存时完成。

  交互关系：
  - 由 App.vue 在打开设置时渲染，props.tool 是当前 ToolDef，关闭时 emit('close')；
  - 通过 platform/bridge.ts 的 invoke 调后端 settings_* / storage_* / open_manual；
  - 读写 platform/settings.ts 的全局缓存，用 clone 复制草稿；
  - 提示与错误交给 platform/toast.ts。
-->

<script setup lang="ts">
// 组合式 API：computed 派生显示文案，watch 跟随工具切换，onMounted 做首次加载
import { computed, onMounted, reactive, ref, watch } from 'vue'

import { invoke } from '../platform/bridge'
import { locale, t } from '../platform/i18n'
// 设置缓存与深拷贝工具；settings 直接读缓存，clone 用于生成可编辑的草稿
import { clone, loadSettings, resetSettings, saveSettings, settings } from '../platform/settings'
import { notify, notifyError } from '../platform/toast'
import type { FieldDef, StorageInfo, ToolDef } from '../platform/types'

// ------ props / emits ------ //

// tool：当前工具的完整定义，设置表单完全由它的 settingsSchema 决定
const props = defineProps<{ tool: ToolDef }>()
// 关闭抽屉：由 App.vue 监听后把 drawer 置回 false
const emit = defineEmits<{ (e: 'close'): void }>()

// ------ 状态 ------ //

// 当前标签页，默认打开“工具参数”
const tab = ref<'tool' | 'storage' | 'about'>('tool')
// 表单草稿：编辑期间只改这里，点保存才写回后端
const draft = reactive<Record<string, any>>({})
// 保存中标记：保存期间禁用保存按钮，避免重复提交
const saving = ref(false)
// “重置”二次确认标记：第一次点击只是进入确认状态，3 秒内再点才真正重置
const resetArmed = ref(false)
// 数据目录信息（存储页展示），未加载时为 null
const storage = ref<StorageInfo | null>(null)

// ------ 草稿读写 ------ //

// 用一份设置覆盖草稿：先清空旧键，再深拷贝传入对象，避免残留已删除的字段
function syncDraft(source: Record<string, any>) {
  Object.keys(draft).forEach((key) => delete draft[key])
  Object.assign(draft, clone(source))
}

// 按点号路径读草稿里的值（字段 key 支持 flat.xzMotion 这样的嵌套）
function read(path: string): any {
  return path.split('.').reduce<any>((node, key) => (node == null ? undefined : node[key]), draft)
}

// 按点号路径写值：中间层不存在或不是对象时自动补一个空对象
function write(path: string, value: unknown) {
  const parts = path.split('.')
  let node: any = draft
  for (const part of parts.slice(0, -1)) {
    if (typeof node[part] !== 'object' || node[part] === null) node[part] = {}
    node = node[part]
  }
  node[parts[parts.length - 1]] = value
}

// ------ 表单事件（按字段类型分流） ------ //

// 数字输入：空串写成 null，由后端按字段类型校验；其他情况转为 Number
function onNumber(field: FieldDef, event: Event) {
  const raw = (event.target as HTMLInputElement).value
  write(field.key, raw === '' ? null : Number(raw))
}

// 勾选框：读写 checked
function onBool(field: FieldDef, event: Event) {
  write(field.key, (event.target as HTMLInputElement).checked)
}

// 下拉框：取选中项的 value
function onEnum(field: FieldDef, event: Event) {
  write(field.key, (event.target as HTMLSelectElement).value)
}

// 文本框（string / path 的输入框）：原样写入字符串
function onText(field: FieldDef, event: Event) {
  write(field.key, (event.target as HTMLInputElement).value)
}

// path 字段的“选择…”按钮：调后端打开系统目录选择框，返回 null 表示用户取消
async function pickPath(field: FieldDef) {
  try {
    const path = await invoke<string | null>('storage_pick_dir')
    if (!path) return
    write(field.key, path)
  } catch (error) {
    notifyError(error)
  }
}

// 数字输入框的步长：优先用后端给的 step；int 默认 1，float 按位数取最小步长
const stepFor = (field: FieldDef) =>
  field.step ?? (field.type === 'int' ? 1 : Math.pow(10, -Math.min(field.digits, 6)))

// ------ 保存 / 重置 / 导入 ------ //

// 保存：把草稿深拷贝后交给后端校验并持久化，再用后端返回的结果刷新草稿
async function save() {
  saving.value = true
  try {
    const saved = await saveSettings(props.tool.id, clone(draft))
    syncDraft(saved)
    notify('success', t('settings.saved'))
  } catch (error) {
    notifyError(error)
  } finally {
    saving.value = false
  }
}

// 重置：需要点击两次（3 秒内）确认；确认后由后端按 schema 默认值重写
async function reset() {
  if (!resetArmed.value) {
    resetArmed.value = true
    window.setTimeout(() => (resetArmed.value = false), 3000)
    return
  }
  resetArmed.value = false
  try {
    const data = await resetSettings(props.tool.id)
    syncDraft(data)
    notify('success', t('settings.resetDone'))
  } catch (error) {
    notifyError(error)
  }
}

// 从 JSON 文件导入配置：后端弹文件选择框并返回 values，再走一次保存
async function importFile() {
  try {
    const result = await invoke<{
      cancelled?: boolean
      values?: Record<string, any>
      migrated?: boolean
    }>('settings_import_file', props.tool.id)
    if (!result || result.cancelled) return
    const values = result.values ?? {}
    const saved = await saveSettings(props.tool.id, values)
    syncDraft(saved)
    // migrated 表示文件来自旧版格式，后端已做过字段迁移
    notify('success', result.migrated ? t('settings.importedLegacy') : t('settings.imported'))
  } catch (error) {
    notifyError(error)
  }
}

// ------ 数据目录 ------ //

// 读取当前数据目录信息
async function refreshStorage() {
  try {
    storage.value = await invoke<StorageInfo>('storage_info')
  } catch (error) {
    notifyError(error)
  }
}

// 更改数据目录：选目录 → 后端切换 → 重新加载设置（目录变了，设置文件也可能变了）
async function changeDir() {
  try {
    const path = await invoke<string | null>('storage_pick_dir')
    if (!path) return
    storage.value = await invoke<StorageInfo>('storage_set_dir', path)
    await loadSettings(props.tool.id)
    syncDraft(settings[props.tool.id] ?? {})
    notify('success', t('storage.changed'))
  } catch (error) {
    notifyError(error)
  }
}

// 恢复默认数据目录（同样要重新加载设置）
async function resetDir() {
  try {
    storage.value = await invoke<StorageInfo>('storage_reset')
    await loadSettings(props.tool.id)
    syncDraft(settings[props.tool.id] ?? {})
    notify('success', t('storage.changed'))
  } catch (error) {
    notifyError(error)
  }
}

// 在系统文件管理器里打开数据目录
async function openDir() {
  try {
    await invoke('storage_open_dir')
  } catch (error) {
    notifyError(error)
  }
}

// 导出配置包：后端弹保存框生成 zip；取消时返回 cancelled
async function exportBundle() {
  try {
    const result = await invoke<{ cancelled?: boolean; path?: string }>('storage_export_bundle')
    if (!result || result.cancelled) return
    // detail 传导出路径，显示在提示的第二行
    notify('success', t('storage.exported'), result.path)
  } catch (error) {
    notifyError(error)
  }
}

// 导入配置包：后端解压并写回 settings/，然后重新加载当前工具设置
async function importBundle() {
  try {
    const result = await invoke<{ cancelled?: boolean; imported?: string[] }>(
      'storage_import_bundle',
    )
    if (!result || result.cancelled) return
    await loadSettings(props.tool.id)
    syncDraft(settings[props.tool.id] ?? {})
    notify('success', t('storage.imported'))
  } catch (error) {
    notifyError(error)
  }
}

// 关于页：按当前语言打开说明文档
async function openDoc() {
  try {
    await invoke('open_manual', locale.value)
  } catch (error) {
    notifyError(error)
  }
}

// ------ 计算属性 ------ //

// 数据目录来源的显示文案：词典里有 storage.source.<source> 各项
const sourceLabel = computed(() => {
  const source = storage.value?.source ?? 'default'
  return t(`storage.source.${source}`)
})

// ------ 生命周期 ------ //

// 挂载时确保设置已加载并同步草稿，随后读取数据目录信息
onMounted(async () => {
  if (!settings[props.tool.id]) {
    try {
      await loadSettings(props.tool.id)
    } catch (error) {
      notifyError(error)
    }
  }
  syncDraft(settings[props.tool.id] ?? {})
  await refreshStorage()
})

// 抽屉打开期间切换工具时，props.tool.id 会变化：按需加载新工具设置并重建草稿
watch(
  () => props.tool.id,
  async (id) => {
    if (!settings[id]) await loadSettings(id)
    syncDraft(settings[id] ?? {})
  },
)
</script>

<template>
  <!-- 遮罩：@click.self 保证只有点到抽屉外的空白处才关闭 -->
  <div class="overlay" @click.self="emit('close')">
    <!-- 区块：设置抽屉 -->
    <aside class="drawer">
      <!-- 区块：抽屉标题栏（标题、当前工具名、关闭按钮） -->
      <header class="drawer-head">
        <div>
          <div class="drawer-title">{{ t('settings.title') }}</div>
          <div class="muted">{{ t(tool.nameKey) }}</div>
        </div>
        <button class="btn ghost" @click="emit('close')">✕</button>
      </header>

      <!-- 区块：标签页切换（工具参数 / 数据与存储 / 关于） -->
      <div class="tabs">
        <button class="tab" :class="{ active: tab === 'tool' }" @click="tab = 'tool'">
          {{ t('settings.tool') }}
        </button>
        <button class="tab" :class="{ active: tab === 'storage' }" @click="tab = 'storage'">
          {{ t('settings.storage') }}
        </button>
        <button class="tab" :class="{ active: tab === 'about' }" @click="tab = 'about'">
          {{ t('settings.about') }}
        </button>
      </div>

      <!-- 区块：抽屉内容，按 tab 显示不同面板 -->
      <div class="drawer-body">
        <template v-if="tab === 'tool'">
          <!-- 区块：工具参数（先遍历 schema 分组，再遍历组内字段） -->
          <section v-for="group in tool.settingsSchema.groups" :key="group.id" class="group">
            <div class="group-title">{{ t(group.label) }}</div>
            <div v-for="field in group.fields" :key="field.key" class="field">
              <label class="field-label">
                <span>{{ t(field.label) }}</span>
                <span v-if="field.unit" class="unit">{{ field.unit.includes('.') ? t(field.unit) : field.unit }}</span>
              </label>

              <!-- 字段控件按 type 分流：enum 下拉、bool 勾选、string/path 文本、其余数字 -->
              <select
                v-if="field.type === 'enum'"
                class="input"
                :value="read(field.key)"
                @change="onEnum(field, $event)"
              >
                <option v-for="option in field.options ?? []" :key="option.value" :value="option.value">
                  {{ t(option.label) }}
                </option>
              </select>

              <label v-else-if="field.type === 'bool'" class="switch">
                <input
                  type="checkbox"
                  :checked="Boolean(read(field.key))"
                  @change="onBool(field, $event)"
                />
                <span>{{ t('settings.enabled') }}</span>
              </label>

              <div v-else-if="field.type === 'string' || field.type === 'path'" class="path-field">
                <input
                  class="input mono"
                  type="text"
                  :value="read(field.key)"
                  @input="onText(field, $event)"
                />
                <!-- path 类型额外提供“选择目录”按钮，调后端打开系统目录选择框 -->
                <button
                  v-if="field.type === 'path'"
                  class="btn sm"
                  @click="pickPath(field)"
                >
                  {{ t('settings.pickDir') }}
                </button>
              </div>

              <input
                v-else
                class="input mono"
                type="number"
                :value="read(field.key)"
                :step="stepFor(field)"
                @input="onNumber(field, $event)"
              />

              <!-- 后端给的字段说明（hint 是 i18n key） -->
              <div v-if="field.hint" class="hint">{{ t(field.hint) }}</div>
            </div>
          </section>

          <!-- 区块：底部操作（保存 / 重置 / 导入配置） -->
          <div class="drawer-actions">
            <button class="btn primary" :disabled="saving" @click="save">{{ t('action.save') }}</button>
            <button class="btn" @click="reset">
              {{ resetArmed ? t('settings.confirmReset') : t('action.reset') }}
            </button>
            <button class="btn" @click="importFile">{{ t('settings.import') }}</button>
          </div>
        </template>

        <template v-else-if="tab === 'storage'">
          <!-- 区块：数据与存储（当前位置、来源、备注） -->
          <div class="field">
            <div class="field-label">
              <span>{{ t('storage.current') }}</span>
              <span class="badge">{{ sourceLabel }}</span>
            </div>
            <div class="path mono">{{ storage?.path }}</div>
            <div v-if="storage?.note" class="hint warn-text">{{ storage.note }}</div>
          </div>

          <!-- 更改位置、打开目录、导出/导入配置包、恢复默认位置 -->
          <div class="storage-grid">
            <button class="btn" @click="changeDir">{{ t('storage.change') }}</button>
            <button class="btn" @click="openDir">{{ t('storage.open') }}</button>
            <button class="btn" @click="exportBundle">{{ t('storage.export') }}</button>
            <button class="btn" @click="importBundle">{{ t('storage.import') }}</button>
            <button class="btn" @click="resetDir">{{ t('storage.reset') }}</button>
          </div>

          <p class="hint">{{ t('storage.hint') }}</p>
        </template>

        <template v-else>
          <!-- 区块：关于（名称、版本、简介、说明文档入口） -->
          <div class="about">
            <div class="about-title">LSP PlayerKit</div>
            <div class="muted">v{{ storage?.version }}</div>
            <p class="hint">{{ t('about.intro') }}</p>
            <div class="storage-grid">
              <button class="btn" @click="openDoc">{{ t('about.docs') }}</button>
            </div>
          </div>
        </template>
      </div>
    </aside>
  </div>
</template>

<style scoped>
/* 区块：遮罩（固定全屏，半透明背景 + 轻微模糊） */
.overlay {
  position: fixed;
  inset: 0;
  background: var(--scrim);
  display: flex;
  justify-content: flex-end;
  z-index: 60;
  backdrop-filter: blur(2px);
}

/* 区块：抽屉主体（从右侧贴边，纵向排列标题、标签页、内容） */
.drawer {
  width: 480px;
  max-width: 92vw;
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--surface);
  border-left: 1px solid var(--line);
  box-shadow: var(--shadow);
}

/* 区块：标题栏 */
.drawer-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  padding: 16px 18px 10px;
}

.drawer-title {
  font-size: 15px;
  font-weight: 600;
}

.drawer .tabs {
  margin: 0 18px;
}

/* 区块：内容区（自身滚动） */
.drawer-body {
  flex: 1;
  overflow: auto;
  padding: 16px 18px 24px;
}

/* 区块：设置分组 */
.group {
  margin-bottom: 18px;
}

.group-title {
  margin-bottom: 10px;
  padding-bottom: 6px;
  border-bottom: 1px solid var(--line);
  color: var(--muted);
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

/* 区块：字段控件（bool 勾选行、path 行内输入 + 按钮） */
.switch {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--muted);
}

.path-field {
  display: flex;
  gap: 8px;
}

.path-field .input {
  flex: 1;
  min-width: 0;
}

/* 区块：底部操作按钮 */
.drawer-actions {
  display: flex;
  gap: 8px;
  margin-top: 20px;
}

/* 区块：数据目录展示 */
.path {
  padding: 8px 10px;
  border-radius: 8px;
  background: var(--bg);
  border: 1px solid var(--line);
  font-size: 11px;
  word-break: break-all;
}

.storage-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  margin: 14px 0;
}

/* 区块：说明文字与强调色 */
.hint {
  color: var(--muted);
  font-size: 11px;
  line-height: 1.7;
}

.warn-text {
  color: var(--warn);
}

.about-title {
  font-size: 18px;
  color: var(--brand);
}
</style>
