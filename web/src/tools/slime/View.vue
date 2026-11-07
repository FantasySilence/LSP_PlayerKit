<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { callTool, invoke } from '../../platform/bridge'
import { t } from '../../platform/i18n'
import { getSettings, loadSettings, saveSettings } from '../../platform/settings'
import { notify, notifyError } from '../../platform/toast'
import type { ToolDef } from '../../platform/types'
import SlimeMap from './SlimeMap.vue'

interface SlimeResult {
  rank: number
  x: number
  z: number
  chunkX: number
  chunkZ: number
  score: number
  coverage: number
}

interface RingInfo {
  inner: number
  outer: number
  area: number
}

interface ScanState {
  id: string
  state: 'running' | 'done' | 'aborted' | 'error'
  mode: 'exact' | 'sample'
  seed: string
  ring: RingInfo
  area: { x0: number; z0: number; x1: number; z1: number }
  done: number
  total: number
  progress: number
  best: number
  results: SlimeResult[]
  stats: Record<string, number | string>
  error: string
  elapsed: number
}

interface MapPayload {
  x0: number
  z0: number
  width: number
  height: number
  bits: string
  heat?: string
}

const props = defineProps<{ tool: ToolDef }>()

const seed = ref<string>('0')
const centerX = ref<number | string>(-32)
const centerZ = ref<number | string>(-8)
const radiusBlocks = ref<number | string>(4096)
const ringInner = ref<number | string>(24)
const ringOuter = ref<number | string>(128)
const simDistance = ref<number | string>(8)
const mode = ref<'auto' | 'exact' | 'sample'>('auto')
const topN = ref<number | string>(100)
const nmsChunks = ref<number | string>(8)
const samples = ref<number | string>(50000)

const seedHistory = ref<string[]>([])
const historyOpen = ref(false)
const historyIndex = ref(-1)
const seedCombo = ref<HTMLElement | null>(null)
const SEED_HISTORY_KEY = 'lspkit.slime.seedHistory'
const SEED_HISTORY_MAX = 12

const busy = ref(false)
const scanId = ref('')
const scan = ref<ScanState | null>(null)
const results = ref<SlimeResult[]>([])
const selected = ref<number | null>(null)
const ringArea = ref(0)
const errorText = ref('')

const mapCells = ref<Uint8Array | null>(null)
const mapHeat = ref<Uint8Array | null>(null)
const mapMeta = ref<{ x0: number; z0: number; width: number; height: number } | null>(null)
const showHeat = ref(false)
const showResults = ref(true)
const perimeterSize = ref<number | string>(21)
const perimeterOpen = ref(false)
const perimeter = ref<{
  cx0: number
  cz0: number
  size: number
  x0: number
  z0: number
  x1: number
  z1: number
} | null>(null)
const perimeterError = ref('')
const mapRef = ref<InstanceType<typeof SlimeMap> | null>(null)

let pollTimer = 0

const progress = computed(() => Math.min(1, Math.max(0, scan.value?.progress ?? 0)))
const stateLabel = computed(() => {
  const state = scan.value?.state
  if (!state) return t('slime.state.idle')
  return t(`slime.state.${state}`)
})
const markers = computed(() =>
  results.value.map((item) => ({ x: item.x, z: item.z, rank: item.rank })),
)

const seedSuggestions = computed(() => {
  const query = String(seed.value).trim().toLowerCase()
  if (!query) return seedHistory.value
  return seedHistory.value.filter((item) => item.toLowerCase().includes(query))
})

function loadSeedHistory(): void {
  try {
    const raw = localStorage.getItem(SEED_HISTORY_KEY)
    const items = raw ? (JSON.parse(raw) as unknown) : []
    if (Array.isArray(items)) {
      seedHistory.value = items
        .filter((item): item is string => typeof item === 'string' && !!item.trim())
        .slice(0, SEED_HISTORY_MAX)
    }
  } catch {
    seedHistory.value = []
  }
}

function persistSeedHistory(): void {
  try {
    localStorage.setItem(SEED_HISTORY_KEY, JSON.stringify(seedHistory.value))
  } catch {
    /* localStorage 不可用时只保留本次会话的历史 */
  }
}

function rememberSeed(value: string): void {
  const text = value.trim()
  if (!text) return
  seedHistory.value = [text, ...seedHistory.value.filter((item) => item !== text)].slice(
    0,
    SEED_HISTORY_MAX,
  )
  persistSeedHistory()
}

