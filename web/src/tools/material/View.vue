<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

import { callTool, invoke } from '../../platform/bridge'
import { locale, t } from '../../platform/i18n'
import { clone, getSettings, loadSettings, revision, saveSettings } from '../../platform/settings'
import { notify, notifyError } from '../../platform/toast'
import type {
  MaterialResult,
  MaterialRow,
  MaterialTotals,
  PackingResult,
  ToolDef,
} from '../../platform/types'
import DataTable from '../../ui/DataTable.vue'
import PackingDialog from './PackingDialog.vue'

const props = defineProps<{ tool: ToolDef }>()

const STACK_OPTIONS = ['64', '16', '1']

interface SourceEntry {
  id?: string
  name: string
  count: number
}

interface SourceMeta {
  regions?: number
  blocks?: number
  items?: number
  filtered?: number
  volume?: number
  kinds?: number
  layout?: string
}

interface SourceFile {
  id: string
  name: string
  text?: string
  entries?: SourceEntry[]
  meta?: SourceMeta
  enabled: boolean
}

const sources = ref<SourceFile[]>([])
const sourceStats = ref<Record<string, { kinds: number; items: number }>>({})
let sourceSeq = 0

const activeSources = computed(() => sources.value.filter((source) => source.enabled))
const items = ref<MaterialRow[]>([])
const totals = ref<MaterialTotals | null>(null)
const warnings = ref<{ line: number; text: string }[]>([])
const skipped = ref(0)
const truncated = ref(false)
const stackSize = ref('64')
const shulkerSlots = ref(27)
const busy = ref(false)
const packing = ref<PackingResult | null>(null)
const packingOpen = ref(false)
const packingBusy = ref(false)
const selected = ref<Set<string>>(new Set())
const batchStack = ref('64')
const stacks = ref<Record<string, string>>({})
const ignored = ref<Set<string>>(new Set())
const ignoredItems = ref<MaterialIgnored[]>([])
const exportName = ref('')
const exportDir = ref('')
const defaultExportDir = ref('')

const perBox = computed(() => Number(stackSize.value) * shulkerSlots.value)
const stackFilter = ref('all')
const sortState = ref<{ key: string; dir: 'asc' | 'desc' }>({ key: 'count', dir: 'desc' })
const listSort = ref<'asc' | 'desc'>('desc')
const search = ref('')
const searchFocused = ref(false)

const filteredItems = computed(() =>
  stackFilter.value === 'all'
    ? items.value
    : items.value.filter((item) => String(item.stack) === stackFilter.value),
)
const orderedItems = computed(() => {
  const sign = listSort.value === 'asc' ? 1 : -1
  return [...items.value, ...ignoredItems.value].sort((a, b) => (a.count - b.count) * sign)
})
const visibleItems = computed(() => {
  const query = search.value.trim().toLowerCase()
  if (!query) return orderedItems.value
  return orderedItems.value.filter((item) => item.name.toLowerCase().includes(query))
})
const suggestions = computed(() => (search.value.trim() ? visibleItems.value.slice(0, 8) : []))
const preview = computed(() => visibleItems.value.slice(0, 120))
const hiddenKinds = computed(() => Math.max(0, visibleItems.value.length - preview.value.length))
const hasItems = computed(() => items.value.length > 0)
const allSelected = computed(
  () => visibleItems.value.length > 0 && selected.value.size === visibleItems.value.length,
)
const allIgnoredSelected = computed(
  () =>
    selected.value.size > 0 &&
    [...selected.value].every((name) => ignored.value.has(name)),
)
const defaultExportName = computed(() => {
  const active = activeSources.value
  if (!active.length) return 'materials.csv'
  const stem = active.length === 1 ? active[0].name : 'merged'
  const base = stem.replace(/\.[^.]+$/, '').trim()
  return base ? `${base}_converted.csv` : 'materials.csv'
})
const currentWarnings = computed(() => warnings.value.slice(0, 3))

function isIgnored(name: string): boolean {
  return ignored.value.has(name)
}

