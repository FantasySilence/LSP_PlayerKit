<!--
  史莱姆区块查找器 · 主界面（View.vue）

  职责：收集搜索参数（种子 / 中心 / 半径 / 圆环 / 模式 / TopN），调用后端 scan_start 启动扫描，
  每 300ms 轮询 scan_status 取进度与结果，再把结果列表、概览图、坐标查看、空置域卡片串联起来。

  单位约定：中心、半径、模拟距离、NMS 都以「区块」计；半径 N 区块对应的方块范围是 ±N×16，
  即边长 2N×16 方块。坐标输入框、结果坐标、查看点则是方块坐标，取图时统一除以 16 换成区块。
-->

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { callTool, invoke } from '../../platform/bridge'
import { t } from '../../platform/i18n'
import { getSettings, loadSettings, saveSettings } from '../../platform/settings'
import { notify, notifyError } from '../../platform/toast'
import type { ToolDef } from '../../platform/types'
import SlimeMap from './SlimeMap.vue'

// ===== 数据结构 =====
// 后端返回的一条命中：x / z 是方块坐标，chunkX / chunkZ 是所在区块，
// score 为圆环覆盖评分，coverage 为覆盖比例（0~1）
interface SlimeResult {
  rank: number
  x: number
  z: number
  chunkX: number
  chunkZ: number
  score: number
  coverage: number
}

// 挂机圆环：内径与外径的单位是方块，area 是圆环覆盖的区块面积，由后端算好
interface RingInfo {
  inner: number
  outer: number
  area: number
}

// 扫描任务状态：state 离开 running 即停止轮询；progress 为 0~1，
// best 为当前最高分；stats 里放 percentile 等附加指标
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

// map 接口的位图结果：bits 为 base64 编码的 0/1 位串（行优先），
// stride 表示「每格代表 N 个区块」，概览图用它降采样；heat 为可选热力图字节
interface MapPayload {
  x0: number
  z0: number
  width: number
  height: number
  bits: string
  heat?: string
  stride?: number
}

const props = defineProps<{ tool: ToolDef }>()

// ===== 响应式状态：参数面板 =====
// 种子允许数字或文本，统一按字符串提交
const seed = ref<string>('0')
// 搜索中心：方块坐标，提交前再取整
const centerX = ref<number | string>(-32)
const centerZ = ref<number | string>(-8)
// 搜索半径：单位是「区块」；方块范围 = 中心 ± 半径 × 16
const radiusChunks = ref<number | string>(4096)
// 查看点：方块坐标，用于手动定位到指定位置看图
const viewX = ref<number | string>(-32)
const viewZ = ref<number | string>(-8)
// 挂机圆环内径 / 外径（方块）与模拟距离（区块）
const ringInner = ref<number | string>(24)
const ringOuter = ref<number | string>(128)
const simDistance = ref<number | string>(8)
// 扫描模式：auto 交给后端按范围自动挑 exact / sample
const mode = ref<'auto' | 'exact' | 'sample'>('auto')
// TopN 最多保留多少条结果；NMS 为结果间最小间隔（区块），0 表示不做非极大值抑制
const topN = ref<number | string>(100)
const nmsChunks = ref<number | string>(8)
// 采样次数：仅 sample 模式使用，exact 模式由后端忽略
const samples = ref<number | string>(50000)

// ===== 响应式状态：种子本地历史 =====
// 历史存 localStorage，最多 SEED_HISTORY_MAX 条，只用于输入框下拉提示
const seedHistory = ref<string[]>([])
const historyOpen = ref(false)
const historyIndex = ref(-1)
const seedCombo = ref<HTMLElement | null>(null)
const SEED_HISTORY_KEY = 'lspkit.slime.seedHistory'
const SEED_HISTORY_MAX = 12

// ===== 响应式状态：扫描与结果 =====
// busy 表示扫描进行中（按钮禁用、状态徽标变橙）
const busy = ref(false)
const scanId = ref('')
const scan = ref<ScanState | null>(null)
// results 为最终结果；selected 是结果列表下标（不是 rank），null 表示未选中
const results = ref<SlimeResult[]>([])
const selected = ref<number | null>(null)
// ringArea 为当前圆环覆盖的区块面积，用于进度区的「最高分」提示
const ringArea = ref(0)
const errorText = ref('')

