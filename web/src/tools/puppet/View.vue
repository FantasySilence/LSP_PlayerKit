<!--
  假人搬货 · 主工作台（页面级组件）。

  职责：把「站点表」与「订单」拼成一张运单计划，交给后端执行线程，
  再把执行进度与台账呈现在同一页。数据全部来自工具 puppet，
  本地只保存订单草稿（draft_save）与界面状态。

  布局：
  - 左栏：订单（始发 / 目的 / 盒数 / 操作）与站点表（分组筛选 + 搜索）；
  - 右栏：命令列表（生成 / 清除两页签），下方面板在执行进度与台账之间切换。

  口径：盒数 → 人数 ceil(盒数 / 36)，每 24 人一批，批与批之间要用户确认。
-->
<script setup lang="ts">
// ------------------------------ 依赖 ------------------------------ #
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'

import { callTool, invoke } from '../../platform/bridge'
import { t } from '../../platform/i18n'
import { getSettings, loadSettings, revision } from '../../platform/settings'
import { notify, notifyError } from '../../platform/toast'
import type { ToolDef } from '../../platform/types'
import ImportDialog from './ImportDialog.vue'
import StationDialog from './StationDialog.vue'
import StationPicker from './StationPicker.vue'
import type {
  DiagnoseCheck,
  ImportResult,
  Order,
  OrderDraft,
  Plan,
  PlanCommand,
  RunMeta,
  RunState,
  SpawnStation,
  Station,
} from './types'

// ------------------------------ props ------------------------------ #
// tool：工具定义，提供稳定的 id；设置项与 revision 都按这个 id 索引。
const props = defineProps<{ tool: ToolDef }>()

// ------------------------------ 常量 ------------------------------ #
// 维度取值与后端 constants.DIMENSIONS 一致；模板里按 dimension 拼 i18n key。
const DIMENSIONS = ['overworld', 'the_nether', 'the_end']

// ------------------------------ 状态 ------------------------------ #
// 站点表：左侧列表、两个选择器与台账反查共用同一份。
const stations = ref<Station[]>([])
// 台账：接口按时间正序返回，refreshHistory 里翻转成最新在上。
const orders = ref<Order[]>([])
// 订单区：始发 / 目的站点 id，直接 v-model 绑到两个 StationPicker。
const originId = ref('')
const destId = ref('')
// 盒数：允许输入框的字符串中间态，提交给后端前再转 Number。
const boxes = ref<number | string>(250)
// 操作口径：假人在始发地还是目的地生成，决定生成命令里的坐标。
const operation = ref<'spawn_at_origin' | 'spawn_at_dest'>('spawn_at_origin')
// 最近一次「生成」的计划；null 表示还没生成过，命令列表为空。
const plan = ref<Plan | null>(null)
// 命令页签：spawn 生成阶段 / kill 清除阶段。
const phase = ref<'spawn' | 'kill'>('spawn')
// 生成中：只用来禁用按钮，防止连点重复算计划。
const busy = ref(false)
// 站点搜索关键字：匹配名称与前缀，不区分大小写。
const search = ref('')
// 站点分组筛选：'*' 表示全部，其余是分组 tag 原值。
const stationGroupFilter = ref('*')
// 是否允许自动输入，来自设置；关闭时执行入口只提示、不发命令。
const allowExecute = ref(false)

// 站点新增 / 编辑弹窗；editing 为 null 表示新增。
const stationDialogOpen = ref(false)
// 正在编辑的站点；与 stationDialogOpen 一起决定弹窗内容。
const editing = ref<Station | null>(null)
// 导入弹窗（旧 stops.json / 纯文本）。
const importOpen = ref(false)
// 已点过一次删除的站点 id；3 秒内再点同一行才真正删除。
const deleteArmed = ref('')
// 撤销二次确认的定时器句柄。
let deleteTimer = 0

// ------------------------------ 执行状态 ------------------------------ #
// 当前执行的完整快照；每 300ms 用 run_status 的结果整体覆盖。
const run = ref<RunState | null>(null)
// 执行线程 id；run_continue / run_stop / run_status 都要带上它。
const runId = ref('')
// 轮询定时器句柄；null 表示当前没有轮询。
const polling = ref<number | null>(null)
// 生成阶段被中断时已生成的假人名，用于一键补 kill。
const cleanupNames = ref<string[]>([])
// 下方面板页签：run 执行进度 / ledger 台账。
const bottomTab = ref<'run' | 'ledger'>('run')

// 日志容器，用来判断是否已经滚到底部。
const logBox = ref<HTMLElement | null>(null)
// 是否贴底：用户往上翻日志后暂停自动滚动。
const logPinned = ref(true)
// 批间确认按钮的防抖标记，避免连点发出多次 run_continue。
const continueBusy = ref(false)

// 草稿是否已加载完；没加载完不许回写，避免用空值覆盖旧草稿。
const draftReady = ref(false)
// 草稿防抖定时器：输入停 400ms 才写一次。
let draftTimer = 0

// 从台账恢复的订单命令；非空时命令区显示它而不是当前计划。
const restored = ref<{ order: Order; commands: PlanCommand[] } | null>(null)

// 鼠标悬停的站点 id，用来展开该行备注。
const hoveredStation = ref('')

// 待确认的执行请求：确认弹窗点「执行」时才真正 run_start。
// 先把参数（命令 / 阶段 / meta / 每批命令数）攒好，避免确认期间订单被改。
const pending = ref<{
  commands: string[]
  phase: 'spawn' | 'kill'
  meta: RunMeta
  batchSize: number
} | null>(null)
// 执行确认弹窗（生成与补清理共用）。
const confirmOpen = ref(false)
// 环境自检弹窗。
const diagOpen = ref(false)
// 自检结果，逐行显示检查项、状态与说明。
const diagChecks = ref<DiagnoseCheck[]>([])

// ------------------------------ 计算属性 ------------------------------ #
// 站点列表：先按分组筛，再按名称或前缀做包含匹配。
const filteredStations = computed(() => {
  const keyword = search.value.trim().toLowerCase()
  const group = stationGroupFilter.value
  return stations.value.filter((station) => {
    if (group !== '*' && (station.group ?? '') !== group) return false
    if (!keyword) return true
    return (
      station.name.toLowerCase().includes(keyword) ||
      station.prefix.toLowerCase().includes(keyword)
    )
  })
})

// 站点表里出现过的分组，按出现顺序去重；空串代表「未分组」，也要保留。
const stationGroups = computed(() => {
  const result: string[] = []
  for (const station of stations.value) {
    const group = station.group ?? ''
    if (!result.includes(group)) result.push(group)
  }
  return result
})