function isCustom(name: string): boolean {
  return stacks.value[name] !== undefined
}

function onSort(payload: { key: string; dir: 'asc' | 'desc' }) {
  sortState.value = payload
}

function toggleListSort() {
  listSort.value = listSort.value === 'desc' ? 'asc' : 'desc'
}

function sortForExport(rows: MaterialRow[]): MaterialRow[] {
  const sign = sortState.value.dir === 'asc' ? 1 : -1
  return [...rows].sort((a, b) => (a.count - b.count) * sign)
}

function toggle(name: string) {
  const next = new Set(selected.value)
  if (next.has(name)) next.delete(name)
  else next.add(name)
  selected.value = next
}

function toggleAll() {
  selected.value = allSelected.value
    ? new Set()
    : new Set(visibleItems.value.map((item) => item.name))
}

function chooseSuggestion(name?: string) {
  if (!name) return
  search.value = name
  searchFocused.value = false
}

async function toggleIgnore() {
  if (!selected.value.size) return
  const next = new Set(ignored.value)
  if (allIgnoredSelected.value) {
    selected.value.forEach((name) => next.delete(name))
  } else {
    selected.value.forEach((name) => next.add(name))
  }
  ignored.value = next
  await convert()
  selected.value = new Set()
}

async function applyBatch() {
  if (!selected.value.size) return
  const next = { ...stacks.value }
  selected.value.forEach((name) => {
    next[name] = batchStack.value
  })
  stacks.value = next
  await convert()
  selected.value = new Set()
}

async function restoreOne(name: string) {
  const next = new Set(ignored.value)
  next.delete(name)
  ignored.value = next
  await convert()
}

async function restoreAll() {
  if (!ignored.value.size) return
  ignored.value = new Set()
  await convert()
}

function syncFromSettings() {
  const data = getSettings(props.tool.id)
  if (!data?.stackSize) return
  stackSize.value = String(data.stackSize)
  shulkerSlots.value = Number(data.shulkerSlots ?? 27)
  exportDir.value = String(data.exportDir ?? '')
}

async function setStack(value: string) {
  if (value === stackSize.value) return
  stackSize.value = value
  try {
    const data = clone(getSettings(props.tool.id))
    data.stackSize = value
    await saveSettings(props.tool.id, data)
    if (activeSources.value.length) await convert()
  } catch (error) {
    notifyError(error)
  }
}

async function convert() {
  const active = activeSources.value
  if (!active.length) {
    notify('info', t(sources.value.length ? 'material.msg.noActive' : 'material.msg.noFile'))
    return
  }
  busy.value = true
  try {
    const result = await callTool<MaterialResult>(props.tool.id, 'convert', {
      sources: active.map((source) =>
        source.entries
          ? { name: source.name, entries: source.entries }
          : { name: source.name, text: source.text ?? '' },
      ),
      locale: locale.value,
      stacks: stacks.value,
      ignore: [...ignored.value],
    })
    items.value = result.items
    totals.value = result.totals
    ignoredItems.value = result.ignoredItems ?? []
    warnings.value = result.warnings
    skipped.value = result.skipped
    truncated.value = result.truncated
    sourceStats.value = Object.fromEntries(
      (result.sources ?? []).map((source) => [
        source.name,
        { kinds: source.kinds, items: source.items },
      ]),
    )
  } catch (error) {
    clearResult()
    notifyError(error)
  } finally {
    busy.value = false
  }
}

watch(locale, async () => {
  if (!sources.value.some((source) => source.entries?.some((entry) => entry.id))) return
  if (activeSources.value.length) await convert()
})

function clearResult() {
  items.value = []
  totals.value = null
  ignoredItems.value = []
  warnings.value = []
  skipped.value = 0
  truncated.value = false
  sourceStats.value = {}
  selected.value = new Set()
}