// ===== 响应式状态：地图位图 =====
// mapCells 是 0/1 的史莱姆位图，mapHeat 是可选热力，mapMeta 描述范围与 stride
const mapCells = ref<Uint8Array | null>(null)
const mapHeat = ref<Uint8Array | null>(null)
const mapMeta = ref<{ x0: number; z0: number; width: number; height: number; stride: number } | null>(null)
// probe 为手动查看点（方块坐标）；viewSpan 是本次取图的视口边长（区块）
const probe = ref<{ x: number; z: number } | null>(null)
const viewSpan = ref(0)

// 搜索中心标记只在概览图（stride > 1）出现；局部图不画，避免与查看点混淆
const searchCenter = computed<{ x: number; z: number } | null>(() => {
  if (!mapMeta.value || (mapMeta.value.stride || 1) <= 1) return null
  const x = Number(centerX.value)
  const z = Number(centerZ.value)
  if (!Number.isFinite(x) || !Number.isFinite(z)) return null
  return { x, z }
})
// 热力图开关、结果侧栏开关
const showHeat = ref(false)
const showResults = ref(true)
// 空置域卡片：边长按「区块」计，输入值最终会夹到 [最小边长, 65]
const perimeterSize = ref<number | string>(21)
const perimeterOpen = ref(false)
// perimeter 是已生效的空置域：cx0/cz0 为左上角区块，x0/z0/x1/z1 为方块包围盒
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
// 子组件 SlimeMap 的实例，用来调用它暴露的 reset / focus / focusPoint / zoomIn 等方法
const mapRef = ref<InstanceType<typeof SlimeMap> | null>(null)

// 轮询定时器 id；0 表示未在轮询
let pollTimer = 0

// 进度条比例：夹在 0~1，避免后端异常值撑破宽度
const progress = computed(() => Math.min(1, Math.max(0, scan.value?.progress ?? 0)))
// 状态徽标文案：无任务时显示 idle，否则取 slime.state.<state> 的译文
const stateLabel = computed(() => {
  const state = scan.value?.state
  if (!state) return t('slime.state.idle')
  return t(`slime.state.${state}`)
})
// 传给地图的结果标记，只保留画图需要的坐标与名次
const markers = computed(() =>
  results.value.map((item) => ({ x: item.x, z: item.z, rank: item.rank })),
)

// 种子下拉的候选：有输入时按子串过滤，无输入时显示全部历史
const seedSuggestions = computed(() => {
  const query = String(seed.value).trim().toLowerCase()
  if (!query) return seedHistory.value
  return seedHistory.value.filter((item) => item.toLowerCase().includes(query))
})

// ===== 种子历史（localStorage） =====
// 读取历史：解析失败或 localStorage 不可用时退化成空数组
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

// 写入历史：整体序列化，失败时只影响持久化，不影响本次会话
function persistSeedHistory(): void {
  try {
    localStorage.setItem(SEED_HISTORY_KEY, JSON.stringify(seedHistory.value))
  } catch {
    /* localStorage 不可用时只保留本次会话的历史 */
  }
}

// 记住种子：已存在则移到最前，再截断到上限（最近的排最前）
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

// 键盘导航：上下键在候选间循环，回车确认，Esc 收起
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

// 点击下拉外部时收起；用捕获阶段监听，保证先于输入框自身事件
function onDocumentPointer(event: PointerEvent): void {
  if (!historyOpen.value) return
  const combo = seedCombo.value
  if (combo && !combo.contains(event.target as Node)) historyOpen.value = false
}

// ===== 圆环与空置域换算 =====
// 空置域允许的最小边长，随有效外径实时变化（模板里作为输入框 min）
const perimeterMin = computed(() => minPerimeterSize(effectiveRingOuter()))

// 有效外径（方块）：先夹到 [1, 128]，再被模拟距离截断——模拟距离以区块计，×16 换成方块
function effectiveRingOuter(): number {
  const outer = Math.round(Number(ringOuter.value) || 128)
  const sim = Math.round(Number(simDistance.value) || 8)
  return Math.min(Math.max(1, outer), Math.max(1, sim) * 16)
}

// 空置域最小边长（区块）：外径 ÷ 8 向上取整再 +1，保证方框能包住整圈挂机范围
function minPerimeterSize(outer: number): number {
  return Math.ceil(outer / 8 + 1)
}

// 数字校验：非数字时抛出带字段名的提示，交给 notifyError 统一展示
function toNumber(value: number | string, label: string): number {
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) throw new Error(t('slime.msg.notNumber', { label }))
  return parsed
}