function openHistory(): void {
  historyOpen.value = true
  historyIndex.value = -1
}

function toggleHistory(): void {
  if (historyOpen.value) historyOpen.value = false
  else openHistory()
}

function pickSeed(value: string): void {
  seed.value = value
  historyOpen.value = false
  historyIndex.value = -1
}

function moveHistory(delta: number): void {
  if (!historyOpen.value) openHistory()
  const total = seedSuggestions.value.length
  if (!total) return
  historyIndex.value = (historyIndex.value + delta + total) % total
}

function confirmHistory(): void {
  const item = seedSuggestions.value[historyIndex.value]
  if (historyOpen.value && item) pickSeed(item)
}

function clearHistory(): void {
  seedHistory.value = []
  persistSeedHistory()
  historyOpen.value = false
}

function onSeedKeydown(event: KeyboardEvent): void {
  if (event.key === 'ArrowDown') {
    event.preventDefault()
    moveHistory(1)
  } else if (event.key === 'ArrowUp') {
    event.preventDefault()
    moveHistory(-1)
  } else if (event.key === 'Enter') {
    if (historyOpen.value && historyIndex.value >= 0) {
      event.preventDefault()
      confirmHistory()
    }
  } else if (event.key === 'Escape') {
    historyOpen.value = false
  }
}

function onDocumentPointer(event: PointerEvent): void {
  if (!historyOpen.value) return
  const combo = seedCombo.value
  if (combo && !combo.contains(event.target as Node)) historyOpen.value = false
}

const perimeterMin = computed(() => minPerimeterSize(effectiveRingOuter()))

function effectiveRingOuter(): number {
  const outer = Math.round(Number(ringOuter.value) || 128)
  const sim = Math.round(Number(simDistance.value) || 8)
  return Math.min(Math.max(1, outer), Math.max(1, sim) * 16)
}

function minPerimeterSize(outer: number): number {
  return Math.ceil(outer / 8 + 1)
}

function toNumber(value: number | string, label: string): number {
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) throw new Error(t('slime.msg.notNumber', { label }))
  return parsed
}

async function applySettings(): Promise<void> {
  const data = await loadSettings(props.tool.id)
  seed.value = String(data.seed ?? '0')
  centerX.value = Number(data.centerX ?? -32)
  centerZ.value = Number(data.centerZ ?? -8)
  ringInner.value = Number(data.ringInner ?? 24)
  ringOuter.value = Number(data.ringOuter ?? 128)
  simDistance.value = Number(data.simDistance ?? 8)
  topN.value = Number(data.topN ?? 100)
  nmsChunks.value = Number(data.nmsChunks ?? 8)
  mode.value = (data.mode as 'auto' | 'exact' | 'sample') ?? 'auto'
  samples.value = Number(data.samples ?? 50000)
  perimeterSize.value = Number(data.perimeterChunks ?? 21)
}

async function saveDefaults(): Promise<void> {
  try {
    const data = {
      ...getSettings(props.tool.id),
      seed: String(seed.value),
      centerX: Math.round(toNumber(centerX.value, t('slime.field.centerX'))),
      centerZ: Math.round(toNumber(centerZ.value, t('slime.field.centerZ'))),
      ringInner: Math.round(toNumber(ringInner.value, 'inner')),
      ringOuter: Math.round(toNumber(ringOuter.value, 'outer')),
      simDistance: Math.round(toNumber(simDistance.value, 'sim')),
      topN: Math.round(toNumber(topN.value, 'topN')),
      nmsChunks: Math.round(toNumber(nmsChunks.value, 'nms')),
      mode: mode.value,
      samples: Math.round(toNumber(samples.value, 'samples')),
      perimeterChunks: Math.round(toNumber(perimeterSize.value, t('slime.field.perimeter'))),
    }
    await saveSettings(props.tool.id, data)
    notify('success', t('action.defaultSaved'))
  } catch (error) {
    notifyError(error)
  }
}

function areaPayload() {
  const cx = toNumber(centerX.value, t('slime.field.centerX'))
  const cz = toNumber(centerZ.value, t('slime.field.centerZ'))
  const radius = Math.abs(toNumber(radiusBlocks.value, t('slime.field.radius')))
  if (radius <= 0) throw new Error(t('slime.msg.badRadius'))
  if (Math.abs(cx) + radius > 30_000_000 || Math.abs(cz) + radius > 30_000_000) {
    throw new Error(t('slime.msg.outOfWorld'))
  }
  return { x0: cx - radius, z0: cz - radius, x1: cx + radius, z1: cz + radius }
}