async function pack() {
  const active = activeSources.value
  if (!active.length) {
    notify('info', t(sources.value.length ? 'material.msg.noActive' : 'material.msg.noFile'))
    return
  }
  packingBusy.value = true
  try {
    const result = await callTool<PackingResult>(props.tool.id, 'pack', {
      sources: active.map((source) =>
        source.entries
          ? { name: source.name, entries: source.entries }
          : { name: source.name, text: source.text ?? '' },
      ),
      locale: locale.value,
      stacks: stacks.value,
      ignore: [...ignored.value],
    })
    packing.value = result
    packingOpen.value = true
  } catch (error) {
    notifyError(error)
  } finally {
    packingBusy.value = false
  }
}

async function readFiles() {
  try {
    const result = await invoke<{
      cancelled?: boolean
      files?: {
        name?: string
        text?: string
        entries?: SourceEntry[]
        meta?: SourceMeta
      }[]
    }>('file_open_material_lists', locale.value)
    if (result?.cancelled || !Array.isArray(result?.files)) return

    let added = 0
    for (const file of result.files) {
      const entries = Array.isArray(file?.entries) ? file.entries : undefined
      const body = typeof file?.text === 'string' ? file.text : ''
      if (!entries?.length && !body.trim()) continue
      sourceSeq += 1
      sources.value.push({
        id: `source-${sourceSeq}`,
        name: (file.name ?? '').trim() || t('material.sources.unnamed'),
        text: entries ? undefined : body,
        entries: entries?.length ? entries : undefined,
        meta: file.meta,
        enabled: true,
      })
      added += 1
    }
    if (!added) {
      notify('info', t('material.msg.emptyFile'))
      return
    }
    selected.value = new Set()
    exportName.value = ''
    notify('success', t('material.msg.importedMany', { n: added }))
    await convert()
  } catch (error) {
    notifyError(error)
  }
}

function sourceTitle(source: SourceFile): string {
  const meta = source.meta
  if (!meta?.regions) return source.name
  const lines = [
    t('material.sources.meta', {
      regions: meta.regions,
      blocks: meta.blocks ?? 0,
    }),
  ]
  if (meta.filtered) {
    lines.push(t('material.sources.filtered', { n: meta.filtered }))
  }
  return `${source.name}\n${lines.join(' · ')}`
}

async function toggleSource(source: SourceFile) {
  source.enabled = !source.enabled
  if (activeSources.value.length) await convert()
  else clearResult()
}

async function removeSource(source: SourceFile) {
  sources.value = sources.value.filter((item) => item.id !== source.id)
  if (activeSources.value.length) await convert()
  else clearResult()
}