// 站点表变化后，若正在筛选的分组已不存在就回到「全部」。
watch(stations, () => {
  if (
    stationGroupFilter.value !== '*' &&
    !stationGroups.value.includes(stationGroupFilter.value)
  ) {
    stationGroupFilter.value = '*'
  }
})

// 当前页签对应的命令：生成阶段或清除阶段。
const activeCommands = computed<PlanCommand[]>(() => {
  if (!plan.value) return []
  return phase.value === 'spawn' ? plan.value.commands : plan.value.killCommands
})

// 实际展示 / 执行 / 导出的命令：恢复态优先，否则用当前计划。
const displayCommands = computed<PlanCommand[]>(() =>
  restored.value ? restored.value.commands : activeCommands.value,
)

// 恢复条文案：第几张运单、哪个阶段、多少条命令。
const restoredLabel = computed(() => {
  if (!restored.value) return ''
  return t('puppet.history.restored', {
    no: restored.value.order.no,
    phase: t(`puppet.phase.${restored.value.order.phase}`),
    n: restored.value.commands.length,
  })
})

// 是否正在执行；用来禁用执行按钮、显示中断按钮。
const running = computed(() => run.value?.state === 'running')
// 停在批间闸门：发送线程在等用户点「继续下一批」。
const waitingContinue = computed(() => running.value && Boolean(run.value?.waiting))
// 状态文案：等待确认时单独一条 i18n，其余按 state 拼 key。
const runStateLabel = computed(() =>
  waitingContinue.value
    ? t('puppet.run.state.waiting')
    : t(`puppet.run.state.${run.value?.state ?? 'idle'}`),
)
// 进度百分比：已发送 / 总数，封顶 100，总数为 0 时给 0。
const runPercent = computed(() => {
  const total = run.value?.total ?? 0
  return total ? Math.min(100, Math.round(((run.value?.sent ?? 0) / total) * 100)) : 0
})

// ------------------------------ 日志滚动（cmd 风格） ------------------------------ #
// 只看最后一行日志：它变化就说明有新日志，用来触发贴底滚动。
const logTail = computed(() => {
  const logs = run.value?.logs ?? []
  return logs.length ? logs[logs.length - 1] : ''
})

// 滚动位置离底部不足 24px 视为「贴底」；用户往上翻后不再自动跟随。
function onLogScroll() {
  const box = logBox.value
  if (!box) return
  logPinned.value = box.scrollHeight - box.scrollTop - box.clientHeight < 24
}

// 等 DOM 更新完再滚到底；force=true 用于刚开始执行时强制贴底。
async function stickLogsToBottom(force = false) {
  if (!force && !logPinned.value) return
  await nextTick()
  const box = logBox.value
  if (box) box.scrollTop = box.scrollHeight
}

// 新日志到达时，按当前贴底状态决定是否跟随。
watch(logTail, () => {
  void stickLogsToBottom()
})

// 台账与提示里的站点名：有分组时「分组 · 名称」，否则只有名称。
function stationLabel(station: Station): string {
  return station.group ? `${station.group} · ${station.name}` : station.name
}

// 台账存的是站点 id，显示前反查；查不到（站点已删）就退回 id 本身。
function stationLabelById(id: string): string {
  const station = stations.value.find((item) => item.id === id)
  return station ? stationLabel(station) : id
}

// 拉站点表；选中的站点被删掉时兜底换一个，避免选择器显示空。
async function refreshStations() {
  const data = await callTool<{ stations: Station[] }>('puppet', 'stations_list')
  stations.value = data.stations
  const ids = new Set(stations.value.map((station) => station.id))
  if (!ids.has(originId.value)) originId.value = stations.value[0]?.id ?? ''
  if (!ids.has(destId.value)) {
    destId.value = stations.value.find((station) => station.id !== originId.value)?.id ?? ''
  }
}

// 台账按时间正序返回，这里翻转成最新在上，直接绑到表格。
async function refreshHistory() {
  const data = await callTool<{ orders: Order[] }>('puppet', 'history_list')
  orders.value = data.orders.slice().reverse()
}

// 从设置里取执行开关；关闭时所有执行入口只提示不发送。
function syncAllowExecute() {
  allowExecute.value = Boolean(getSettings(props.tool.id).allowExecute)
}

// 设置对象整体替换后 revision 会变，据此重新同步 allowExecute。
watch(
  () => revision[props.tool.id],
  () => syncAllowExecute(),
)

// ------------------------------ 订单草稿 ------------------------------ #
// 恢复上次留在订单区的选择；字段不可信（站点已删等）就跳过，不阻塞页面。
async function loadDraft() {
  try {
    const data = await callTool<{ draft: OrderDraft }>('puppet', 'draft_load')
    const draft = data?.draft
    if (draft) {
      const ids = new Set(stations.value.map((station) => station.id))
      if (draft.origin && ids.has(draft.origin)) originId.value = draft.origin
      if (draft.dest && ids.has(draft.dest) && draft.dest !== originId.value) {
        destId.value = draft.dest
      }
      if (draft.boxes > 0) boxes.value = draft.boxes
      if (draft.operation === 'spawn_at_origin' || draft.operation === 'spawn_at_dest') {
        operation.value = draft.operation
      }
    }
  } catch {
    // 草稿读不出来（旧数据 / 权限问题）不影响正常使用
  } finally {
    draftReady.value = true
  }
}

// 落盘前统一口径：盒数取 >=0 的整数，与后端校验保持一致。
function draftPayload() {
  return {
    origin: originId.value,
    dest: destId.value,
    boxes: Math.max(0, Math.trunc(Number(boxes.value) || 0)),
    operation: operation.value,
  }
}

// 立即写一次草稿（切换工具 / 卸载时用），失败不提示。
function flushDraft() {
  window.clearTimeout(draftTimer)
  return callTool('puppet', 'draft_save', draftPayload()).catch(() => undefined)
}

// 输入变化后延迟合并写入，避免每敲一个键就发一次桥接调用。
function scheduleDraftSave() {
  if (!draftReady.value) return
  window.clearTimeout(draftTimer)
  draftTimer = window.setTimeout(() => {
    void flushDraft()
  }, 400)
}

// 四个订单字段任一变化都触发防抖保存。
watch([originId, destId, boxes, operation], scheduleDraftSave)

// 生成运单：只让后端算计划，本地除了清掉恢复态不做别的。
async function generate() {
  if (!originId.value || !destId.value) {
    notify('info', t('puppet.empty.stations'))
    return
  }
  busy.value = true
  try {
    plan.value = await callTool<Plan>('puppet', 'plan', {
      origin: originId.value,
      dest: destId.value,
      boxes: Number(boxes.value),
      operation: operation.value,
    })
    // 每次重新生成都回到「生成」页签，并丢掉恢复态与待清理名单。
    phase.value = 'spawn'
    cleanupNames.value = []
    restored.value = null
  } catch (error) {
    notifyError(error)
  } finally {
    busy.value = false
  }
}