// ===== 设置加载 / 保存 =====
// 读取该工具的默认设置并回填各输入框；查看点默认跟随搜索中心
async function applySettings(): Promise<void> {
  const data = await loadSettings(props.tool.id)
  seed.value = String(data.seed ?? '0')
  centerX.value = Number(data.centerX ?? -32)
  centerZ.value = Number(data.centerZ ?? -8)
  viewX.value = Number(data.centerX ?? -32)
  viewZ.value = Number(data.centerZ ?? -8)
  ringInner.value = Number(data.ringInner ?? 24)
  ringOuter.value = Number(data.ringOuter ?? 128)
  simDistance.value = Number(data.simDistance ?? 8)
  topN.value = Number(data.topN ?? 100)
  nmsChunks.value = Number(data.nmsChunks ?? 8)
  mode.value = (data.mode as 'auto' | 'exact' | 'sample') ?? 'auto'
  samples.value = Number(data.samples ?? 50000)
  perimeterSize.value = Number(data.perimeterChunks ?? 21)
}

// 保存为默认：先取现有设置再覆盖本次参数，保留其它工具可能写入的键
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

// ===== 搜索：启动 / 轮询 / 停止 =====
// 把「中心 + 半径（区块）」换算成后端要的方块包围盒，并做世界边界检查
// 半径 N 区块 ⇒ half = N × 16 方块，范围是 [中心 - half, 中心 + half]
function areaPayload() {
  const cx = toNumber(centerX.value, t('slime.field.centerX'))
  const cz = toNumber(centerZ.value, t('slime.field.centerZ'))
  const radius = Math.abs(toNumber(radiusChunks.value, t('slime.field.radius')))
  if (radius <= 0) throw new Error(t('slime.msg.badRadius'))
  const half = radius * 16
  if (Math.abs(cx) + half > 30_000_000 || Math.abs(cz) + half > 30_000_000) {
    throw new Error(t('slime.msg.outOfWorld'))
  }
  return { x0: cx - half, z0: cz - half, x1: cx + half, z1: cz + half }
}

// 启动扫描：先清空上一次的结果与地图状态，再 scan_start，成功后开始 300ms 轮询
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
  probe.value = null
  viewSpan.value = 0
  mapMeta.value = null
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

// 轮询一次 scan_status：running 时只更新进度；done / aborted / error 时停表并分发结果
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
        selected.value = null
        if (results.value.length) void loadOverview()
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

// 主动停止：发 scan_stop；真正结束仍以随后一次轮询的状态为准
async function stop(): Promise<void> {
  if (!scanId.value) return
  try {
    await callTool('slime', 'scan_stop', { scanId: scanId.value })
    notify('info', t('slime.msg.stopping'))
  } catch (error) {
    notifyError(error)
  }
}

// 清掉轮询定时器；重复调用安全
function stopPolling(): void {
  if (pollTimer) {
    window.clearInterval(pollTimer)
    pollTimer = 0
  }
}

// ===== 位图解码 =====
// base64 → 字节数组
function decodeBytes(text: string): Uint8Array {
  const raw = atob(text)
  const bytes = new Uint8Array(raw.length)
  for (let index = 0; index < raw.length; index += 1) bytes[index] = raw.charCodeAt(index)
  return bytes
}

// 位串 → 0/1 数组：每个字节高位在前，index >> 3 定位字节、7 - (index & 7) 定位位
function decodeBits(text: string, count: number): Uint8Array {
  const bytes = decodeBytes(text)
  const cells = new Uint8Array(count)
  for (let index = 0; index < count; index += 1) {
    cells[index] = (bytes[index >> 3] >> (7 - (index & 7))) & 1
  }
  return cells
}