function csvCell(value: unknown): string {
  const cell = String(value ?? '')
  return /[",\r\n]/.test(cell) ? `"${cell.replaceAll('"', '""')}"` : cell
}

async function exportCsv() {
  if (!filteredItems.value.length || !totals.value) {
    notify('info', t('material.msg.exportEmpty'))
    return
  }
  const header = [
    t('material.col.name'),
    t('material.col.stack'),
    t('material.col.count'),
    t('material.col.shulkers'),
    t('material.col.stacks'),
    t('material.col.items'),
  ]
  const body = sortForExport(filteredItems.value).map((row) => [
    row.name,
    row.stack,
    row.count,
    row.shulkers,
    row.stacks,
    row.items,
  ])
  const total = [
    t('material.row.total'),
    '',
    totals.value.count,
    totals.value.shulkers,
    totals.value.stacks,
    totals.value.items,
  ]
  const csv = [header, ...body, total]
    .map((line) => line.map(csvCell).join(','))
    .join('\r\n')

  try {
    const target = exportName.value.trim() || defaultExportName.value
    const result = await invoke<{ cancelled?: boolean }>(
      'file_save_text',
      target,
      csv,
      exportDir.value.trim(),
    )
    if (result?.cancelled) return
    notify('success', t('material.msg.exported'))
  } catch (error) {
    notifyError(error)
  }
}

async function saveExportDir() {
  try {
    const data = clone(getSettings(props.tool.id))
    data.exportDir = exportDir.value.trim()
    await saveSettings(props.tool.id, data)
    notify('success', t('settings.saved'))
  } catch (error) {
    notifyError(error)
  }
}

async function pickExportDir() {
  try {
    const path = await invoke<string | null>('storage_pick_dir')
    if (!path) return
    exportDir.value = path
    await saveExportDir()
  } catch (error) {
    notifyError(error)
  }
}

async function loadDefaultExportDir() {
  try {
    const info = await invoke<{ path?: string }>('storage_info')
    const base = String(info?.path ?? '').replace(/[\\/]+$/, '')
    defaultExportDir.value = base ? `${base}\\output` : ''
  } catch {
    defaultExportDir.value = ''
  }
}

watch(
  () => revision[props.tool.id],
  () => {
    syncFromSettings()
  },
)

onMounted(async () => {
  try {
    const data = await loadSettings(props.tool.id)
    stackSize.value = String(data.stackSize)
    shulkerSlots.value = Number(data.shulkerSlots)
    exportDir.value = String(data.exportDir ?? '')
  } catch (error) {
    notifyError(error)
  }
  await loadDefaultExportDir()
})
</script>

<template>
  <div class="workbench">
    <section class="panel">
      <div class="panel-head">
        <span>{{ t('material.panel.input') }}</span>
        <span class="badge">{{ perBox }} {{ t('material.unit.perBox') }}</span>
      </div>

      <div class="panel-body">
        <div class="import-card">
          <button class="btn primary block import-btn" :disabled="busy" @click="readFiles">
            {{ t('material.action.import') }}
          </button>
          <div class="import-file">
            <span v-if="sources.length" class="muted">
              {{ t('material.sources.count', { n: sources.length, active: activeSources.length }) }}
            </span>
            <span v-else class="muted">{{ t('material.sources.hint') }}</span>
          </div>
        </div>

        <div v-if="sources.length" class="source-list">
          <label
            v-for="source in sources"
            :key="source.id"
            class="source-row"
            :class="{ off: !source.enabled }"
          >
            <input type="checkbox" :checked="source.enabled" @change="toggleSource(source)" />
            <span class="source-name" :title="sourceTitle(source)">{{ source.name }}</span>
            <span v-if="sourceStats[source.name]" class="source-meta mono">
              {{ sourceStats[source.name].kinds }} · {{ sourceStats[source.name].items }}
            </span>
            <button
              class="source-remove"
              type="button"
              :title="t('material.action.removeList')"
              @click.prevent="removeSource(source)"
            >
              ✕
            </button>
          </label>
        </div>

        <div class="field">
          <label class="field-label">
            <span>{{ t('material.field.defaultStack') }}</span>
            <span class="unit">{{ t('material.hint.stack') }}</span>
          </label>
          <div class="segmented">
            <button
              v-for="option in STACK_OPTIONS"
              :key="option"
              :class="{ active: stackSize === option }"
              @click="setStack(option)"
            >
              {{ option }}
            </button>
          </div>
        </div>

        <div class="field material-list-field">
          <label class="field-label">
            <span>{{ t('material.list.title') }}</span>
            <span class="unit">
              {{ items.length }} {{ t('material.unit.kinds') }} · {{ totals?.count ?? 0 }}
              {{ t('material.unit.items') }}
              <template v-if="ignoredItems.length">
                · {{ t('material.list.ignoredCount', { n: ignoredItems.length }) }}
              </template>
            </span>
          </label>

          <div class="search">
            <input
              v-model="search"
              class="input search-input"
              type="text"
              :placeholder="t('material.search.placeholder')"
              @focus="searchFocused = true"
              @input="searchFocused = true"
              @blur="searchFocused = false"
              @keydown.enter.prevent="chooseSuggestion(suggestions[0]?.name)"
              @keydown.esc="search = ''"
            />
            <button v-if="search" class="search-clear" @click="search = ''">✕</button>
            <div v-if="searchFocused && search && suggestions.length" class="suggestions">
              <button
                v-for="item in suggestions"
                :key="item.name"
                class="suggestion"
                type="button"
                @mousedown.prevent="chooseSuggestion(item.name)"
              >
                <span class="suggestion-name">{{ item.name }}</span>
                <span class="suggestion-count mono">{{ item.count }}</span>
              </button>
            </div>
          </div>

          <div class="list">
            <div class="list-head">
              <label class="pick">
                <input
                  type="checkbox"
                  :checked="allSelected"
                  :disabled="!orderedItems.length"
                  @change="toggleAll"
                />
                <span>{{ t('material.list.selectAll') }}</span>
              </label>
              <span class="muted">{{ t('material.list.selected', { n: selected.size }) }}</span>
              <button class="sort-btn" :title="t('material.list.sortHint')" @click="toggleListSort">
                {{ t('material.col.count') }}
                <span class="arrow">{{ listSort === 'desc' ? '▼' : '▲' }}</span>
              </button>
            </div>

            <label
              v-for="item in preview"
              :key="item.name"
              class="list-row"
              :class="{ picked: selected.has(item.name), ignored: isIgnored(item.name) }"
            >
              <input type="checkbox" :checked="selected.has(item.name)" @change="toggle(item.name)" />
              <span class="list-name" :title="item.name">{{ item.name }}</span>
              <span v-if="isIgnored(item.name)" class="ignored-tag">
                {{ t('material.list.ignored') }}
              </span>
              <span
                class="stack-chip"
                :class="{ custom: isCustom(item.name) }"
                :title="t('material.list.customHint')"
              >
                {{ item.stack }}
              </span>
              <span class="list-count mono">{{ item.count }}</span>
            </label>

            <div v-if="!orderedItems.length" class="list-empty">{{ t('material.list.empty') }}</div>
            <div v-else-if="!visibleItems.length" class="list-empty">
              {{ t('material.search.empty') }}
            </div>
            <div v-if="hiddenKinds" class="list-more">
              {{ t('material.list.more', { n: hiddenKinds }) }}
            </div>
          </div>

          <div class="batch">
            <select v-model="batchStack" class="input batch-select" :disabled="!hasItems">
              <option v-for="option in STACK_OPTIONS" :key="option" :value="option">
                {{ option }}
              </option>
            </select>
            <button class="btn sm" :disabled="!selected.size || busy" @click="applyBatch">
              {{ t('material.action.apply') }}
            </button>
            <button class="btn sm" :disabled="!selected.size || busy" @click="toggleIgnore">
              {{ allIgnoredSelected ? t('material.action.restore') : t('material.action.ignore') }}
            </button>
          </div>
        </div>

        <div class="ignored-panel">
          <div class="ignored-head">
            <span>{{ t('material.ignored.title', { n: ignoredItems.length }) }}</span>
            <button
              v-if="ignoredItems.length"
              class="sort-btn"
              type="button"
              @click="restoreAll"
            >
              {{ t('material.ignored.restoreAll') }}
            </button>
          </div>
          <div v-if="ignoredItems.length" class="ignored-list">
            <div v-for="item in ignoredItems" :key="item.name" class="ignored-row">
              <span class="ignored-name" :title="item.name">{{ item.name }}</span>
              <span class="list-count mono">{{ item.count }}</span>
              <button
                class="btn ghost sm ignored-restore"
                type="button"
                @click="restoreOne(item.name)"
              >
                {{ t('material.ignored.restore') }}
              </button>
            </div>
          </div>
          <div v-else class="ignored-empty">{{ t('material.ignored.empty') }}</div>
        </div>

        <div class="actions">
          <button class="btn primary" :disabled="busy || !hasItems" @click="convert">
            {{ busy ? t('status.calculating') : t('material.action.convert') }}
          </button>
          <button class="btn" :disabled="packingBusy || !hasItems" @click="pack">
            {{ t('material.action.pack') }}
          </button>
          <button class="btn" :disabled="!hasItems" @click="exportCsv">
            {{ t('material.action.export') }}
          </button>
        </div>

        <div class="export-block">
          <div class="export-row">
            <span class="export-label">{{ t('material.field.exportName') }}</span>
            <input
              v-model="exportName"
              class="input export-input"
              :placeholder="defaultExportName"
            />
          </div>
          <div class="export-row">
            <span class="export-label">{{ t('material.field.exportDir') }}</span>
            <input
              v-model="exportDir"
              class="input export-input"
              :placeholder="defaultExportDir"
              @change="saveExportDir"
            />
            <button class="btn sm" type="button" @click="pickExportDir">
              {{ t('settings.pickDir') }}
            </button>
          </div>
        </div>
      </div>
    </section>

    <section class="panel">
      <div class="panel-head">
        <span>{{ t('material.panel.result') }}</span>
        <span class="head-meta">
          <span v-if="truncated" class="badge warn">{{ t('material.msg.truncated') }}</span>
          <span class="muted">{{ t('material.col.stack') }}</span>
          <span class="stack-filter">
            <button
              v-for="option in ['all', '64', '16', '1']"
              :key="option"
              :class="{ active: stackFilter === option }"
              @click="stackFilter = option"
            >
              {{ option === 'all' ? t('material.filter.all') : option }}
            </button>
          </span>
          <span v-if="totals" class="muted">
            {{ filteredItems.length }} / {{ totals.kinds }}
          </span>
        </span>
      </div>

      <div class="result-body">
        <DataTable
          :columns="tool.columns"
          :rows="filteredItems"
          :selected="null"
          :sortable="['count']"
          :default-sort="sortState"
          empty-key="material.empty"
          @sort-change="onSort"
        />
      </div>

      <footer v-if="totals" class="summary">
        <div class="stats">
          <div class="stat">
            <span class="stat-label">{{ t('material.stats.kinds') }}</span>
            <span class="stat-value mono">{{ totals.kinds }}</span>
          </div>
          <div class="stat">
            <span class="stat-label">{{ t('material.stats.count') }}</span>
            <span class="stat-value mono">{{ totals.count }}</span>
          </div>
          <div class="stat">
            <span class="stat-label">{{ t('material.stats.shulkers') }}</span>
            <span class="stat-value mono">{{ totals.shulkers }}</span>
          </div>
          <div class="stat brand">
            <span class="stat-label">{{ t('material.stats.boxesNeeded') }}</span>
            <span class="stat-value mono">{{ totals.boxesNeeded }}</span>
          </div>
          <div class="stat">
            <span class="stat-label">{{ t('material.stats.perBox') }}</span>
            <span class="stat-value mono">{{ totals.perBox }}</span>
          </div>
        </div>

        <div v-if="skipped" class="warn-line">
          <span class="badge warn">{{ t('material.warn.skipped', { n: skipped }) }}</span>
          <span v-for="item in currentWarnings" :key="item.line" class="warn-item muted">
            {{ t('material.warn.line', { line: item.line, text: item.text }) }}
          </span>
          <span v-if="skipped > currentWarnings.length" class="muted">…</span>
        </div>
      </footer>
    </section>
  </div>

  <PackingDialog v-if="packingOpen && packing" :result="packing" @close="packingOpen = false" />
</template>

<style scoped>
.workbench {
  height: 100%;
  display: grid;
  grid-template-columns: 380px minmax(0, 1fr);
  gap: 14px;
  min-height: 0;
  min-width: 0;
}

@media (max-width: 1080px) {
  .workbench {
    grid-template-columns: 1fr;
    grid-template-rows: auto 1fr;
    overflow: auto;
  }
}

.import-card {
  padding: 12px;
  border: 1px dashed var(--line-strong);
  border-radius: 10px;
  background: var(--surface-2);
  margin-bottom: 14px;
}

.import-file {
  margin-top: 8px;
  font-size: 11px;
  text-align: center;
  min-height: 16px;
}

.file-name {
  display: inline-block;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--brand);
}