// 复制全部命令：恢复态与当前计划共用 displayCommands。
async function copyAll() {
  if (!displayCommands.value.length) {
    notify('info', t('puppet.msg.exportEmpty'))
    return
  }
  try {
    await invoke('clipboard_write', displayCommands.value.map((item) => item.text).join('\n'))
    notify('success', t('puppet.msg.copied'))
  } catch (error) {
    notifyError(error)
  }
}

// 导出 txt：恢复态用运单号命名，否则用站点与盒数，便于事后核对。
async function exportAll() {
  if (!displayCommands.value.length) {
    notify('info', t('puppet.msg.exportEmpty'))
    return
  }
  const name = restored.value
    ? `puppet_order_${restored.value.order.no}.txt`
    : `puppet_${originId.value}_${destId.value}_${plan.value?.boxes ?? 0}.txt`
  try {
    const result = await invoke<{ cancelled?: boolean }>(
      'file_save_text',
      name,
      displayCommands.value.map((item) => item.text).join('\n'),
      '',
    )
    if (result?.cancelled) return
    notify('success', t('puppet.msg.exported'))
  } catch (error) {
    notifyError(error)
  }
}

// 导出站点表 JSON：先由后端序列化，再走 file_save_text 选保存位置。
async function exportStations() {
  if (!stations.value.length) {
    notify('info', t('puppet.msg.noStations'))
    return
  }
  try {
    const data = await callTool<{ filename: string; text: string; count: number }>(
      'puppet',
      'stations_export',
      { format: 'json' },
    )
    const result = await invoke<{ cancelled?: boolean }>(
      'file_save_text',
      data.filename,
      data.text,
      '',
      false,
    )
    if (result?.cancelled) return
    notify('success', t('puppet.msg.stationsExported', { n: data.count }))
  } catch (error) {
    notifyError(error)
  }
}

// 从台账恢复一张运单的命令：只恢复文本，不改当前订单草稿。
function restoreOrder(order: Order) {
  const list = order.commands ?? []
  if (!list.length) {
    notify('info', t('puppet.msg.noCommandsSaved'))
    return
  }
  // 台账只存了命令文本，序号与阶段按当前运单补出来，bot / name 留空。
  restored.value = {
    order,
    commands: list.map((text, index) => ({
      index: index + 1,
      phase: order.phase,
      bot: 0,
      name: '',
      text,
      batch: 0,
    })),
  }
  notify('success', restoredLabel.value)
}

// 退出恢复态，命令列表回到当前计划。
function clearRestored() {
  restored.value = null
}

// 把计划 / 台账里的生成站点收敛成 SpawnStation；没有 id 视为无效。
function spawnStationOf(
  station: Plan['spawnStation'] | SpawnStation | null | undefined,
): SpawnStation | null {
  if (!station || !station.id) return null
  return {
    id: station.id,
    name: station.name,
    group: station.group ?? '',
    dimension: station.dimension,
  }
}

// 清空命令：丢掉计划与恢复态，顺带清掉待清理名单。
function clearCommands() {
  plan.value = null
  restored.value = null
  cleanupNames.value = []
  notify('success', t('puppet.msg.commandsCleared'))
}

// 台账「生成于」列：分组 · 名称 · 维度，缺字段就省略对应片段。
function spawnLabel(order: Order): string {
  const station = order.spawnStation ?? order.meta?.spawnStation
  if (!station?.name) return '—'
  const label = station.group ? `${station.group} · ${station.name}` : station.name
  const dimension = station.dimension ? t(`puppet.dim.${station.dimension}`) : ''
  return dimension ? `${label} · ${dimension}` : label
}

// ------------------------------ 站点 ------------------------------ #
// 新增（传 null）与编辑（传站点）共用同一个弹窗。
function openStation(station: Station | null) {
  editing.value = station
  stationDialogOpen.value = true
}

// 保存后后端回整张站点表，直接替换，避免本地只改一半。
async function saveStation(station: Station) {
  try {
    const data = await callTool<{ stations: Station[] }>('puppet', 'stations_save', { station })
    stations.value = data.stations
    stationDialogOpen.value = false
    notify('success', t('puppet.action.save'))
    // 首次保存后自动补上始发 / 目的，省得再点两次选择器。
    if (!originId.value) originId.value = data.stations[0]?.id ?? ''
    if (!destId.value) {
      destId.value = data.stations.find((item) => item.id !== originId.value)?.id ?? ''
    }
  } catch (error) {
    notifyError(error)
  }
}

// 二次确认：第一次点击只进入「待删除」态，3 秒内再点同一行才真删。
async function deleteStation(station: Station) {
  // 上次点的是别的站点（或已超时）：重新计时，只提示不删除。
  if (deleteArmed.value !== station.id) {
    deleteArmed.value = station.id
    notify('info', t('puppet.msg.armed'))
    window.clearTimeout(deleteTimer)
    deleteTimer = window.setTimeout(() => (deleteArmed.value = ''), 3000)
    return
  }
  deleteArmed.value = ''
  try {
    const data = await callTool<{ stations: Station[] }>('puppet', 'stations_delete', {
      id: station.id,
    })
    stations.value = data.stations
    if (originId.value === station.id) originId.value = data.stations[0]?.id ?? ''
    if (destId.value === station.id) {
      destId.value = data.stations.find((item) => item.id !== originId.value)?.id ?? ''
    }
    notify('success', t('puppet.msg.deleted'))
  } catch (error) {
    notifyError(error)
  }
}

// 导入完成：整表替换，并提示新增 / 更新 / 重复 / 跳过的条数。
function onImported(list: Station[], result: ImportResult) {
  stations.value = list
  importOpen.value = false
  notify(
    'success',
    t('puppet.import.result', {
      added: result.added,
      updated: result.updated,
      duplicated: result.duplicated,
      skipped: result.skipped.length,
    }),
  )
  if (!originId.value) originId.value = list[0]?.id ?? ''
  if (!destId.value) destId.value = list.find((item) => item.id !== originId.value)?.id ?? ''
}