async function start(): Promise<void> {
  if (busy.value) return
  stopPolling()
  busy.value = true
  errorText.value = ''
  results.value = []
  selected.value = null
  scan.value = null
  mapCells.value = null
  mapHeat.value = null
  perimeter.value = null
  perimeterOpen.value = false
  perimeterError.value = ''
  scanId.value = ''
  try {
    const area = areaPayload()
    const data = await callTool<{
      scanId: string
      mode: string
      total: number
      ring: RingInfo
    }>('slime', 'scan_start', {
      seed: String(seed.value),
      area,
      ringInner: Math.round(toNumber(ringInner.value, 'inner')),
      ringOuter: Math.round(toNumber(ringOuter.value, 'outer')),
      simDistance: Math.round(toNumber(simDistance.value, 'sim')),
      mode: mode.value,
      topN: Math.round(toNumber(topN.value, 'topN')),
      nmsChunks: Math.round(toNumber(nmsChunks.value, 'nms')),
      samples: Math.round(toNumber(samples.value, 'samples')),
    })
    scanId.value = data.scanId
    ringArea.value = data.ring.area
    rememberSeed(String(seed.value))
    notify('success', t('slime.msg.started'))
    pollTimer = window.setInterval(poll, 300)
  } catch (error) {
    busy.value = false
    notifyError(error)
  }
}

async function poll(): Promise<void> {
  if (!scanId.value) return
  try {
    const data = await callTool<ScanState>('slime', 'scan_status', { scanId: scanId.value })
    scan.value = data
    ringArea.value = data.ring.area
    if (data.state !== 'running') {
      stopPolling()
      busy.value = false
      if (data.state === 'done') {
        results.value = data.results
        notify('success', t('slime.msg.done', { n: results.value.length, seconds: data.elapsed }))
        if (results.value.length) select(0)
        else notify('info', t('slime.msg.empty'))
      } else if (data.state === 'aborted') {
        notify('info', t('slime.msg.aborted'))
      } else {
        errorText.value = data.error
        notify('error', data.error || t('slime.state.error'))
      }
    }
  } catch (error) {
    stopPolling()
    busy.value = false
    notifyError(error)
  }
}

async function stop(): Promise<void> {
  if (!scanId.value) return
  try {
    await callTool('slime', 'scan_stop', { scanId: scanId.value })
    notify('info', t('slime.msg.stopping'))
  } catch (error) {
    notifyError(error)
  }
}

function stopPolling(): void {
  if (pollTimer) {
    window.clearInterval(pollTimer)
    pollTimer = 0
  }
}

function decodeBytes(text: string): Uint8Array {
  const raw = atob(text)
  const bytes = new Uint8Array(raw.length)
  for (let index = 0; index < raw.length; index += 1) bytes[index] = raw.charCodeAt(index)
  return bytes
}

function decodeBits(text: string, count: number): Uint8Array {
  const bytes = decodeBytes(text)
  const cells = new Uint8Array(count)
  for (let index = 0; index < count; index += 1) {
    cells[index] = (bytes[index >> 3] >> (7 - (index & 7))) & 1
  }
  return cells
}

async function loadMap(item: SlimeResult, focusIndex: number | null = null): Promise<void> {
  const size = 192
  const cx = Math.floor(item.x / 16)
  const cz = Math.floor(item.z / 16)
  const x0 = cx - size / 2
  const z0 = cz - size / 2
  try {
    const data = await callTool<MapPayload>('slime', 'map', {
      seed: String(seed.value),
      x0,
      z0,
      width: size,
      height: size,
      heat: showHeat.value,
      ringInner: Math.round(toNumber(ringInner.value, 'inner')),
      ringOuter: Math.round(toNumber(ringOuter.value, 'outer')),
      simDistance: Math.round(toNumber(simDistance.value, 'sim')),
    })
    mapCells.value = decodeBits(data.bits, data.width * data.height)
    mapHeat.value = data.heat ? decodeBytes(data.heat) : null
    mapMeta.value = { x0: data.x0, z0: data.z0, width: data.width, height: data.height }
    await nextTick()
    if (focusIndex === null) {
      mapRef.value?.reset()
    } else {
      mapRef.value?.focus(focusIndex)
    }
  } catch (error) {
    notifyError(error)
  }
}