// ===== 地图取数 =====
// 取某条结果周围的局部图（固定 192×192 区块，stride=1 即一格一区块），
// 取完后按 focusIndex 决定是整体适配还是聚焦到该结果
async function loadMap(item: SlimeResult, focusIndex: number | null = null): Promise<void> {
  const size = 192
  const cx = Math.floor(item.x / 16)
  const cz = Math.floor(item.z / 16)
  // 让结果大致居中：左上角 = 结果区块 - size/2
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
    // 记录位图范围；stride 缺省视为 1（一格一区块）
    mapMeta.value = {
      x0: data.x0,
      z0: data.z0,
      width: data.width,
      height: data.height,
      stride: data.stride ?? 1,
    }
    // 等 DOM 更新后再操作子组件，否则 mapRef 可能还没挂载
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

// 查找完成后的概览：覆盖整个搜索范围（含中心点）；范围太大时用 stride 按每格 N 区块采样
async function loadOverview(): Promise<void> {
  const cx = Number(centerX.value)
  const cz = Number(centerZ.value)
  const radius = Math.abs(Number(radiusChunks.value))
  if (!Number.isFinite(cx) || !Number.isFinite(cz) || !Number.isFinite(radius) || radius <= 0) return
  // span：搜索范围边长（区块）= 2 × 半径
  const span = Math.max(1, Math.ceil(radius * 2))
  // stride：每格代表 N 个区块；保证总格数不超过 MAX_VIEW_CHUNKS（超了就降采样）
  const stride = Math.max(1, Math.ceil(span / MAX_VIEW_CHUNKS))
  // cells：实际请求的格数；整体居中，半宽按「格数 × stride」折算
  const cells = Math.max(1, Math.ceil(span / stride))
  const halfSpan = Math.floor((cells * stride) / 2)
  // 中心由方块换成区块，再向左上偏移半宽
  const x0 = Math.floor(cx / 16) - halfSpan
  const z0 = Math.floor(cz / 16) - halfSpan
  try {
    const data = await callTool<MapPayload>('slime', 'map', {
      seed: String(seed.value),
      x0,
      z0,
      width: cells,
      height: cells,
      stride,
      heat: false,
      ringInner: Math.round(toNumber(ringInner.value, 'inner')),
      ringOuter: Math.round(toNumber(ringOuter.value, 'outer')),
      simDistance: Math.round(toNumber(simDistance.value, 'sim')),
    })
    mapCells.value = decodeBits(data.bits, data.width * data.height)
    mapHeat.value = null
    mapMeta.value = {
      x0: data.x0,
      z0: data.z0,
      width: data.width,
      height: data.height,
      stride: data.stride ?? stride,
    }
    // 概览图不带查看点；旧的查看点与空置域一并清掉，避免画在错误位置
    probe.value = null
    viewSpan.value = 0
    perimeter.value = null
    perimeterOpen.value = false
    perimeterError.value = ''
    await nextTick()
    mapRef.value?.reset()
  } catch (error) {
    notifyError(error)
  }
}

// 手动查看坐标：视口边长与「搜索半径」一致（2 × 半径），最多 1024 区块
const MAX_VIEW_CHUNKS = 1024

// 取图并定位到某个坐标；成功后把该点设为「查看点」
async function showPoint(bx: number, bz: number, resetView = true): Promise<boolean> {
  const radius = Math.abs(Number(radiusChunks.value))
  if (!Number.isFinite(radius) || radius <= 0) {
    notify('error', t('slime.msg.badRadius'))
    return false
  }
  if (Math.abs(bx) > 30_000_000 || Math.abs(bz) > 30_000_000) {
    notify('error', t('slime.msg.outOfWorld'))
    return false
  }
  // wanted：按 2 × 半径 算出的理想边长（区块）；size 再夹到 MAX_VIEW_CHUNKS
  const wanted = Math.max(1, Math.ceil(radius * 2))
  const size = Math.min(MAX_VIEW_CHUNKS, wanted)
  // 以查看点所在区块为中心取图
  const x0 = Math.floor(bx / 16) - Math.floor(size / 2)
  const z0 = Math.floor(bz / 16) - Math.floor(size / 2)
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
    mapMeta.value = {
      x0: data.x0,
      z0: data.z0,
      width: data.width,
      height: data.height,
      stride: data.stride ?? 1,
    }
    // 记录查看点与本次视口边长（区块），后续圆环 / 空置域都以查看点为准
    probe.value = { x: bx, z: bz }
    viewSpan.value = size
    await nextTick()
    if (resetView) {
      // 自动缩放：以查看点为中心放大到约 40×40 区块（地图本身仍是 2×半径 的范围）
      mapRef.value?.focusPoint(bx, bz, Math.min(40, size))
    }
    if (size < wanted) notify('info', t('slime.msg.viewClamped', { size }))
    return true
  } catch (error) {
    notifyError(error)
    return false
  }
}