// ------------------------------ 执行 ------------------------------ #
// 点「执行」只整理参数并弹确认框，真正发送在 confirmRun。
function requestExecute() {
  if (!displayCommands.value.length) {
    notify('info', t('puppet.empty.commands'))
    return
  }
  if (!allowExecute.value) {
    notify('error', t('puppet.run.disabled'))
    return
  }
  // 恢复态执行台账里的阶段，否则用当前页签。
  const commandList = displayCommands.value.map((item) => item.text)
  const runPhase = restored.value ? restored.value.order.phase : phase.value
  // 恢复态优先用台账存的 meta（它记着原始站点与假人名）。
  let meta: RunMeta
  if (restored.value) {
    const source = restored.value.order.meta
    meta = {
      origin: source?.origin ?? restored.value.order.origin,
      dest: source?.dest ?? restored.value.order.dest,
      boxes: source?.boxes ?? restored.value.order.boxes,
      bots: source?.bots ?? restored.value.order.bots,
      names: source?.names ?? [],
      spawnStation:
        source?.spawnStation ?? restored.value.order.spawnStation ?? null,
    }
  } else {
    meta = {
      origin: originId.value,
      dest: destId.value,
      boxes: plan.value?.boxes ?? 0,
      bots: plan.value?.bots ?? 0,
      names: plan.value?.names.slice() ?? [],
      spawnStation: spawnStationOf(plan.value?.spawnStation),
    }
  }
  // 每批人数：计划里有就用计划的，台账恢复的用设置里的默认值（0 表示不分批）
  const perBatch = Number(
    plan.value?.botsPerBatch ?? getSettings(props.tool.id).botsPerBatch ?? 0,
  )
  const batchSize = Number.isFinite(perBatch) && perBatch > 0 ? Math.trunc(perBatch) : 0
  pending.value = { commands: commandList, phase: runPhase, meta, batchSize }
  confirmOpen.value = true
}

// 中断后补清理：把已生成的假人按名字逐个 kill，走同一条确认流程。
function requestCleanup() {
  if (!cleanupNames.value.length) return
  pending.value = {
    commands: cleanupNames.value.map((name) => `/player ${name} kill`),
    phase: 'kill',
    batchSize: 0,
    meta: {
      origin: originId.value,
      dest: destId.value,
      boxes: plan.value?.boxes ?? 0,
      bots: cleanupNames.value.length,
      names: cleanupNames.value.slice(),
      spawnStation:
        run.value?.meta?.spawnStation ??
        spawnStationOf(plan.value?.spawnStation) ??
        restored.value?.order.meta?.spawnStation ??
        restored.value?.order.spawnStation ??
        null,
    },
  }
  confirmOpen.value = true
}

// 确认后真正 run_start：先用本地快照切到「执行中」，再开始轮询。
async function confirmRun() {
  if (!pending.value) return
  confirmOpen.value = false
  try {
    const data = await callTool<{ runId: string; total: number }>('puppet', 'run_start', {
      commands: pending.value.commands,
      phase: pending.value.phase,
      meta: pending.value.meta,
      batchSize: pending.value.batchSize,
    })
    runId.value = data.runId
    // 本地先占位，第一轮 run_status 回来就整体替换成后端快照。
    run.value = {
      id: data.runId,
      state: 'running',
      phase: pending.value.phase,
      total: data.total,
      sent: 0,
      index: 0,
      current: '',
      logs: [],
      startedAt: Date.now() / 1000,
      finishedAt: null,
      elapsed: 0,
      error: '',
      meta: pending.value.meta,
      waiting: false,
      batch: 0,
      batches: pending.value.batchSize
        ? Math.ceil(data.total / pending.value.batchSize)
        : 0,
    }
    logPinned.value = true
    bottomTab.value = 'run'
    void stickLogsToBottom(true)
    notify('success', t('puppet.run.started'))
    startPolling()
  } catch (error) {
    notifyError(error)
  }
}

// 批间确认：放行下一批；后端对不在等待的运单返回 continued=false，不算错。
async function continueRun() {
  if (!runId.value || continueBusy.value) return
  continueBusy.value = true
  try {
    await callTool('puppet', 'run_continue', { runId: runId.value })
  } catch (error) {
    notifyError(error)
  } finally {
    continueBusy.value = false
  }
}

// 轮询间隔 300ms：够跟上日志，也不至于给桥接层太大压力。
function startPolling() {
  stopPolling()
  polling.value = window.setInterval(pollStatus, 300)
}

// 运行结束、出错、组件卸载时都要停轮询。
function stopPolling() {
  if (polling.value !== null) {
    window.clearInterval(polling.value)
    polling.value = null
  }
}

// 拉一次状态；结束时停轮询、刷新台账，并按结果给提示。
async function pollStatus() {
  if (!runId.value) return
  try {
    const data = await callTool<RunState>('puppet', 'run_status', { runId: runId.value })
    if (run.value) run.value.sent = data.sent
    // 用后端快照整体覆盖本地状态（日志只回最近 40 行）。
    run.value = { ...data }
    void stickLogsToBottom()
    // 结束态：中断且已生成过假人时记录名字供补 kill；完成 / 出错各给一条提示。
    if (data.state !== 'running') {
      stopPolling()
      await refreshHistory()
      if (data.state === 'aborted') {
        notify('info', t('puppet.run.abortedMsg', { n: data.sent }))
        if (data.phase === 'spawn' && data.sent > 0) {
          cleanupNames.value = (data.meta?.names ?? []).slice(0, data.sent)
        }
      } else if (data.state === 'done') {
        notify('success', t('puppet.run.finished'))
      } else {
        notify('error', data.error || t('puppet.run.state.error'))
      }
    }
  } catch (error) {
    stopPolling()
    notifyError(error)
  }
}

// 中断：只发请求，界面状态等下一轮 run_status 自己收敛。
async function stopRun() {
  if (!runId.value) return
  try {
    await callTool('puppet', 'run_stop', { runId: runId.value })
  } catch (error) {
    notifyError(error)
  }
}

// 切换到别的工具再回来时，执行线程还在跑（可能停在批间确认），把界面接回去
async function resumeRunning() {
  try {
    // 不传 runId 时后端返回最近一次执行，用来判断是否需要接续。
    const data = await callTool<RunState>('puppet', 'run_status', {})
    // 已经结束的运单不接管，避免把旧日志灌进面板。
    if (!data || data.state !== 'running') return
    run.value = data
    runId.value = data.id
    bottomTab.value = 'run'
    logPinned.value = true
    startPolling()
  } catch {
    // 没有可接续的执行记录
  }
}

// ------------------------------ 其它 ------------------------------ #
// 环境自检：检查自动输入是否可用（剪贴板、窗口焦点等）。
async function diagnose() {
  try {
    const data = await callTool<{ supported: boolean; checks: DiagnoseCheck[] }>(
      'puppet',
      'diagnose',
    )
    diagChecks.value = data.checks
    diagOpen.value = true
  } catch (error) {
    notifyError(error)
  }
}

// 清空台账：后端落盘空列表，前端同时清掉列表。
async function clearHistory() {
  try {
    await callTool('puppet', 'history_clear')
    orders.value = []
    notify('success', t('puppet.msg.historyCleared'))
  } catch (error) {
    notifyError(error)
  }
}