function mapContains(item: SlimeResult): boolean {
  const meta = mapMeta.value
  if (!meta) return false
  const cx = item.x / 16
  const cz = item.z / 16
  return cx >= meta.x0 && cx < meta.x0 + meta.width && cz >= meta.z0 && cz < meta.z0 + meta.height
}

function select(index: number): void {
  if (index < 0 || index >= results.value.length) return
  selected.value = index
  perimeter.value = null
  perimeterOpen.value = false
  perimeterError.value = ''
  const item = results.value[index]
  if (mapContains(item)) {
    mapRef.value?.focus(index)
  } else {
    void loadMap(item, index)
  }
}

function recommendPerimeter(): void {
  if (selected.value === null) {
    notify('info', t('slime.msg.perimeterNoSelection'))
    return
  }
  perimeterOpen.value = true
  applyPerimeter()
}

function closePerimeter(): void {
  perimeterOpen.value = false
  perimeter.value = null
  perimeterError.value = ''
}

function applyPerimeter(): void {
  if (selected.value === null) {
    perimeterOpen.value = false
    return
  }
  const item = results.value[selected.value]
  if (!item) return
  perimeterOpen.value = true
  const outer = effectiveRingOuter()
  const minimum = minPerimeterSize(outer)
  let size = Math.round(Number(perimeterSize.value) || 0)
  if (!Number.isFinite(size) || size <= 0) {
    perimeter.value = null
    perimeterError.value = t('slime.msg.perimeterTooSmall', {
      size: perimeterSize.value,
      min: minimum,
      outer,
    })
    return
  }
  if (size < minimum) {
    perimeter.value = null
    perimeterError.value = t('slime.msg.perimeterTooSmall', {
      size,
      min: minimum,
      outer,
    })
    notify('error', perimeterError.value)
    return
  }
  size = Math.min(65, size)
  perimeterSize.value = size
  perimeterError.value = ''
  const half = size * 8
  const cx0 = Math.round((item.x - half) / 16)
  const cz0 = Math.round((item.z - half) / 16)
  const x0 = cx0 * 16
  const z0 = cz0 * 16
  perimeter.value = {
    cx0,
    cz0,
    size,
    x0,
    z0,
    x1: x0 + size * 16 - 1,
    z1: z0 + size * 16 - 1,
  }
}

function perimeterCornersText(): string {
  const area = perimeter.value
  if (!area) return ''
  return [
    `${t('slime.perimeter.nw')} (${area.x0}, ${area.z0})`,
    `${t('slime.perimeter.ne')} (${area.x1}, ${area.z0})`,
    `${t('slime.perimeter.sw')} (${area.x0}, ${area.z1})`,
    `${t('slime.perimeter.se')} (${area.x1}, ${area.z1})`,
  ].join(' | ')
}

function onMapSelect(index: number): void {
  if (index < 0 || index >= results.value.length) return
  selected.value = index
}

function focusSelected(): void {
  if (selected.value === null) return
  const item = results.value[selected.value]
  if (mapContains(item)) {
    mapRef.value?.focus(selected.value)
  } else {
    void loadMap(item, selected.value)
  }
}

async function toggleHeat(): Promise<void> {
  showHeat.value = !showHeat.value
  if (selected.value !== null) {
    await loadMap(results.value[selected.value], selected.value)
  }
}

async function exportCsv(): Promise<void> {
  if (!results.value.length) {
    notify('info', t('slime.msg.noResults'))
    return
  }
  const header = 'rank,x,z,chunkX,chunkZ,score,coverage'
  const rows = results.value.map((item) =>
    [
      item.rank,
      item.x,
      item.z,
      item.chunkX,
      item.chunkZ,
      Math.round(item.score),
      item.coverage.toFixed(4),
    ].join(','),
  )
  const name = `slime_${scan.value?.seed ?? seed.value}_${scan.value?.area.x0 ?? 0}_${
    scan.value?.area.z0 ?? 0
  }.csv`
  try {
    await invoke('file_save_text', name, [header, ...rows].join('\n'), '')
    notify('success', t('slime.msg.exported'))
  } catch (error) {
    notifyError(error)
  }
}

async function copy(text: string): Promise<void> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
    } else {
      await invoke('clipboard_write', text)
    }
    notify('success', t('action.copied'))
  } catch (error) {
    notifyError(error)
  }
}