.source-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 132px;
  overflow-y: auto;
  margin-bottom: 14px;
  padding: 8px;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: var(--surface-2);
}

.source-row {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  font-size: 11px;
  color: var(--text);
  cursor: pointer;
}

.source-row.off {
  color: var(--muted);
}

.source-row.off .source-name {
  text-decoration: line-through;
}

.source-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.source-meta {
  flex: 0 0 auto;
  color: var(--muted);
  font-size: 10px;
}

.source-remove {
  flex: 0 0 auto;
  width: 18px;
  height: 18px;
  padding: 0;
  border: none;
  border-radius: 4px;
  background: transparent;
  color: var(--muted);
  font-size: 10px;
  line-height: 1;
  cursor: pointer;
}

.source-remove:hover {
  background: var(--surface-3);
  color: var(--text);
}

.list {
  max-height: 120px;
  overflow: auto;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--bg);
}

.panel-body {
  display: flex;
  flex-direction: column;
}

.panel-body > *:not(.material-list-field) {
  flex: 0 0 auto;
}

.material-list-field {
  flex: 1 1 auto;
  min-height: 360px;
  display: flex;
  flex-direction: column;
}

.material-list-field .list {
  flex: 1 1 auto;
  min-height: 240px;
  max-height: none;
}

.search {
  position: relative;
  margin-bottom: 8px;
}

