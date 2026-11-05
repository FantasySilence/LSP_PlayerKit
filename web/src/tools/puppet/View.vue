<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'

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
  Plan,
  PlanCommand,
  RunMeta,
  RunState,
  SpawnStation,
  Station,
} from './types'

const props = defineProps<{ tool: ToolDef }>()

const DIMENSIONS = ['overworld', 'the_nether', 'the_end']

const stations = ref<Station[]>([])
const orders = ref<Order[]>([])
const originId = ref('')
const destId = ref('')
const boxes = ref<number | string>(250)
const operation = ref<'spawn_at_origin' | 'spawn_at_dest'>('spawn_at_origin')
const plan = ref<Plan | null>(null)
const phase = ref<'spawn' | 'kill'>('spawn')
const busy = ref(false)
const search = ref('')
const stationGroupFilter = ref('*')
const allowExecute = ref(false)

const stationDialogOpen = ref(false)
const editing = ref<Station | null>(null)
const importOpen = ref(false)
const deleteArmed = ref('')
let deleteTimer = 0

const run = ref<RunState | null>(null)
const runId = ref('')
const polling = ref<number | null>(null)
const cleanupNames = ref<string[]>([])
const bottomTab = ref<'run' | 'ledger'>('run')

const restored = ref<{ order: Order; commands: PlanCommand[] } | null>(null)

const hoveredStation = ref('')

const pending = ref<{ commands: string[]; phase: 'spawn' | 'kill'; meta: RunMeta } | null>(null)
const confirmOpen = ref(false)
const diagOpen = ref(false)
const diagChecks = ref<DiagnoseCheck[]>([])

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

const stationGroups = computed(() => {
  const result: string[] = []
  for (const station of stations.value) {
    const group = station.group ?? ''
    if (!result.includes(group)) result.push(group)
  }
  return result
})

watch(stations, () => {
  if (
    stationGroupFilter.value !== '*' &&
    !stationGroups.value.includes(stationGroupFilter.value)
  ) {
    stationGroupFilter.value = '*'
  }
})

const activeCommands = computed<PlanCommand[]>(() => {
  if (!plan.value) return []
  return phase.value === 'spawn' ? plan.value.commands : plan.value.killCommands
})

const displayCommands = computed<PlanCommand[]>(() =>
  restored.value ? restored.value.commands : activeCommands.value,
)

const restoredLabel = computed(() => {
  if (!restored.value) return ''
  return t('puppet.history.restored', {
    no: restored.value.order.no,
    phase: t(`puppet.phase.${restored.value.order.phase}`),
    n: restored.value.commands.length,
  })
})

const running = computed(() => run.value?.state === 'running')
const runStateLabel = computed(() => t(`puppet.run.state.${run.value?.state ?? 'idle'}`))
const runPercent = computed(() => {
  const total = run.value?.total ?? 0
  return total ? Math.min(100, Math.round(((run.value?.sent ?? 0) / total) * 100)) : 0
})

function stationLabel(station: Station): string {
  return station.group ? `${station.group} · ${station.name}` : station.name
}

function stationLabelById(id: string): string {
  const station = stations.value.find((item) => item.id === id)
  return station ? stationLabel(station) : id
}

async function refreshStations() {
  const data = await callTool<{ stations: Station[] }>('puppet', 'stations_list')
  stations.value = data.stations
  const ids = new Set(stations.value.map((station) => station.id))
  if (!ids.has(originId.value)) originId.value = stations.value[0]?.id ?? ''
  if (!ids.has(destId.value)) {
    destId.value = stations.value.find((station) => station.id !== originId.value)?.id ?? ''
  }
}

async function refreshHistory() {
  const data = await callTool<{ orders: Order[] }>('puppet', 'history_list')
  orders.value = data.orders.slice().reverse()
}

function syncAllowExecute() {
  allowExecute.value = Boolean(getSettings(props.tool.id).allowExecute)
}