watch([ringOuter, simDistance], () => {
  if (perimeterOpen.value) applyPerimeter()
})

onMounted(async () => {
  loadSeedHistory()
  document.addEventListener('pointerdown', onDocumentPointer, true)
  try {
    await applySettings()
  } catch (error) {
    notifyError(error)
  }
})

onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', onDocumentPointer, true)
  stopPolling()
})
</script>

<template>
  <div class="workbench" :class="{ 'results-collapsed': !showResults }">
    <section class="panel params-panel">
      <div class="panel-head">
        <span>{{ t('slime.panel.params') }}</span>
        <span class="badge" :class="{ warn: busy }">{{ stateLabel }}</span>
      </div>
      <div class="panel-body params-body">
        <div ref="seedCombo" class="field seed-field">
          <label class="field-label">{{ t('slime.field.seed') }}</label>
          <div class="combo">
            <input
              v-model="seed"
              class="input mono seed-input"
              type="text"
              spellcheck="false"
              autocomplete="off"
              @focus="openHistory"
              @keydown="onSeedKeydown"
            />
            <button
              type="button"
              class="combo-arrow"
              tabindex="-1"
              :title="t('slime.history.title')"
              @click="toggleHistory"
            >
              ▾
            </button>
            <div v-if="historyOpen" class="combo-menu">
              <div class="combo-title">{{ t('slime.history.title') }}</div>
              <div v-if="!seedSuggestions.length" class="combo-empty">
                {{ t('slime.history.empty') }}
              </div>
              <button
                v-for="(item, index) in seedSuggestions"
                :key="item"
                type="button"
                class="combo-item"
                :class="{ active: index === historyIndex }"
                @mousedown.prevent="pickSeed(item)"
                @click="pickSeed(item)"
              >
                <span class="mono">{{ item }}</span>
              </button>
              <button
                v-if="seedHistory.length"
                type="button"
                class="combo-clear"
                @mousedown.prevent="clearHistory"
                @click="clearHistory"
              >
                {{ t('slime.history.clear') }}
              </button>
            </div>
          </div>
          <div class="hint">{{ t('slime.hint.seed') }}</div>
        </div>

        <div class="field-row">
          <div class="field">
            <label class="field-label">{{ t('slime.field.centerX') }}</label>
            <input v-model.number="centerX" class="input mono" type="number" step="16" />
          </div>
          <div class="field">
            <label class="field-label">{{ t('slime.field.centerZ') }}</label>
            <input v-model.number="centerZ" class="input mono" type="number" step="16" />
          </div>
        </div>

        <div class="field">
          <label class="field-label">
            <span>{{ t('slime.field.radius') }}</span>
            <span class="unit">{{ t('slime.unit.block') }}</span>
          </label>
          <input v-model.number="radiusBlocks" class="input mono" type="number" min="16" step="16" />
          <div class="hint">{{ t('slime.hint.radius') }}</div>
        </div>

        <div class="field-row">
          <div class="field">
            <label class="field-label">
              <span>{{ t('slime.field.ringInner') }}</span>
              <span class="unit">{{ t('slime.unit.block') }}</span>
            </label>
            <input v-model.number="ringInner" class="input mono" type="number" min="0" max="127" />
          </div>
          <div class="field">
            <label class="field-label">
              <span>{{ t('slime.field.ringOuter') }}</span>
              <span class="unit">{{ t('slime.unit.block') }}</span>
            </label>
            <input v-model.number="ringOuter" class="input mono" type="number" min="1" max="128" />
          </div>
        </div>

        <div class="field-row">
          <div class="field">
            <label class="field-label">
              <span>{{ t('slime.field.simDistance') }}</span>
              <span class="unit">{{ t('slime.unit.chunk') }}</span>
            </label>
            <input v-model.number="simDistance" class="input mono" type="number" min="1" max="32" />
          </div>
          <div class="field">
            <label class="field-label">{{ t('slime.field.mode') }}</label>
            <select v-model="mode" class="input">
              <option value="auto">{{ t('slime.mode.auto') }}</option>
              <option value="exact">{{ t('slime.mode.exact') }}</option>
              <option value="sample">{{ t('slime.mode.sample') }}</option>
            </select>
          </div>
        </div>

        <div class="field-row">
          <div class="field">
            <label class="field-label">{{ t('slime.field.topN') }}</label>
            <input v-model.number="topN" class="input mono" type="number" min="1" max="500" />
          </div>
          <div class="field">
            <label class="field-label">
              <span>{{ t('slime.field.nms') }}</span>
              <span class="unit">{{ t('slime.unit.chunk') }}</span>
            </label>
            <input v-model.number="nmsChunks" class="input mono" type="number" min="0" max="32" />
          </div>
        </div>

        <div class="field">
          <label class="field-label">{{ t('slime.field.samples') }}</label>
          <input v-model.number="samples" class="input mono" type="number" min="1000" step="1000" />
        </div>

        <div class="actions">
          <button class="btn primary" :disabled="busy" @click="start">
            {{ t('slime.action.start') }}
          </button>
          <button class="btn" :disabled="!busy" @click="stop">
            {{ t('slime.action.stop') }}
          </button>
        </div>

        <div v-if="scan" class="progress-box">
          <div class="progress"><div class="progress-bar" :style="{ width: `${progress * 100}%` }" /></div>
          <div class="progress-line mono">
            <span>{{ Math.floor(progress * 100) }}%</span>
            <span v-if="scan.state === 'running'">
              {{ t('slime.progress.scanning', { done: scan.done, total: scan.total }) }}
            </span>
            <span v-else>{{ t('slime.progress.elapsed', { seconds: scan.elapsed }) }}</span>
          </div>
          <div v-if="ringArea" class="progress-line mono muted">
            {{ t('slime.progress.best', { score: Math.round(scan.best), area: ringArea }) }}
          </div>
          <div v-if="scan.stats.percentile !== undefined" class="progress-line mono muted">
            {{ t('slime.progress.percentile', { pct: Math.round(Number(scan.stats.percentile) * 1000) / 10 }) }}
          </div>
        </div>

        <div v-if="errorText" class="error-text">{{ errorText }}</div>

        <div class="secondary-actions">
          <button class="btn sm" @click="saveDefaults">{{ t('action.saveAsDefault') }}</button>
          <button class="btn sm" @click="applySettings">{{ t('action.applyDefaults') }}</button>
        </div>

        <div class="hint block-hint">{{ t('slime.hint.exactLimit') }}</div>
      </div>
    </section>

    <section class="panel map-panel">
        <div class="panel-head">
          <span>{{ t('slime.panel.map') }}</span>
          <div class="head-actions">
            <button class="btn sm" :class="{ primary: showResults }" @click="showResults = !showResults">
              {{ t('slime.action.results') }}
            </button>
            <button class="btn sm" :class="{ primary: showHeat }" @click="toggleHeat">
              {{ t('slime.action.heat') }}
            </button>
            <button class="btn sm" :disabled="selected === null" @click="recommendPerimeter">
              {{ t('slime.action.perimeter') }}
            </button>
            <button class="btn sm" :disabled="selected === null" @click="focusSelected">
              {{ t('slime.action.locate') }}
            </button>
            <button class="btn sm" @click="mapRef?.zoomIn()">＋</button>
            <button class="btn sm" @click="mapRef?.zoomOut()">－</button>
            <button class="btn sm" @click="mapRef?.reset()">{{ t('slime.action.reset') }}</button>
          </div>
        </div>
        <div class="map-body">
          <SlimeMap
            v-if="mapMeta && mapCells"
            ref="mapRef"
            :cells="mapCells"
            :heat="mapHeat"
            :width="mapMeta.width"
            :height="mapMeta.height"
            :x0="mapMeta.x0"
            :z0="mapMeta.z0"
            :markers="markers"
            :selected="selected"
            :ring-inner="Number(ringInner) || 24"
            :ring-outer="Number(ringOuter) || 128"
            :perimeter="perimeter"
            @select="onMapSelect"
          />
          <div v-else class="empty">{{ t('slime.empty.map') }}</div>
          <div v-if="perimeterOpen" class="perimeter-bar">
            <div class="perimeter-title">
              <strong>
                {{ t('slime.perimeter.title', { size: perimeter ? perimeter.size : perimeterSize }) }}
              </strong>
              <span v-if="perimeter" class="muted mono">
                {{ perimeter.size * 16 }}×{{ perimeter.size * 16 }} {{ t('slime.unit.block') }}
                · {{ t('slime.perimeter.chunks') }} ({{ perimeter.cx0 }}, {{ perimeter.cz0 }})–({{
                  perimeter.cx0 + perimeter.size - 1
                }}, {{ perimeter.cz0 + perimeter.size - 1 }})
              </span>
            </div>
            <div v-if="perimeter" class="perimeter-corners mono">
              <span>{{ t('slime.perimeter.nw') }} ({{ perimeter.x0 }}, {{ perimeter.z0 }})</span>
              <span>{{ t('slime.perimeter.ne') }} ({{ perimeter.x1 }}, {{ perimeter.z0 }})</span>
              <span>{{ t('slime.perimeter.sw') }} ({{ perimeter.x0 }}, {{ perimeter.z1 }})</span>
              <span>{{ t('slime.perimeter.se') }} ({{ perimeter.x1 }}, {{ perimeter.z1 }})</span>
            </div>
            <div class="perimeter-actions">
              <label class="perimeter-size">
                {{ t('slime.field.perimeter') }}
                <input
                  v-model.number="perimeterSize"
                  type="number"
                  :min="perimeterMin"
                  max="65"
                  step="2"
                  @change="applyPerimeter"
                />
                {{ t('slime.unit.chunk') }}
              </label>
              <button class="btn sm" :disabled="!perimeter" @click="copy(perimeterCornersText())">
                {{ t('slime.action.copy') }}
              </button>
              <button class="btn ghost sm" @click="closePerimeter">×</button>
            </div>
          </div>
          <div v-if="perimeterError" class="perimeter-error">{{ perimeterError }}</div>
          <div class="legend">
            <span><i class="dot slime" />{{ t('slime.legend.slime') }}</span>
            <span><i class="dot marker" />{{ t('slime.legend.marker') }}</span>
            <span><i class="dot ring" />{{ t('slime.legend.ring') }}</span>
          </div>
        </div>
      </section>

      <section v-if="showResults" class="panel results-panel">
        <div class="panel-head">
          <span>{{ t('slime.panel.results') }} · {{ results.length }}</span>
          <div class="head-actions">
            <button class="btn sm" :disabled="!results.length" @click="exportCsv">
              {{ t('slime.action.export') }}
            </button>
          </div>
        </div>
        <div class="result-body">
          <div v-if="!results.length" class="empty">{{ t('slime.empty.results') }}</div>
          <table v-else class="result-table">
            <thead>
              <tr>
                <th>#</th>
                <th>X</th>
                <th>Z</th>
                <th>{{ t('slime.col.score') }}</th>
                <th>{{ t('slime.col.coverage') }}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="(item, index) in results"
                :key="item.rank"
                :class="{ active: index === selected }"
                @click="select(index)"
              >
                <td class="mono">{{ item.rank }}</td>
                <td class="mono">{{ item.x }}</td>
                <td class="mono">{{ item.z }}</td>
                <td class="mono">{{ Math.round(item.score) }}</td>
                <td class="mono">{{ (item.coverage * 100).toFixed(1) }}%</td>
                <td class="row-actions">
                  <button class="btn ghost sm" @click.stop="copy(`${item.x} ${item.z}`)">
                    {{ t('slime.action.copy') }}
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
  </div>