// ------------------------------ 生命周期 ------------------------------ #
// 挂载顺序：设置 → 站点 → 草稿 → 台账 → 尝试接回正在执行的运单。
onMounted(async () => {
  try {
    await loadSettings(props.tool.id)
    syncAllowExecute()
  } catch (error) {
    notifyError(error)
  }
  try {
    // 站点必须先于草稿：草稿里的 id 要拿站点表校验。
    await refreshStations()
    await loadDraft()
    await refreshHistory()
    // 切走再回来时执行线程可能还在跑，这里把界面接回去。
    await resumeRunning()
  } catch (error) {
    notifyError(error)
  }
})

// 卸载时停轮询、清删除定时器，并把最新草稿立刻落盘。
onUnmounted(() => {
  stopPolling()
  window.clearTimeout(deleteTimer)
  if (draftReady.value) void flushDraft()
})
</script>

<template>
  <!-- 区块：工作台（左右两栏） -->
  <div class="workbench">
    <!-- 区块：左栏（订单 + 站点表） -->
    <div class="left-col">
      <!-- 区块：订单（选站点、填盒数、选操作） -->
      <section class="panel order-panel">
        <div class="panel-head">{{ t('puppet.panel.order') }}</div>
        <div class="panel-body order-body">
          <!-- 区块：始发站（自绘选择器） -->
          <div class="field">
            <label class="field-label">{{ t('puppet.field.origin') }}</label>
            <StationPicker v-model="originId" :stations="stations" />
          </div>

          <!-- 区块：目的站（自绘选择器） -->
          <div class="field">
            <label class="field-label">{{ t('puppet.field.dest') }}</label>
            <StationPicker v-model="destId" :stations="stations" />
          </div>

          <!-- 区块：盒数与操作 -->
          <div class="field-row">
            <div class="field">
              <label class="field-label">
                {{ t('puppet.field.boxes') }}
                <span class="unit">{{ t('puppet.unit.box') }}</span>
              </label>
              <input v-model="boxes" class="input mono" type="number" min="1" step="1" />
            </div>
            <div class="field">
              <label class="field-label">{{ t('puppet.field.operation') }}</label>
              <select v-model="operation" class="input">
                <option value="spawn_at_origin">{{ t('puppet.op.spawn_at_origin') }}</option>
                <option value="spawn_at_dest">{{ t('puppet.op.spawn_at_dest') }}</option>
              </select>
            </div>
          </div>

          <!-- 区块：计划摘要（人数 / 批次 / 命令数 / 预估耗时） -->
          <div v-if="plan" class="summary">
            <span class="mono">
              {{
                t('puppet.summary', {
                  bots: plan.bots,
                  waves: plan.waves,
                  commands: plan.commands.length,
                })
              }}
            </span>
            <span class="muted mono">{{ t('puppet.summary.estimate', { seconds: plan.estimate.spawnSeconds }) }}</span>
          </div>

          <!-- 区块：生成计划 -->
          <button class="btn primary block" :disabled="busy || !stations.length" @click="generate">
            {{ t('puppet.action.generate') }}
          </button>
        </div>
      </section>

      <!-- 区块：站点表（分组筛选 + 搜索 + 列表 + 备注） -->
      <section class="panel stations-panel">
        <div class="panel-head">
          <span>{{ t('puppet.panel.stations') }} · {{ stations.length }}</span>
        </div>
        <!-- 区块：站点工具栏（导入 / 导出 / 新增） -->
        <div class="station-toolbar">
          <button class="btn sm" @click="importOpen = true">{{ t('puppet.action.import') }}</button>
          <button class="btn sm" :disabled="!stations.length" @click="exportStations">
            {{ t('puppet.action.exportStations') }}
          </button>
          <button class="btn sm primary" @click="openStation(null)">
            + {{ t('puppet.action.addStation') }}
          </button>
        </div>
        <!-- 区块：站点列表区 -->
        <div class="panel-body stations-body">
          <!-- 区块：分组筛选胶囊（全部 + 各组） -->
          <div class="station-filter">
            <button
              type="button"
              class="filter-chip"
              :class="{ active: stationGroupFilter === '*' }"
              @click="stationGroupFilter = '*'"
            >
              {{ t('puppet.filter.all') }}
            </button>
            <button
              v-for="group in stationGroups"
              :key="group || '-none-'"
              type="button"
              class="filter-chip"
              :class="{ active: stationGroupFilter === group }"
              @click="stationGroupFilter = group"
            >
              {{ group || t('puppet.station.noGroup') }}
            </button>
          </div>
          <!-- 区块：关键字搜索（匹配名称与前缀） -->
          <input v-model="search" class="input search" :placeholder="t('puppet.field.search')" />
          <!-- 区块：空状态（没有站点 / 没有匹配项） -->
          <div v-if="!stations.length" class="empty">{{ t('puppet.empty.stations') }}</div>
          <div v-else-if="!filteredStations.length" class="empty">
            {{ t('puppet.empty.filtered') }}
          </div>
          <!-- 区块：站点行 -->
          <div v-else class="station-list">
            <div
              v-for="station in filteredStations"
              :key="station.id"
              class="station-row"
              :class="{ active: station.id === originId || station.id === destId }"
              @mouseenter="hoveredStation = station.id"
              @mouseleave="hoveredStation = ''"
            >
              <!-- 区块：行主内容与悬停操作（编辑 / 删除） -->
              <div class="station-line">
                <div class="station-main">
                  <div class="station-name">
                    <!-- 分组 tag 胶囊（无分组时不显示） -->
                    <span v-if="station.group" class="group-tag">{{ station.group }}</span>
                    {{ station.name }}
                  </div>
                  <div class="station-meta">
                    <span class="badge dim">{{ t(`puppet.dim.${station.dimension}`) }}</span>
                    <span class="mono">{{ station.x }} {{ station.y }} {{ station.z }}</span>
                    <span class="mono muted">· {{ station.prefix }}</span>
                  </div>
                </div>
                <div class="station-actions">
                  <button class="btn ghost sm" @click="openStation(station)">✎</button>
                  <button
                    class="btn ghost sm"
                    :class="{ 'danger-text': deleteArmed === station.id }"
                    @click="deleteStation(station)"
                  >
                    {{ deleteArmed === station.id ? '✓' : '✕' }}
                  </button>
                </div>
              </div>
              <!-- 区块：悬停展开备注（最多两行） -->
              <div
                v-if="hoveredStation === station.id && station.note"
                class="station-note"
              >
                {{ station.note }}
              </div>
            </div>
          </div>
        </div>
      </section>
    </div>

    <!-- 区块：右栏（命令 + 执行 / 台账） -->
    <div class="right-col">
      <!-- 区块：命令面板（生成 / 清除两页签） -->
      <section class="panel commands-panel">
        <!-- 区块：页签与人数批次摘要 -->
        <div class="panel-head">
          <div class="tabs inline">
            <button class="tab" :class="{ active: phase === 'spawn' }" @click="phase = 'spawn'">
              {{ t('puppet.phase.spawn') }}
              <span v-if="plan" class="tab-count">{{ plan.commands.length }}</span>
            </button>
            <button class="tab" :class="{ active: phase === 'kill' }" @click="phase = 'kill'">
              {{ t('puppet.phase.kill') }}
              <span v-if="plan" class="tab-count">{{ plan.killCommands.length }}</span>
            </button>
          </div>
          <div class="head-actions">
            <span v-if="plan" class="badge">{{ plan.bots }} · {{ plan.waves }}</span>
          </div>
        </div>

        <!-- 区块：工具条（自检 / 复制 / 清空 / 导出 / 执行） -->
        <div class="toolbar">
          <button class="btn sm" @click="diagnose">{{ t('puppet.action.diagnose') }}</button>
          <button class="btn sm" :disabled="!displayCommands.length" @click="copyAll">
            {{ t('puppet.action.copy') }}
          </button>
          <button class="btn sm" :disabled="!displayCommands.length" @click="clearCommands">
            {{ t('puppet.action.clearCommands') }}
          </button>
          <button class="btn sm" :disabled="!displayCommands.length" @click="exportAll">
            {{ t('puppet.action.export') }}
          </button>
          <button
            class="btn sm execute"
            :class="allowExecute ? 'primary' : ''"
            :disabled="!displayCommands.length || running"
            @click="requestExecute"
          >
            {{ t('puppet.action.execute') }}
          </button>
        </div>

        <!-- 区块：恢复条（当前显示的是从台账恢复的命令） -->
        <div v-if="restored" class="restored-bar">
          <span class="restored-text">{{ restoredLabel }}</span>
          <button class="btn sm" @click="clearRestored">{{ t('puppet.action.backToOrder') }}</button>
        </div>

        <!-- 区块：命令列表（序号 / 阶段 / 假人名 / 命令文本） -->
        <div class="panel-body commands-body">
          <div v-if="!displayCommands.length" class="empty">{{ t('puppet.empty.commands') }}</div>
          <div v-else class="command-list">
            <div v-for="item in displayCommands" :key="item.index" class="command-row">
              <span class="command-index mono">{{ item.index }}</span>
              <span class="badge dim">{{ t(`puppet.phase.${item.phase}`) }}</span>
              <span class="command-name mono">{{ item.name || '—' }}</span>
              <span class="command-text mono" :title="item.text">{{ item.text }}</span>
            </div>
          </div>
        </div>
      </section>

      <!-- 区块：下方面板（执行进度与台账切换） -->
      <section class="panel bottom-panel">
        <div class="panel-head">
          <div class="tabs inline">
            <button class="tab" :class="{ active: bottomTab === 'run' }" @click="bottomTab = 'run'">
              {{ t('puppet.panel.run') }}
            </button>
            <button class="tab" :class="{ active: bottomTab === 'ledger' }" @click="bottomTab = 'ledger'">
              {{ t('puppet.panel.history') }}
            </button>
          </div>
          <!-- 区块：台账头（清空按钮） -->
          <div v-if="bottomTab === 'ledger'" class="head-actions">
            <button class="btn sm" :disabled="!orders.length" @click="clearHistory">
              {{ t('puppet.action.clearHistory') }}
            </button>
          </div>
          <!-- 区块：执行头（状态徽标 + 中断按钮） -->
          <div v-else class="head-actions">
            <span class="badge" :class="{ warn: running }">{{ runStateLabel }}</span>
            <button v-if="running" class="btn sm danger" @click="stopRun">
              {{ t('puppet.action.stop') }}
            </button>
          </div>
        </div>

        <!-- 区块：执行进度（进度条 / 当前命令 / 批间确认 / 补清理 / 日志） -->
        <div v-if="bottomTab === 'run'" class="panel-body run-body">
          <div v-if="!run" class="empty">{{ t('puppet.run.empty') }}</div>
          <template v-else>
            <div class="run-line">
              <span class="mono">{{ t('puppet.run.progress', { sent: run.sent, total: run.total }) }}</span>
              <span class="mono muted">{{ run.elapsed }}s</span>
            </div>
            <!-- 区块：进度条（已发送 / 总数） -->
            <div class="progress"><div class="progress-bar" :style="{ width: `${runPercent}%` }" /></div>
            <!-- 区块：当前正在发送的命令 -->
            <div v-if="run.current" class="current mono" :title="run.current">
              {{ t('puppet.run.current') }}: {{ run.current }}
            </div>
            <!-- 区块：批间确认条（等用户放行下一批） -->
            <div v-if="waitingContinue" class="wait-bar">
              <div class="wait-text">
                <span class="mono">
                  {{
                    t('puppet.run.waitBatch', {
                      batch: run.batch ?? 0,
                      batches: run.batches ?? 0,
                      sent: run.sent,
                      total: run.total,
                    })
                  }}
                </span>
                <span class="wait-hint">{{ t('puppet.run.waitHint') }}</span>
              </div>
              <button class="btn sm primary" :disabled="continueBusy" @click="continueRun">
                {{ t('puppet.action.continueBatch') }}
              </button>
            </div>
            <!-- 区块：中断后的补清理入口 -->
            <div v-if="cleanupNames.length && !running" class="cleanup">
              <span>{{ t('puppet.run.cleanupHint', { n: cleanupNames.length }) }}</span>
              <button class="btn sm" @click="requestCleanup">{{ t('puppet.action.cleanup') }}</button>
            </div>
            <!-- 区块：日志（自动贴底，往上翻后暂停跟随） -->
            <div ref="logBox" class="run-logs mono" @scroll="onLogScroll">
              <div v-for="(line, index) in run.logs" :key="index" class="log-line">{{ line }}</div>
            </div>
          </template>
        </div>

        <!-- 区块：台账（最多 200 条，点击行可恢复该单命令） -->
        <div v-else class="panel-body ledger-body">
          <div v-if="!orders.length" class="empty">{{ t('puppet.empty.history') }}</div>
          <!-- 区块：台账表头 -->
          <table v-else class="ledger">
            <thead>
              <tr>
                <th>{{ t('puppet.history.no') }}</th>
                <th>{{ t('puppet.history.time') }}</th>
                <th>{{ t('puppet.history.route') }}</th>
                <th>{{ t('puppet.history.spawn') }}</th>
                <th>{{ t('puppet.history.boxes') }}</th>
                <th>{{ t('puppet.history.bots') }}</th>
                <th>{{ t('puppet.history.phase') }}</th>
                <th>{{ t('puppet.history.state') }}</th>
                <th>{{ t('puppet.history.sent') }}</th>
              </tr>
            </thead>
            <tbody>
              <!-- 区块：台账行（有保存命令的行才可点击恢复） -->
              <tr
                v-for="order in orders"
                :key="order.no"
                class="ledger-row"
                :class="{ clickable: order.commands && order.commands.length }"
                :title="t('puppet.history.clickHint')"
                @click="restoreOrder(order)"
              >
                <td class="mono">{{ order.no }}</td>
                <td class="mono">{{ order.date }} {{ order.at }}</td>
                <td>{{ stationLabelById(order.origin) }} → {{ stationLabelById(order.dest) }}</td>
                <td class="spawn-cell" :title="spawnLabel(order)">{{ spawnLabel(order) }}</td>
                <td class="mono">{{ order.boxes }}</td>
                <td class="mono">{{ order.bots }}</td>
                <td>{{ t(`puppet.phase.${order.phase}`) }}</td>
                <td>
                  <span class="badge" :class="{ warn: order.state === 'aborted' }">
                    {{ t(`puppet.run.state.${order.state}`) }}
                  </span>
                </td>
                <td class="mono">{{ order.sent }}/{{ order.total }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </div>

    <!-- 区块：新增 / 编辑站点弹窗 -->
    <StationDialog
      :open="stationDialogOpen"
      :station="editing"
      @close="stationDialogOpen = false"
      @save="saveStation"
    />
    <!-- 区块：导入弹窗 -->
    <ImportDialog :open="importOpen" @close="importOpen = false" @done="onImported" />

    <!-- 区块：执行确认弹窗（生成与补清理共用） -->
    <div v-if="confirmOpen" class="overlay" @click.self="confirmOpen = false">
      <div class="dialog">
        <header class="dialog-head">
          <span>{{ t('puppet.run.confirmTitle') }}</span>
          <button class="btn ghost sm" @click="confirmOpen = false">✕</button>
        </header>
        <div class="dialog-body">
          <p class="confirm-text">
            {{ t('puppet.run.confirmBody', { n: pending?.commands.length ?? 0 }) }}
          </p>
          <div v-if="!allowExecute" class="warn-text">{{ t('puppet.run.disabled') }}</div>
        </div>
        <footer class="dialog-foot">
          <button class="btn" @click="confirmOpen = false">{{ t('puppet.action.cancel') }}</button>
          <button class="btn primary" :disabled="!allowExecute" @click="confirmRun">
            {{ t('puppet.action.execute') }}
          </button>
        </footer>
      </div>
    </div>

    <!-- 区块：环境自检弹窗 -->
    <div v-if="diagOpen" class="overlay" @click.self="diagOpen = false">
      <div class="dialog wide">
        <header class="dialog-head">
          <span>{{ t('puppet.diag.title') }}</span>
          <button class="btn ghost sm" @click="diagOpen = false">✕</button>
        </header>
        <div class="dialog-body">
          <div v-for="check in diagChecks" :key="check.id" class="diag-row">
            <span
              class="badge"
              :class="{ warn: check.ok === false, brand: check.ok === true }"
            >
              {{ check.ok === null ? t('puppet.diag.unknown') : check.ok ? t('puppet.diag.ok') : t('puppet.diag.fail') }}
            </span>
            <span class="diag-id mono">{{ check.id }}</span>
            <span class="diag-detail">{{ check.detail }}</span>
          </div>
          <p class="hint">{{ t('puppet.diag.hint') }}</p>
        </div>
        <footer class="dialog-foot">
          <button class="btn" @click="diagOpen = false">{{ t('puppet.action.confirm') }}</button>
        </footer>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* 区块：两栏布局（左 360px 固定，右自适应） */
.workbench {
  height: 100%;
  width: 100%;
  display: grid;
  grid-template-columns: 360px minmax(0, 1fr);
  gap: 14px;
  min-height: 0;
  min-width: 0;
}

/* 区块：两栏容器（面板纵向堆叠） */
.left-col,
.right-col {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-height: 0;
  min-width: 0;
}

.right-col {
  overflow-x: hidden;
}

.left-col {
  overflow-y: auto;
  overflow-x: hidden;
}

/* 区块：左栏面板高度分配 */
.stations-panel {
  flex: 1 0 240px;
  min-height: 240px;
}

/* 区块：订单面板（overflow visible 让选择器下拉不被裁掉） */
.order-panel {
  flex: 0 0 auto;
  position: relative;
  z-index: 5;
  overflow: visible;
}

/* 区块：订单表单体（同样允许下拉溢出） */
.order-body {
  overflow: visible;
}

/* 区块：命令面板与下方面板 */
.commands-panel {
  flex: 1;
  min-height: 200px;
}

.bottom-panel {
  flex: 0 0 300px;
  min-height: 260px;
}

/* 区块：面板头右侧动作 */
.head-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

/* 区块：命令工具条 */
.toolbar {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  padding: 8px 14px;
  border-bottom: 1px solid var(--line);
}

/* 区块：执行按钮与其它按钮留一点间距 */
.toolbar .execute {
  margin-left: 4px;
}

/* 区块：恢复条（从台账恢复命令时的提示） */
.restored-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 14px;
  border-bottom: 1px solid var(--line);
  background: var(--brand-soft);
  color: var(--brand);
  font-size: 12px;
}