watch(
  () => revision[props.tool.id],
  () => syncAllowExecute(),
)

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
    phase.value = 'spawn'
    cleanupNames.value = []
    restored.value = null
  } catch (error) {
    notifyError(error)
  } finally {
    busy.value = false
  }
}

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

function restoreOrder(order: Order) {
  const list = order.commands ?? []
  if (!list.length) {
    notify('info', t('puppet.msg.noCommandsSaved'))
    return
  }
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

function clearRestored() {
  restored.value = null
}

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

function clearCommands() {
  plan.value = null
  restored.value = null
  cleanupNames.value = []
  notify('success', t('puppet.msg.commandsCleared'))
}

function spawnLabel(order: Order): string {
  const station = order.spawnStation ?? order.meta?.spawnStation
  if (!station?.name) return '—'
  const label = station.group ? `${station.group} · ${station.name}` : station.name
  const dimension = station.dimension ? t(`puppet.dim.${station.dimension}`) : ''
  return dimension ? `${label} · ${dimension}` : label
}

// ------------------------------ 站点 ------------------------------ #
function openStation(station: Station | null) {
  editing.value = station
  stationDialogOpen.value = true
}

async function saveStation(station: Station) {
  try {
    const data = await callTool<{ stations: Station[] }>('puppet', 'stations_save', { station })
    stations.value = data.stations
    stationDialogOpen.value = false
    notify('success', t('puppet.action.save'))
    if (!originId.value) originId.value = data.stations[0]?.id ?? ''
    if (!destId.value) {
      destId.value = data.stations.find((item) => item.id !== originId.value)?.id ?? ''
    }
  } catch (error) {
    notifyError(error)
  }
}

async function deleteStation(station: Station) {
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
function requestExecute() {
  if (!displayCommands.value.length) {
    notify('info', t('puppet.empty.commands'))
    return
  }
  if (!allowExecute.value) {
    notify('error', t('puppet.run.disabled'))
    return
  }
  const commandList = displayCommands.value.map((item) => item.text)
  const runPhase = restored.value ? restored.value.order.phase : phase.value
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
  pending.value = { commands: commandList, phase: runPhase, meta }
  confirmOpen.value = true
}

function requestCleanup() {
  if (!cleanupNames.value.length) return
  pending.value = {
    commands: cleanupNames.value.map((name) => `/player ${name} kill`),
    phase: 'kill',
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

async function confirmRun() {
  if (!pending.value) return
  confirmOpen.value = false
  try {
    const data = await callTool<{ runId: string; total: number }>('puppet', 'run_start', {
      commands: pending.value.commands,
      phase: pending.value.phase,
      meta: pending.value.meta,
    })
    runId.value = data.runId
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
    }
    bottomTab.value = 'run'
    notify('success', t('puppet.run.started'))
    startPolling()
  } catch (error) {
    notifyError(error)
  }
}

function startPolling() {
  stopPolling()
  polling.value = window.setInterval(pollStatus, 300)
}

function stopPolling() {
  if (polling.value !== null) {
    window.clearInterval(polling.value)
    polling.value = null
  }
}

async function pollStatus() {
  if (!runId.value) return
  try {
    const data = await callTool<RunState>('puppet', 'run_status', { runId: runId.value })
    if (run.value) run.value.sent = data.sent
    run.value = { ...data }
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

async function stopRun() {
  if (!runId.value) return
  try {
    await callTool('puppet', 'run_stop', { runId: runId.value })
  } catch (error) {
    notifyError(error)
  }
}

// ------------------------------ 其它 ------------------------------ #
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

async function clearHistory() {
  try {
    await callTool('puppet', 'history_clear')
    orders.value = []
    notify('success', t('puppet.msg.historyCleared'))
  } catch (error) {
    notifyError(error)
  }
}

onMounted(async () => {
  try {
    await loadSettings(props.tool.id)
    syncAllowExecute()
  } catch (error) {
    notifyError(error)
  }
  try {
    await refreshStations()
    await refreshHistory()
  } catch (error) {
    notifyError(error)
  }
})

onUnmounted(() => {
  stopPolling()
  window.clearTimeout(deleteTimer)
})
</script>

<template>
  <div class="workbench">
    <div class="left-col">
      <section class="panel order-panel">
        <div class="panel-head">{{ t('puppet.panel.order') }}</div>
        <div class="panel-body order-body">
          <div class="field">
            <label class="field-label">{{ t('puppet.field.origin') }}</label>
            <StationPicker v-model="originId" :stations="stations" />
          </div>

          <div class="field">
            <label class="field-label">{{ t('puppet.field.dest') }}</label>
            <StationPicker v-model="destId" :stations="stations" />
          </div>

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

          <button class="btn primary block" :disabled="busy || !stations.length" @click="generate">
            {{ t('puppet.action.generate') }}
          </button>
        </div>
      </section>

      <section class="panel stations-panel">
        <div class="panel-head">
          <span>{{ t('puppet.panel.stations') }} · {{ stations.length }}</span>
        </div>
        <div class="station-toolbar">
          <button class="btn sm" @click="importOpen = true">{{ t('puppet.action.import') }}</button>
          <button class="btn sm" :disabled="!stations.length" @click="exportStations">
            {{ t('puppet.action.exportStations') }}
          </button>
          <button class="btn sm primary" @click="openStation(null)">
            + {{ t('puppet.action.addStation') }}
          </button>
        </div>
        <div class="panel-body stations-body">
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
          <input v-model="search" class="input search" :placeholder="t('puppet.field.search')" />
          <div v-if="!stations.length" class="empty">{{ t('puppet.empty.stations') }}</div>
          <div v-else-if="!filteredStations.length" class="empty">
            {{ t('puppet.empty.filtered') }}
          </div>
          <div v-else class="station-list">
            <div
              v-for="station in filteredStations"
              :key="station.id"
              class="station-row"
              :class="{ active: station.id === originId || station.id === destId }"
              @mouseenter="hoveredStation = station.id"
              @mouseleave="hoveredStation = ''"
            >
              <div class="station-line">
                <div class="station-main">
                  <div class="station-name">
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

    <div class="right-col">
      <section class="panel commands-panel">
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

        <div v-if="restored" class="restored-bar">
          <span class="restored-text">{{ restoredLabel }}</span>
          <button class="btn sm" @click="clearRestored">{{ t('puppet.action.backToOrder') }}</button>
        </div>

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
          <div v-if="bottomTab === 'ledger'" class="head-actions">
            <button class="btn sm" :disabled="!orders.length" @click="clearHistory">
              {{ t('puppet.action.clearHistory') }}
            </button>
          </div>
          <div v-else class="head-actions">
            <span class="badge" :class="{ warn: running }">{{ runStateLabel }}</span>
            <button v-if="running" class="btn sm danger" @click="stopRun">
              {{ t('puppet.action.stop') }}
            </button>
          </div>
        </div>

        <div v-if="bottomTab === 'run'" class="panel-body run-body">
          <div v-if="!run" class="empty">{{ t('puppet.run.empty') }}</div>
          <template v-else>
            <div class="run-line">
              <span class="mono">{{ t('puppet.run.progress', { sent: run.sent, total: run.total }) }}</span>
              <span class="mono muted">{{ run.elapsed }}s</span>
            </div>
            <div class="progress"><div class="progress-bar" :style="{ width: `${runPercent}%` }" /></div>
            <div v-if="run.current" class="current mono" :title="run.current">
              {{ t('puppet.run.current') }}: {{ run.current }}
            </div>
            <div v-if="cleanupNames.length && !running" class="cleanup">
              <span>{{ t('puppet.run.cleanupHint', { n: cleanupNames.length }) }}</span>
              <button class="btn sm" @click="requestCleanup">{{ t('puppet.action.cleanup') }}</button>
            </div>
            <div class="run-logs mono">
              <div v-for="(line, index) in run.logs" :key="index" class="log-line">{{ line }}</div>
            </div>
          </template>
        </div>

        <div v-else class="panel-body ledger-body">
          <div v-if="!orders.length" class="empty">{{ t('puppet.empty.history') }}</div>
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

    <StationDialog
      :open="stationDialogOpen"
      :station="editing"
      @close="stationDialogOpen = false"
      @save="saveStation"
    />
    <ImportDialog :open="importOpen" @close="importOpen = false" @done="onImported" />

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
.workbench {
  height: 100%;
  width: 100%;
  display: grid;
  grid-template-columns: 360px minmax(0, 1fr);
  gap: 14px;
  min-height: 0;
  min-width: 0;
}

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

.stations-panel {
  flex: 1 0 240px;
  min-height: 240px;
}

.order-panel {
  flex: 0 0 auto;
  position: relative;
  z-index: 5;
  overflow: visible;
}

.order-body {
  overflow: visible;
}

.commands-panel {
  flex: 1;
  min-height: 200px;
}

.bottom-panel {
  flex: 0 0 240px;
  min-height: 200px;
}

.head-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  padding: 8px 14px;
  border-bottom: 1px solid var(--line);
}

.toolbar .execute {
  margin-left: 4px;
}

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

.restored-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ledger-row.clickable {
  cursor: pointer;
}

.commands-panel .panel-head,
.bottom-panel .panel-head {
  flex-wrap: wrap;
  row-gap: 6px;
}

.stations-body {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.search {
  height: 30px;
  font-size: 12px;
}

.station-filter {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

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

.station-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.station-row {
  padding: 6px 8px;
  border: 1px solid transparent;
  border-radius: 8px;
}

.station-line {
  display: flex;
  align-items: center;
  gap: 8px;
}

.station-row:hover {
  background: var(--surface-2);
}

.station-row.active {
  border-color: var(--brand-dim);
  background: var(--select-bg);
}

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

.station-main {
  flex: 1;
  min-width: 0;
}

.station-name {
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

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

.station-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 2px;
  font-size: 10px;
  color: var(--muted);
}

.station-actions {
  display: flex;
  gap: 2px;
  opacity: 0;
  transition: opacity 0.15s ease;
}

.station-row:hover .station-actions {
  opacity: 1;
}

.danger-text {
  color: var(--danger);
}

.order-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.summary {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px 10px;
  border: 1px dashed var(--line-strong);
  border-radius: 8px;
  font-size: 12px;
}

.tabs.inline {
  display: flex;
  gap: 2px;
  margin: 0;
}

.tab-count {
  margin-left: 6px;
  color: var(--muted);
  font-size: 10px;
}

.commands-body {
  padding: 0;
}

.command-list {
  display: flex;
  flex-direction: column;
}

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

.run-body {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.run-line {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
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

.current {
  font-size: 11px;
  color: var(--muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

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

.run-logs {
  flex: 1;
  min-height: 90px;
  overflow: auto;
  padding: 8px 10px;
  border-radius: 8px;
  background: var(--bg);
  font-size: 10px;
  line-height: 1.6;
}

.log-line {
  color: var(--muted);
  white-space: pre-wrap;
  word-break: break-all;
}

.ledger-body {
  padding: 0;
}

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

.ledger td.spawn-cell {
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--muted);
}

.ledger tbody tr:hover {
  background: var(--surface-2);
}

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

.dialog.wide {
  width: 640px;
}

.dialog-head,
.dialog-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--line);
}

.dialog-foot {
  border-bottom: none;
  border-top: 1px solid var(--line);
  justify-content: flex-end;
  gap: 8px;
}

.dialog-body {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 16px;
}

.confirm-text {
  margin: 0;
  font-size: 12px;
  line-height: 1.8;
}

.warn-text {
  color: var(--warn);
  font-size: 12px;
}

.diag-row {
  display: grid;
  grid-template-columns: 60px 80px minmax(0, 1fr);
  align-items: center;
  gap: 8px;
  font-size: 12px;
}

.diag-id {
  color: var(--muted);
}

.hint {
  margin: 4px 0 0;
  color: var(--muted);
  font-size: 11px;
  line-height: 1.7;
}
</style>