</template>

<style scoped>
.workbench {
  height: 100%;
  display: grid;
  grid-template-columns: 340px minmax(0, 1fr) 300px;
  gap: 14px;
  min-height: 0;
  min-width: 0;
}

.workbench.results-collapsed {
  grid-template-columns: 340px minmax(0, 1fr);
}

@media (max-width: 1240px) {
  .workbench {
    grid-template-columns: 320px minmax(0, 1fr);
    grid-template-rows: minmax(0, 1fr) 260px;
  }

  .params-panel {
    grid-row: 1 / span 2;
  }

  .map-panel {
    grid-column: 2;
    grid-row: 1;
  }

  .results-panel {
    grid-column: 2;
    grid-row: 2;
  }
}

@media (max-width: 900px) {
  .workbench {
    grid-template-columns: 1fr;
    grid-template-rows: auto minmax(320px, 1fr) 260px;
    overflow: auto;
  }

  .params-panel,
  .map-panel,
  .results-panel {
    grid-column: 1;
    grid-row: auto;
  }
}

.map-panel {
  min-width: 0;
  min-height: 0;
}

.params-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.params-body .field {
  margin-bottom: 0;
}

.seed-field {
  position: relative;
}

.combo {
  position: relative;
}

.seed-input {
  padding-right: 30px;
}