/* 区块：恢复条文案（单行省略） */
.restored-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 区块：台账可点击行 */
.ledger-row.clickable {
  cursor: pointer;
}

/* 区块：面板头换行（窄屏时页签与按钮分行） */
.commands-panel .panel-head,
.bottom-panel .panel-head {
  flex-wrap: wrap;
  row-gap: 6px;
}

/* 区块：站点列表体 */
.stations-body {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

/* 区块：搜索框 */
.search {
  height: 30px;
  font-size: 12px;
}

/* 区块：分组筛选胶囊（自动换行） */
.station-filter {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

/* 区块：筛选胶囊（默认透明，选中高亮） */
.filter-chip {
  padding: 2px 8px;
  border: 1px solid transparent;
  border-radius: 999px;
  background: transparent;
  color: var(--muted);
  font-size: 11px;
  cursor: pointer;
}

.filter-chip:hover {
  color: var(--text);
}

.filter-chip.active {
  border-color: var(--brand-dim);
  background: var(--brand-soft);
  color: var(--brand);
}

/* 区块：站点列表 */
.station-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

/* 区块：站点行（默认透明边框，选中时描边） */
.station-row {
  padding: 6px 8px;
  border: 1px solid transparent;
  border-radius: 8px;
}

/* 区块：站点行主内容 */
.station-line {
  display: flex;
  align-items: center;
  gap: 8px;
}

.station-row:hover {
  background: var(--surface-2);
}

/* 区块：站点行选中态（作为始发或目的） */
.station-row.active {
  border-color: var(--brand-dim);
  background: var(--select-bg);
}

/* 区块：站点工具栏 */
.station-toolbar {
  display: flex;
  gap: 6px;
  padding: 8px 14px;
  border-bottom: 1px solid var(--line);
}

.station-toolbar .btn {
  flex: 1;
  min-width: 0;
  padding: 0 8px;
}

/* 区块：站点名称与元信息 */
.station-main {
  flex: 1;
  min-width: 0;
}

/* 区块：站点名（单行省略） */
.station-name {
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 区块：分组 tag 胶囊 */
.group-tag {
  display: inline-block;
  margin-right: 6px;
  padding: 1px 6px;
  border-radius: 999px;
  background: var(--brand-soft);
  color: var(--brand);
  font-size: 10px;
  vertical-align: 1px;
}

/* 区块：备注（悬停展开，最多两行） */
.station-note {
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  overflow: hidden;
  margin-top: 6px;
  padding: 6px 8px;
  border-radius: 6px;
  background: var(--brand-soft);
  color: var(--text);
  font-size: 11px;
  line-height: 1.6;
  overflow-wrap: anywhere;
}

/* 区块：维度 / 坐标 / 前缀一行 */
.station-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 2px;
  font-size: 10px;
  color: var(--muted);
}

/* 区块：行操作按钮（默认透明，行悬停才显示） */
.station-actions {
  display: flex;
  gap: 2px;
  opacity: 0;
  transition: opacity 0.15s ease;
}

.station-row:hover .station-actions {
  opacity: 1;
}

/* 区块：删除二次确认态的颜色 */
.danger-text {
  color: var(--danger);
}

/* 区块：订单表单纵向间距 */
.order-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* 区块：计划摘要（虚线框） */
.summary {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px 10px;
  border: 1px dashed var(--line-strong);
  border-radius: 8px;
  font-size: 12px;
}

/* 区块：内联页签 */
.tabs.inline {
  display: flex;
  gap: 2px;
  margin: 0;
}

/* 区块：页签上的命令条数 */
.tab-count {
  margin-left: 6px;
  color: var(--muted);
  font-size: 10px;
}

/* 区块：命令列表区（去掉内边距，让行贴边） */
.commands-body {
  padding: 0;
}

/* 区块：命令列表容器 */
.command-list {
  display: flex;
  flex-direction: column;
}

/* 区块：单条命令行（四列网格：序号 / 阶段 / 名字 / 文本） */
.command-row {
  display: grid;
  grid-template-columns: 34px 46px 140px minmax(0, 1fr);
  align-items: center;
  gap: 8px;
  padding: 6px 14px;
  border-bottom: 1px solid var(--line);
  font-size: 11px;
}

.command-row:hover {
  background: var(--surface-2);
}

/* 区块：序号、名字与命令文本（弱化颜色，单行省略） */
.command-index {
  color: var(--muted);
}

.command-name {
  color: var(--brand);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.command-text {
  color: var(--muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 区块：执行进度面板 */
.run-body {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

/* 区块：进度文字行 */
.run-line {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
}

/* 区块：进度条 */
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

/* 区块：当前命令一行 */
.current {
  font-size: 11px;
  color: var(--muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 区块：补清理提示 */
.cleanup {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 10px;
  border: 1px solid var(--line-strong);
  border-radius: 8px;
  font-size: 12px;
}

/* 区块：批间确认条 */
.wait-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 10px;
  border: 1px solid var(--brand-dim);
  border-radius: 8px;
  background: var(--brand-soft);
  color: var(--brand);
}

/* 区块：确认条文字与提示 */
.wait-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  font-size: 12px;
}

.wait-hint {
  color: var(--muted);
  font-size: 11px;
}

/* 区块：日志区（可滚动，滚动条占位保持宽度稳定） */
.run-logs {
  flex: 1;
  min-height: 90px;
  overflow: auto;
  padding: 8px 10px;
  border-radius: 8px;
  background: var(--bg);
  font-size: 10px;
  line-height: 1.6;
  scrollbar-gutter: stable;
}

/* 区块：单行日志（保留换行与缩进） */
.log-line {
  color: var(--muted);
  white-space: pre-wrap;
  word-break: break-all;
}

/* 区块：台账容器 */
.ledger-body {
  padding: 0;
}

/* 区块：台账表格（表头粘顶） */
.ledger {
  width: 100%;
  border-collapse: collapse;
  font-size: 11px;
}

.ledger th {
  position: sticky;
  top: 0;
  padding: 8px 10px;
  border-bottom: 1px solid var(--line);
  background: var(--surface);
  color: var(--muted);
  font-weight: 400;
  text-align: left;
  white-space: nowrap;
}

.ledger td {
  padding: 7px 10px;
  border-bottom: 1px solid var(--line);
  white-space: nowrap;
}

/* 区块：生成于列（超宽省略） */
.ledger td.spawn-cell {
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--muted);
}

.ledger tbody tr:hover {
  background: var(--surface-2);
}

/* 区块：弹窗遮罩 */
.overlay {
  position: fixed;
  inset: 0;
  z-index: 55;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--scrim);
  backdrop-filter: blur(2px);
}

/* 区块：弹窗容器（确认框与自检框共用） */
.dialog {
  width: 480px;
  max-width: 92vw;
  display: flex;
  flex-direction: column;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
}

/* 区块：自检弹窗（更宽） */
.dialog.wide {
  width: 640px;
}

/* 区块：弹窗头尾共用排版 */
.dialog-head,
.dialog-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--line);
}

/* 区块：弹窗底栏（按钮靠右） */
.dialog-foot {
  border-bottom: none;
  border-top: 1px solid var(--line);
  justify-content: flex-end;
  gap: 8px;
}

/* 区块：弹窗内容 */
.dialog-body {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 16px;
}

/* 区块：确认文案与未开执行开关的警告 */
.confirm-text {
  margin: 0;
  font-size: 12px;
  line-height: 1.8;
}

.warn-text {
  color: var(--warn);
  font-size: 12px;
}

/* 区块：自检项（状态徽标 / 检查 id / 说明） */
.diag-row {
  display: grid;
  grid-template-columns: 60px 80px minmax(0, 1fr);
  align-items: center;
  gap: 8px;
  font-size: 12px;
}

/* 区块：自检项 id（弱化颜色） */
.diag-id {
  color: var(--muted);
}

/* 区块：弹窗底部提示 */
.hint {
  margin: 4px 0 0;
  color: var(--muted);
  font-size: 11px;
  line-height: 1.7;
}
</style>
