<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { callTool, invoke } from '../../platform/bridge'
import { t } from '../../platform/i18n'
import { loadSettings } from '../../platform/settings'
import { notify, notifyError } from '../../platform/toast'
import type { ColumnDef, PearlRow, ToolDef } from '../../platform/types'
import CompassRose from '../../ui/CompassRose.vue'
import DataTable from '../../ui/DataTable.vue'

interface TracePoint {
  t: number
  x: number
  y: number
  z: number
}

const props = defineProps<{ tool: ToolDef }>()

const originX = ref<number | string>(0)
const originZ = ref<number | string>(0)
const targetX = ref<number | string>(0)
const targetZ = ref<number | string>(0)
const maxTnt = ref<number | string>(3640)
const mode = ref<'flat' | 'eject'>('flat')
const ejectionAvailable = ref(true)

const rows = ref<PearlRow[]>([])
const selected = ref<number | null>(null)
const direction = ref<string | null>(null)
const manualDirection = ref(false)
const tab = ref<'table' | 'trace'>('table')
const points = ref<TracePoint[]>([])
const landingTick = ref<number | null>(null)
const busy = ref(false)
const calcVersion = ref(0)
const decode = ref<{ blueText: string; redText: string; blue: number[]; red: number[] } | null>(null)

const traceColumns: ColumnDef[] = [
  { key: 't', nameKey: 'pearl.trace.col.t', type: 'int' },
  { key: 'x', nameKey: 'pearl.trace.col.x', type: 'float', digits: 3 },
  { key: 'y', nameKey: 'pearl.trace.col.y', type: 'float', digits: 3 },
  { key: 'z', nameKey: 'pearl.trace.col.z', type: 'float', digits: 3 },
]

const pointRows = computed(() => points.value as unknown as Record<string, any>[])

const landingIndex = computed(() => {
  if (landingTick.value === null) return null
  const index = points.value.findIndex((point) => point.t === landingTick.value)
  return index >= 0 ? index : null
})

const current = computed(() => (selected.value === null ? null : rows.value[selected.value] ?? null))
const canSimulate = computed(() => current.value !== null)

function toNumber(value: number | string, label: string): number {
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) throw new Error(`${label} 不是有效数字`)
  return parsed
}

async function applySettings() {
  const data = await loadSettings(props.tool.id)
  originX.value = data.originX
  originZ.value = data.originZ
  maxTnt.value = data.maxTnt
  ejectionAvailable.value = Boolean(data.ejectionAvailable)
  if (!ejectionAvailable.value) mode.value = 'flat'
}

async function calculate() {
  busy.value = true
  try {
    const result = await callTool<{ direction: string; rows: PearlRow[]; mode: string }>(
      props.tool.id,
      'calculate',
      {
        origin: { x: toNumber(originX.value, '炮口 X'), z: toNumber(originZ.value, '炮口 Z') },
        target: { x: toNumber(targetX.value, '目标 X'), z: toNumber(targetZ.value, '目标 Z') },
        maxTnt: toNumber(maxTnt.value, '最大 TNT'),
        mode: mode.value,
      },
    )
    rows.value = result.rows
    calcVersion.value += 1
    direction.value = result.direction
    manualDirection.value = false
    points.value = []
    landingTick.value = null
    tab.value = 'table'
    decode.value = null
    if (result.rows.length) {
      let best = 0
      result.rows.forEach((row, index) => {
        if (row.error < result.rows[best].error) best = index
      })
      await selectRow(best)
    } else {
      selected.value = null
      notify('info', t('pearl.msg.noRows'))
    }
  } catch (error) {
    notifyError(error)
  } finally {
    busy.value = false
  }
}

async function selectRow(index: number) {
  selected.value = index
  const row = rows.value[index]
  if (!row) return
  try {
    const result = await callTool<{
      blue: number[]
      red: number[]
      blueText: string
      redText: string
    }>(props.tool.id, 'decode', { blue: row.blue, red: row.red })
    decode.value = result
  } catch (error) {
    decode.value = null
    notifyError(error)
  }
}

function selectDirection(value: 'north' | 'east' | 'south' | 'west') {
  direction.value = value
  manualDirection.value = true
}

async function simulate() {
  const row = current.value
  if (!row) return
  busy.value = true
  try {
    const result = await callTool<{ points: TracePoint[] }>(props.tool.id, 'trace', {
      origin: { x: toNumber(originX.value, '炮口 X'), z: toNumber(originZ.value, '炮口 Z') },
      direction: direction.value ?? 'east',
      mode: mode.value,
      ticks: row.ticks + 50,
      blue: row.blue,
      red: row.red,
    })
    points.value = result.points
    landingTick.value = row.ticks
    tab.value = 'trace'
  } catch (error) {
    notifyError(error)
  } finally {
    busy.value = false
  }
}

function formatParts(parts: number[]): string {
  const total = parts.reduce((sum, part) => sum + part, 0)
  if (parts.length <= 1) return String(total)
  return `${parts.join(' + ')} = ${total}`
}

async function copy(text: string) {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
    } else {
      await invoke('clipboard_write', text)
    }
    notify('success', t('action.copied'))
  } catch (error) {
    try {
      await invoke('clipboard_write', text)
      notify('success', t('action.copied'))
    } catch (fallbackError) {
      notifyError(fallbackError)
    }
  }
}

onMounted(async () => {
  try {
    await applySettings()
  } catch (error) {
    notifyError(error)
  }
})
</script>