.combo-arrow {
  position: absolute;
  top: 50%;
  right: 6px;
  width: 22px;
  height: 24px;
  transform: translateY(-50%);
  border: 0;
  border-radius: 5px;
  background: transparent;
  color: var(--muted);
  font-size: 11px;
  line-height: 1;
  cursor: pointer;
}

.combo-arrow:hover {
  background: var(--surface-2);
  color: var(--text);
}

.combo-menu {
  position: absolute;
  top: calc(100% + 4px);
  right: 0;
  left: 0;
  z-index: 30;
  max-height: 240px;
  overflow: auto;
  padding: 4px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--surface);
  box-shadow: 0 10px 28px rgba(0, 0, 0, 0.14);
}

.combo-title {
  padding: 4px 8px;
  color: var(--muted);
  font-size: 10px;
}

.combo-item {
  display: block;
  width: 100%;
  padding: 6px 8px;
  border: 0;
  border-radius: 5px;
  background: transparent;
  color: var(--text);
  font-size: 12px;
  text-align: left;
  cursor: pointer;
}

.combo-item:hover,
.combo-item.active {
  background: var(--surface-2);
}

.combo-empty {
  padding: 6px 8px;
  color: var(--muted);
  font-size: 11px;
}

.combo-clear {
  display: block;
  width: 100%;
  margin-top: 2px;
  padding: 6px 8px;
  border: 0;
  border-top: 1px solid var(--line);
  background: transparent;
  color: var(--muted);
  font-size: 11px;
  text-align: left;
  cursor: pointer;
}