.search-input {
  height: 30px;
  padding-right: 30px;
  font-size: 12px;
}

.search-clear {
  position: absolute;
  top: 50%;
  right: 5px;
  width: 20px;
  height: 20px;
  transform: translateY(-50%);
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--muted);
  font-size: 11px;
  cursor: pointer;
}

.search-clear:hover {
  background: var(--surface-3);
  color: var(--text);
}

.suggestions {
  position: absolute;
  z-index: 8;
  top: calc(100% + 4px);
  left: 0;
  right: 0;
  max-height: 220px;
  overflow-y: auto;
  background: var(--surface-3);
  border: 1px solid var(--line-strong);
  border-radius: 8px;
  box-shadow: var(--shadow);
  overflow-x: hidden;
}

.suggestion {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  width: 100%;
  padding: 6px 10px;
  border: none;
  background: transparent;
  color: var(--text);
  font-size: 12px;
  text-align: left;
  cursor: pointer;
}

.suggestion:hover {
  background: var(--brand-soft);
  color: var(--brand);
}

.suggestion-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.suggestion-count {
  flex: 0 0 auto;
  color: var(--muted);
  font-size: 11px;
}

.list-head {
  position: sticky;
  top: 0;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 5px 10px;
  background: var(--surface-2);
  border-bottom: 1px solid var(--line);
  font-size: 11px;
}