<template>
  <div class="workbench">
    <section class="panel">
      <div class="panel-head">
        <span>{{ t('pearl.panel.input') }}</span>
        <span class="badge">{{ mode === 'flat' ? t('pearl.mode.flat') : t('pearl.mode.eject') }}</span>
      </div>
      <div class="panel-body">
        <div class="field-row">
          <div class="field">
            <label class="field-label">{{ t('pearl.field.originX') }}</label>
            <input v-model.number="originX" class="input mono" type="number" step="0.0625" />
          </div>
          <div class="field">
            <label class="field-label">{{ t('pearl.field.originZ') }}</label>
            <input v-model.number="originZ" class="input mono" type="number" step="0.0625" />
          </div>
        </div>

        <div class="field-row">
          <div class="field">
            <label class="field-label">{{ t('pearl.field.targetX') }}</label>
            <input v-model.number="targetX" class="input mono" type="number" />
          </div>
          <div class="field">
            <label class="field-label">{{ t('pearl.field.targetZ') }}</label>
            <input v-model.number="targetZ" class="input mono" type="number" />
          </div>
        </div>

        <div class="field">
          <label class="field-label">
            <span>{{ t('pearl.field.maxTnt') }}</span>
            <span class="unit">{{ t('pearl.unit.tnt') }}</span>
          </label>
          <input v-model.number="maxTnt" class="input mono" type="number" min="1" step="10" />
        </div>

        <div class="field">
          <label class="field-label">{{ t('pearl.field.mode') }}</label>
          <div class="segmented">
            <button :class="{ active: mode === 'flat' }" @click="mode = 'flat'">
              {{ t('pearl.mode.flat') }}
            </button>
            <button
              :class="{ active: mode === 'eject' }"
              :disabled="!ejectionAvailable"
              :title="ejectionAvailable ? '' : t('pearl.msg.ejectDisabled')"
              @click="mode = 'eject'"
            >
              {{ t('pearl.mode.eject') }}
            </button>
          </div>
        </div>

        <div class="field direction-field">
          <label class="field-label">
            <span>{{ t('pearl.field.direction') }}</span>
            <span v-if="manualDirection" class="badge warn">{{ t('direction.manual') }}</span>
          </label>
          <CompassRose :direction="direction" :manual="manualDirection" @select="selectDirection" />
        </div>

        <div class="actions">
          <button class="btn primary" :disabled="busy" @click="calculate">
            {{ busy ? t('status.calculating') : t('pearl.action.calculate') }}
          </button>
          <button class="btn" :disabled="busy || !canSimulate" @click="simulate">
            {{ t('pearl.action.trace') }}
          </button>
          <button class="btn ghost" :title="t('pearl.msg.loadDefaults')" @click="applySettings">
            ⟲
          </button>
        </div>
      </div>
    </section>

    <section class="panel">
      <div class="panel-head">
        <div class="tabs">
          <button class="tab" :class="{ active: tab === 'table' }" @click="tab = 'table'">
            {{ t('tabs.table') }}
          </button>
          <button class="tab" :class="{ active: tab === 'trace' }" @click="tab = 'trace'">
            {{ t('tabs.trace') }}
          </button>
        </div>
        <span class="muted">
          {{ direction ? t(`direction.${direction}`) : t('direction.unknown') }} ·
          {{ rows.length }} {{ t('label.rows') }}
        </span>
      </div>

      <div class="result-body">
        <DataTable
          v-if="tab === 'table'"
          :key="calcVersion"
          :columns="tool.columns"
          :rows="rows"
          :selected="selected"
          :sortable="['error', 'ticks']"
          :default-sort="{ key: 'ticks', dir: 'asc' }"
          @select="selectRow"
        />
        <div v-else class="trace-panel">
          <DataTable
            :columns="traceColumns"
            :rows="pointRows"
            :selected="null"
            :highlight-index="landingIndex"
          />
        </div>
      </div>

      <footer v-if="decode" class="decode-bar">
        <div class="decode-line">
          <span class="badge brand">{{ t('pearl.decode.blue') }}</span>
          <span class="decode-value blue mono">{{ formatParts(decode.blue) }}</span>
          <button class="btn ghost sm" @click="copy(formatParts(decode.blue))">
            {{ t('action.copy') }}
          </button>
        </div>
        <div class="decode-line">
          <span class="badge">{{ t('pearl.decode.red') }}</span>
          <span class="decode-value red mono">{{ formatParts(decode.red) }}</span>
          <button class="btn ghost sm" @click="copy(formatParts(decode.red))">
            {{ t('action.copy') }}
          </button>
        </div>
      </footer>
    </section>
  </div>
</template>

<style scoped>
.workbench {
  height: 100%;
  display: grid;
  grid-template-columns: 360px minmax(0, 1fr);
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

.segmented {
  display: grid;
  grid-template-columns: 1fr 1fr;
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
  cursor: pointer;
}

.segmented button.active {
  background: var(--brand);
  color: #04241f;
  font-weight: 600;
}

.segmented button:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.direction-field {
  align-items: center;
}

.actions {
  display: flex;
  gap: 8px;
  margin-top: 4px;
}

.actions .primary {
  flex: 1;
}

.result-body {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.trace-panel {
  height: 100%;
  min-height: 0;
  display: flex;
}

.trace-panel > * {
  flex: 1;
  min-width: 0;
}

.decode-bar {
  border-top: 1px solid var(--line);
  padding: 8px 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  background: var(--surface-2);
}

.decode-line {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.decode-value {
  flex: 1;
  min-width: 0;
  display: inline-flex;
  align-items: center;
  padding: 5px 12px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--surface);
  color: var(--text);
  font-size: 13px;
  letter-spacing: 0.02em;
  word-break: break-all;
}

.decode-value.blue {
  border-color: rgba(62, 224, 196, 0.35);
  background: var(--brand-soft);
  color: var(--brand);
}

.decode-value.red {
  border-color: rgba(255, 106, 77, 0.35);
  background: var(--accent-soft);
  color: var(--accent);
}
</style>