// 「查看坐标」按钮：校验输入 → 取图并定位 → 按当前查看点重算空置域
async function viewPoint(): Promise<void> {
  let bx = 0
  let bz = 0
  try {
    bx = Math.round(toNumber(viewX.value, t('slime.field.viewX')))
    bz = Math.round(toNumber(viewZ.value, t('slime.field.viewZ')))
  } catch (error) {
    notifyError(error)
    return
  }
  selected.value = null
  perimeter.value = null
  perimeterOpen.value = false
  perimeterError.value = ''
  if (await showPoint(bx, bz)) applyPerimeter()
}

// 热力图等场景下，按当前查看点重新取图（保持缩放）
async function reloadPoint(): Promise<void> {
  const point = probe.value
  if (!point) return
  await showPoint(point.x, point.z, false)
  applyPerimeter()
}

// 结果是否落在当前位图覆盖范围内：真实跨度是「格数 × stride」（概览图一格 N 区块）
function mapContains(item: SlimeResult): boolean {
  const meta = mapMeta.value
  if (!meta) return false
  const cx = item.x / 16
  const cz = item.z / 16
  const spanX = meta.width * (meta.stride || 1)
  const spanZ = meta.height * (meta.stride || 1)
  return cx >= meta.x0 && cx < meta.x0 + spanX && cz >= meta.z0 && cz < meta.z0 + spanZ
}

// 选中结果：清掉查看点与空置域（上下文切到该结果），局部图能覆盖就直接聚焦，
// 否则（概览图或超出当前范围）重新取一张以该结果为中心的局部图
function select(index: number): void {
  if (index < 0 || index >= results.value.length) return
  selected.value = index
  probe.value = null
  viewSpan.value = 0
  perimeter.value = null
  perimeterOpen.value = false
  perimeterError.value = ''
  const item = results.value[index]
  if ((mapMeta.value?.stride ?? 1) === 1 && mapContains(item)) {
    mapRef.value?.focus(index)
  } else {
    void loadMap(item, index)
  }
}

// 空置域 / 圆环的目标：优先当前查看点，其次选中的结果
function perimeterTarget(): { x: number; z: number } | null {
  if (probe.value) return probe.value
  if (selected.value !== null) {
    const item = results.value[selected.value]
    if (item) return { x: item.x, z: item.z }
  }
  return null
}

// 「推荐空置域」按钮：先确认有目标点，再打开卡片并按目标重算
function recommendPerimeter(): void {
  if (!perimeterTarget()) {
    notify('info', t('slime.msg.perimeterNoSelection'))
    return
  }
  perimeterOpen.value = true
  applyPerimeter()
}

// 收起空置域卡片：同时丢弃已算好的方框与错误提示
function closePerimeter(): void {
  perimeterOpen.value = false
  perimeter.value = null
  perimeterError.value = ''
}

function applyPerimeter(): void {
  const target = perimeterTarget()
  if (!target) {
    perimeterOpen.value = false
    return
  }
  perimeterOpen.value = true
  // 最小边长由「有效外径」决定；输入非法（空 / 0 / NaN）只报错，不画方框
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
  // 上限 65 区块（65×16 方块）；超出的输入会被夹回该值
  size = Math.min(65, size)
  perimeterSize.value = size
  perimeterError.value = ''
  // half：半边长（方块）= size × 16 ÷ 2；左上角对齐到区块边界
  const half = size * 8
  const cx0 = Math.round((target.x - half) / 16)
  const cz0 = Math.round((target.z - half) / 16)
  const x0 = cx0 * 16
  const z0 = cz0 * 16
  // x1 / z1 用 -1 收边，使包围盒正好覆盖 size×16 方块
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

// 四个角的方块坐标文案（NW / NE / SW / SE），供「复制」使用
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

// 地图上点中标记：只改选中项，不复位视图
function onMapSelect(index: number): void {
  if (index < 0 || index >= results.value.length) return
  selected.value = index
  // 在地图上点结果即切换上下文：查看点与它的空置域一并收掉
  probe.value = null
  viewSpan.value = 0
  perimeter.value = null
  perimeterOpen.value = false
  perimeterError.value = ''
}

// 「定位」按钮：优先聚焦选中结果，其次聚焦查看点；两者都没有时按钮为禁用态
function focusSelected(): void {
  if (selected.value !== null) {
    const item = results.value[selected.value]
    if ((mapMeta.value?.stride ?? 1) === 1 && mapContains(item)) {
      mapRef.value?.focus(selected.value)
    } else {
      void loadMap(item, selected.value)
    }
    return
  }
  if (probe.value) mapRef.value?.focusPoint(probe.value.x, probe.value.z)
}

// 切换热力图：热力数据随取图一起返回，所以要按当前上下文重取一张图
async function toggleHeat(): Promise<void> {
  showHeat.value = !showHeat.value
  if (selected.value !== null) {
    // 有选中结果：重取以该结果为中心的局部图（同时保持视图聚焦）
    await loadMap(results.value[selected.value], selected.value)
  } else if (probe.value) {
    // 有查看点：按查看点重取，保留当前缩放
    await reloadPoint()
  }
}

// 导出结果 CSV：表头固定，score 取整、coverage 保留 4 位小数；
// 文件名用「种子_范围左上角方块坐标」，避免多次导出互相覆盖
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

// 复制到剪贴板：优先浏览器 Clipboard API，不可用时退回后端 clipboard_write
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

// 外径 / 模拟距离变化会改变最小边长，卡片开着时立即重算
watch([ringOuter, simDistance], () => {
  if (perimeterOpen.value) applyPerimeter()
})

// 挂载：恢复种子历史、监听点击外部、加载默认设置
onMounted(async () => {
  loadSeedHistory()
  document.addEventListener('pointerdown', onDocumentPointer, true)
  try {
    await applySettings()
  } catch (error) {
    notifyError(error)
  }
})

// 卸载：移除全局监听并停掉轮询，防止组件销毁后仍在请求
onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', onDocumentPointer, true)
  stopPolling()
})
</script>