.pick {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
}

.list input[type='checkbox'] {
  width: 13px;
  height: 13px;
  margin: 0;
  accent-color: var(--brand);
  cursor: pointer;
}

.list-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 10px;
  border-bottom: 1px solid var(--line);
  font-size: 12px;
  cursor: pointer;
}

.list-row.picked {
  background: var(--brand-soft);
}

.list-row:last-child {
  border-bottom: none;
}

.list-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.list-count {
  color: var(--text);
  font-size: 12px;
}

.stack-chip {
  min-width: 30px;
  padding: 1px 6px;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: var(--surface-3);
  color: var(--muted);
  font-family: var(--font-mono);
  font-size: 11px;
  text-align: center;
}

.stack-chip.custom {
  border-color: rgba(62, 224, 196, 0.35);
  background: var(--brand-soft);
  color: var(--brand);
}

.list-row.ignored .list-name {
  color: var(--muted);
  text-decoration: line-through;
}

.list-row.ignored .stack-chip {
  opacity: 0.5;
}

.list-row.ignored .list-count {
  color: var(--muted);
}

.ignored-tag {
  flex: 0 0 auto;
  padding: 0 6px;
  border-radius: 999px;
  background: rgba(242, 193, 78, 0.12);
  color: var(--warn);
  font-size: 10px;
}

.export-block {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 10px;
}

.export-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.export-label {
  flex: 0 0 58px;
  color: var(--muted);
  font-size: 11px;
}