.combo-clear:hover {
  color: var(--danger);
}

.hint {
  color: var(--muted);
  font-size: 11px;
  line-height: 1.6;
}

.block-hint {
  margin-top: 4px;
}

.actions {
  display: flex;
  gap: 8px;
}

.actions .primary {
  flex: 1;
}

.secondary-actions {
  display: flex;
  gap: 8px;
}

.secondary-actions .btn {
  flex: 1;
}

.progress-box {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.progress {
  height: 6px;
  border-radius: 3px;
  background: var(--surface-2);
  overflow: hidden;
}

.progress-bar {
  height: 100%;
  background: var(--brand);
  transition: width 0.2s ease;
}

.progress-line {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  font-size: 11px;
}

.error-text {
  color: var(--danger);
  font-size: 12px;
}

.map-body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  position: relative;
}

.perimeter-bar {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 7px 10px;
  border-top: 1px solid var(--line);
  background: rgba(245, 158, 11, 0.06);
}

.perimeter-title {
  display: flex;
  align-items: baseline;
  gap: 8px;
  font-size: 11px;
}

.perimeter-corners {
  display: grid;
  grid-template-columns: repeat(2, max-content);
  gap: 0 18px;
  color: var(--muted);
  font-size: 10.5px;
}

.perimeter-actions {
  display: flex;
  align-items: center;
  gap: 6px;
}

.perimeter-size {
  display: flex;
  align-items: center;
  gap: 4px;
  color: var(--muted);
  font-size: 11px;
}

.perimeter-size input {
  width: 58px;
  height: 24px;
  padding: 0 6px;
}

.perimeter-error {
  padding: 5px 10px;
  border-top: 1px solid var(--line);
  color: var(--danger);
  font-size: 11px;
}

.legend {
  display: flex;
  gap: 14px;
  padding: 6px 12px;
  border-top: 1px solid var(--line);
  color: var(--muted);
  font-size: 11px;
}.legend span {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  display: inline-block;
}

.dot.slime {
  background: #10b981;
}

.dot.marker {
  background: #0f9d8a;
}

.dot.ring {
  border: 1px dashed #ff6a4d;
  background: transparent;
}

.results-panel {
  min-width: 0;
  min-height: 0;
}

.result-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
}

.result-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 10.5px;
}

.result-table th {
  position: sticky;
  top: 0;
  z-index: 1;
  padding: 6px 6px;
  border-bottom: 1px solid var(--line);
  background: var(--surface);
  color: var(--muted);
  font-weight: 400;
  text-align: left;
  white-space: nowrap;
}

.result-table td {
  padding: 6px 6px;
  border-bottom: 1px solid var(--line);
  white-space: nowrap;
}

.result-table tbody tr {
  cursor: pointer;
}

.result-table tbody tr:hover {
  background: var(--surface-2);
}

.result-table tbody tr.active {
  background: var(--select-bg);
}

.row-actions {
  text-align: right;
}

.head-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}
</style>