<template>
  <div class="workbench" :class="{ 'results-collapsed': !showResults }">
    <!-- 区块：参数面板 -->
    <section class="panel params-panel">
      <div class="panel-head">
        <span>{{ t('slime.panel.params') }}</span>
        <span class="badge" :class="{ warn: busy }">{{ stateLabel }}</span>
      </div>
      <div class="panel-body params-body">
        <!-- 种子输入 + 本地历史下拉（最多 12 条） -->
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

        <!-- 搜索范围：中心为方块坐标，半径为区块数 -->
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

        <!-- 搜索半径（区块）：方块范围 = 中心 ± 半径 × 16 -->
        <div class="field">
          <label class="field-label">
            <span>{{ t('slime.field.radius') }}</span>
            <span class="unit">{{ t('slime.unit.chunk') }}</span>
          </label>
          <input v-model.number="radiusChunks" class="input mono" type="number" min="1" step="1" />
          <div class="hint">{{ t('slime.hint.radius') }}</div>
        </div>

        <!-- 查看坐标（方块）：按当前半径取图并定位到该点 -->
        <div class="field">
          <label class="field-label">
            <span>{{ t('slime.field.view') }}</span>
            <span class="unit">{{ t('slime.unit.block') }}</span>
          </label>
          <div class="view-row">
            <input
              v-model.number="viewX"
              class="input mono"
              type="number"
              step="16"
              :aria-label="t('slime.field.viewX')"
              :placeholder="t('slime.field.viewX')"
            />
            <input
              v-model.number="viewZ"
              class="input mono"
              type="number"
              step="16"
              :aria-label="t('slime.field.viewZ')"
              :placeholder="t('slime.field.viewZ')"
            />
            <button class="btn primary sm" @click="viewPoint">{{ t('slime.action.viewPoint') }}</button>
          </div>
          <div class="hint">{{ t('slime.hint.view') }}</div>
        </div>

        <!-- 挂机圆环内径 / 外径（方块）：外径会被模拟距离截断 -->
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

        <!-- 模拟距离（区块）与扫描模式：auto 由后端按范围自动选 exact / sample -->
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

        <!-- TopN（保留条数）与 NMS 间隔（区块，0 表示关闭抑制） -->
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

        <!-- 采样次数：仅 sample 模式使用 -->
        <div class="field">
          <label class="field-label">{{ t('slime.field.samples') }}</label>
          <input v-model.number="samples" class="input mono" type="number" min="1000" step="1000" />
        </div>

        <!-- 开始 / 停止 -->
        <div class="actions">
          <button class="btn primary" :disabled="busy" @click="start">
            {{ t('slime.action.start') }}
          </button>
          <button class="btn" :disabled="!busy" @click="stop">
            {{ t('slime.action.stop') }}
          </button>
        </div>

        <!-- 进度：百分比、扫描格数 / 耗时、当前最高分与百分位 -->
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

        <!-- 保存当前参数为默认值 / 重新载入默认值 -->
        <div class="secondary-actions">
          <button class="btn sm" @click="saveDefaults">{{ t('action.saveAsDefault') }}</button>
          <button class="btn sm" @click="applySettings">{{ t('action.applyDefaults') }}</button>
        </div>

        <!-- 精确扫描上限说明：未设上限时始终精确；设置项填 0 表示不限制 -->
        <div class="hint block-hint">{{ t('slime.hint.exactLimit') }}</div>
      </div>
    </section>

    <!-- 区块：地图面板（工具栏 / 画布 / 空置域卡片 / 图例） -->
    <section class="panel map-panel">
        <div class="panel-head">
          <span>{{ t('slime.panel.map') }}</span>
          <!-- 工具栏：结果栏开关、热力、空置域、定位、全图、缩放、复位 -->
          <div class="head-actions">
            <button class="btn sm" :class="{ primary: showResults }" @click="showResults = !showResults">
              {{ t('slime.action.results') }}
            </button>
            <button class="btn sm" :class="{ primary: showHeat }" @click="toggleHeat">
              {{ t('slime.action.heat') }}
            </button>
            <button class="btn sm" :disabled="selected === null && !probe" @click="recommendPerimeter">
              {{ t('slime.action.perimeter') }}
            </button>
            <button class="btn sm" :disabled="selected === null && !probe" @click="focusSelected">
              {{ t('slime.action.locate') }}
            </button>
            <!-- 全图：重新按搜索范围取概览；处于概览（stride > 1）时按钮高亮 -->
            <button
              class="btn sm"
              :class="{ primary: mapMeta && (mapMeta.stride || 1) > 1 }"
              @click="loadOverview"
            >
              {{ t('slime.action.overview') }}
            </button>
            <button class="btn sm" @click="mapRef?.zoomIn()">＋</button>
            <button class="btn sm" @click="mapRef?.zoomOut()">－</button>
            <button class="btn sm" @click="mapRef?.reset()">{{ t('slime.action.reset') }}</button>
          </div>
        </div>
        <div class="map-body">
          <!-- 画布：位图 / 热力 / 圆环 / 标记 / 坐标轴都由子组件绘制 -->
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
            :probe="probe"
            :chunk-size="mapMeta.stride || 1"
            :center="searchCenter"
            @select="onMapSelect"
          />
          <div v-else class="empty">{{ t('slime.empty.map') }}</div>
          <!-- 空置域卡片：尺寸（区块）、四角方块坐标、复制 -->
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
          <!-- 图例：史莱姆 / 结果标记 / 圆环 / 搜索中心 / 查看点 / 概览说明 -->
          <div class="legend">
            <span><i class="dot slime" />{{ t('slime.legend.slime') }}</span>
            <span><i class="dot marker" />{{ t('slime.legend.marker') }}</span>
            <span><i class="dot ring" />{{ t('slime.legend.ring') }}</span>
            <span v-if="searchCenter"><i class="dot center" />{{ t('slime.legend.center') }}</span>
            <span v-if="probe"><i class="dot probe" />{{ t('slime.legend.probe') }}</span>
            <span v-if="mapMeta && (mapMeta.stride || 1) > 1" class="mono">
              {{ t('slime.map.overview', { n: mapMeta.stride }) }}
            </span>
          </div>
        </div>
      </section>

      <!-- 区块：结果侧栏（可整体收起，收起后地图占满宽度） -->
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
          <!-- 结果表格：点行选中并定位，行尾按钮复制「X Z」 -->
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
/* 区块：工作台栅格与响应式断点（参数 340 / 地图自适应 / 结果 300） */
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

/* 区块：参数面板（种子下拉、查看坐标行） */
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

.view-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.view-row .input {
  flex: 1 1 0;
  min-width: 0;
}

.view-row .btn {
  flex: 0 0 auto;
  white-space: nowrap;
}

.block-hint {
  margin-top: 4px;
}

/* 区块：主操作 / 次级操作 / 进度条 */
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

/* 区块：地图画布容器与空置域卡片 */
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

/* 区块：图例与色点 */
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

.dot.probe {
  background: #2f80ed;
}

.dot.center {
  border: 2px solid #d97706;
  background: transparent;
}

/* 区块：结果侧栏与表格（表头吸顶） */
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