.export-row .btn {
  flex: 0 0 auto;
  height: 28px;
}

.export-input {
  flex: 1;
  min-width: 0;
  height: 28px;
  font-family: var(--font-mono);
  font-size: 12px;
}

.ignored-panel {
  margin-top: 12px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--bg);
  overflow: hidden;
}

.ignored-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 6px 10px;
  border-bottom: 1px solid var(--line);
  background: var(--surface-2);
  color: var(--muted);
  font-size: 11px;
}

.ignored-list {
  max-height: 64px;
  overflow-y: auto;
  overscroll-behavior: contain;
}

.ignored-list::-webkit-scrollbar {
  width: 8px;
}

.ignored-list::-webkit-scrollbar-thumb {
  border: none;
  border-radius: 999px;
  background: var(--brand-dim);
}

.ignored-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 10px;
  border-bottom: 1px solid var(--line);
  font-size: 12px;
}

.ignored-row:last-child {
  border-bottom: none;
}

.ignored-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--muted);
  text-decoration: line-through;
}

.ignored-restore {
  flex: 0 0 auto;
  height: 22px;
  padding: 0 8px;
  font-size: 11px;
}

.ignored-empty {
  padding: 10px;
  text-align: center;
  color: var(--muted);
  font-size: 11px;
}

.batch {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}

.batch-select {
  width: 96px;
  height: 28px;
  padding: 0 8px;
  font-family: var(--font-mono);
}

.batch .btn {
  flex: 1;
}

.sort-btn {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 2px 6px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--muted);
  font-size: 11px;
  cursor: pointer;
}

.sort-btn:hover {
  background: var(--surface-3);
  color: var(--text);
}

.sort-btn .arrow {
  color: var(--brand);
  font-size: 9px;
}

.stack-filter {
  display: inline-flex;
  gap: 2px;
  padding: 2px;
  background: var(--surface-2);
  border-radius: 6px;
}

.stack-filter button {
  height: 20px;
  padding: 0 7px;
  border: none;
  border-radius: 4px;
  background: transparent;
  color: var(--muted);
  font-family: var(--font-mono);
  font-size: 11px;
  cursor: pointer;
}

.stack-filter button.active {
  background: var(--surface-3);
  color: var(--brand);
}

.list-empty {
  padding: 18px 10px;
  text-align: center;
  color: var(--muted);
  font-size: 12px;
}

.list-more {
  padding: 6px 10px;
  color: var(--muted);
  font-size: 11px;
  text-align: center;
}

.segmented {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 4px;
  padding: 4px;
  background: var(--surface-2);
  border-radius: 8px;
}

.segmented button {
  height: 28px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--muted);
  font-family: var(--font-mono);
  cursor: pointer;
}

.segmented button.active {
  background: var(--brand);
  color: #04241f;
  font-weight: 600;
}

.actions {
  display: flex;
  gap: 8px;
  margin-top: 4px;
}

.actions .primary {
  flex: 1.2;
}

.actions .btn:not(.primary) {
  flex: 1;
}

.tip {
  margin-top: 10px;
  font-size: 10px;
  line-height: 1.6;
}

.panel-body .field {
  margin-bottom: 10px;
}

.panel-body .import-card {
  padding: 10px;
  margin-bottom: 10px;
}

.result-body {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.head-meta {
  display: flex;
  align-items: center;
  gap: 8px;
}

.summary {
  border-top: 1px solid var(--line);
  padding: 10px 12px;
  background: var(--surface-2);
}

.stats {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 8px;
}

.stat {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 8px 10px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--surface);
  min-width: 0;
}

.stat-label {
  color: var(--muted);
  font-size: 11px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.stat-value {
  font-size: 15px;
  color: var(--text);
}

.stat.brand {
  border-color: rgba(62, 224, 196, 0.35);
  background: var(--brand-soft);
}

.stat.brand .stat-value {
  color: var(--brand);
}

.warn-line {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 8px;
  font-size: 11px;
}

.warn-item {
  max-width: 240px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
