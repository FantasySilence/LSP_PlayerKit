<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { callTool, invoke } from '../../platform/bridge'
import { t } from '../../platform/i18n'
import { clone, getSettings, loadSettings, saveSettings } from '../../platform/settings'
import { notify, notifyError } from '../../platform/toast'
import type { BorderRow, ToolDef } from '../../platform/types'
import DataTable from '../../ui/DataTable.vue'

const props = defineProps<{ tool: ToolDef }>()

const originX = ref<number | string>(9996.24)
const originY = ref<number | string>(256)
const originZ = ref<number | string>(9999.24)
const targetX = ref<number | string>(0)
const targetY = ref<number | string>(128)
const targetZ = ref<number | string>(0)
const flightTime = ref<number | string>(1200)
const directionMode = ref('origin')

const rows = ref<BorderRow[]>([])
const selected = ref<number | null>(null)
const busy = ref(false)

interface DecodeResult {
  valid: boolean
  reason?: string
  small?: Record<string, string>
  big?: Record<string, string>
  landing?: { x: number; z: number; ticks: number }
  text?: string
  tnt?: number[]
}

const decoded = ref<DecodeResult | null>(null)
const current = computed(() => (selected.value === null ? null : rows.value[selected.value] ?? null))

const tableRows = computed(() =>
  rows.value.map((row) => ({ ...row, dirText: t(`border.dir.${row.dirCode}`) })),
)

const validCount = computed(
  () => rows.value.filter((row) => Math.min(row.t1, row.t2, row.t3) >= 0).length,
)

function toNumber(value: number | string, label: string): number {
  const parsed = Number(value)
  if (!Number.isFinite(parsed) || String(value).trim() === '') {
    throw new Error(`${label} 不是有效数字`)
  }
  return parsed
}

async function applySettings() {
  const data = await loadSettings(props.tool.id)
  originX.value = data.originX
  originY.value = data.originY
  originZ.value = data.originZ
  targetX.value = data.targetX
  targetY.value = data.targetY
  targetZ.value = data.targetZ
  flightTime.value = data.flightTime
  directionMode.value = data.directionMode
}

async function saveAsDefault() {
  try {
    const data = clone(getSettings(props.tool.id))
    data.originX = toNumber(originX.value, '炮口 X')
    data.originY = toNumber(originY.value, '炮口 Y')
    data.originZ = toNumber(originZ.value, '炮口 Z')
    data.targetX = toNumber(targetX.value, '目标 X')
    data.targetY = toNumber(targetY.value, '目标 Y')
    data.targetZ = toNumber(targetZ.value, '目标 Z')
    data.flightTime = toNumber(flightTime.value, '预计飞行时间')
    await saveSettings(props.tool.id, data)
    notify('success', t('action.defaultSaved'))
  } catch (error) {
    notifyError(error)
  }
}

async function calculate() {
  busy.value = true
  try {
    const result = await callTool<{ rows: BorderRow[]; directionMode: string }>(
      props.tool.id,
      'calculate',
      {
        origin: {
          x: toNumber(originX.value, '炮口 X'),
          y: toNumber(originY.value, '炮口 Y'),
          z: toNumber(originZ.value, '炮口 Z'),
        },
        target: {
          x: toNumber(targetX.value, '目标 X'),
          y: toNumber(targetY.value, '目标 Y'),
          z: toNumber(targetZ.value, '目标 Z'),
        },
        time: toNumber(flightTime.value, '预计飞行时间'),
      },
    )
    rows.value = result.rows
    selected.value = null
    decoded.value = null
    if (result.rows.length) {
      const firstValid = result.rows.findIndex((row) => Math.min(row.t1, row.t2, row.t3) >= 0)
      await selectRow(firstValid >= 0 ? firstValid : 0)
    } else {
      notify('info', t('border.msg.noRows'))
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
    const result = await callTool<DecodeResult>(props.tool.id, 'decode', {
      tnt: [row.t1, row.t2, row.t3],
      motion: { x: row.mx, y: row.my, z: row.mz },
      dirLabel: row.dirLabel,
      origin: {
        x: toNumber(originX.value, '炮口 X'),
        y: toNumber(originY.value, '炮口 Y'),
        z: toNumber(originZ.value, '炮口 Z'),
      },
    })
    decoded.value = result
  } catch (error) {
    decoded.value = null
    notifyError(error)
  }
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
        <span>{{ t('border.panel.input') }}</span>
        <span class="badge" :title="t('border.msg.directionModeHint')">
          {{ directionMode === 'origin' ? t('border.option.directionOrigin') : t('border.option.directionFixed') }}
        </span>
      </div>
      <div class="panel-body">
        <div class="coord-block origin">
          <div class="coord-head">
            <span class="marker" />
            <span class="coord-title">{{ t('border.panel.origin') }}</span>
            <span class="coord-tag">{{ t('border.panel.originTag') }}</span>
          </div>
          <div class="coords">
            <label class="coord">
              <span class="axis">X</span>
              <input
                v-model.number="originX"
                class="input mono"
                type="number"
                :title="t('border.field.originX')"
                :aria-label="t('border.field.originX')"
              />
            </label>
            <label class="coord">
              <span class="axis">Y</span>
              <input
                v-model.number="originY"
                class="input mono"
                type="number"
                :title="t('border.field.originY')"
                :aria-label="t('border.field.originY')"
              />
            </label>
            <label class="coord">
              <span class="axis">Z</span>
              <input
                v-model.number="originZ"
                class="input mono"
                type="number"
                :title="t('border.field.originZ')"
                :aria-label="t('border.field.originZ')"
              />
            </label>
          </div>
        </div>

        <div class="coord-block target">
          <div class="coord-head">
            <span class="marker" />
            <span class="coord-title">{{ t('border.panel.target') }}</span>
            <span class="coord-tag">{{ t('border.panel.targetTag') }}</span>
          </div>
          <div class="coords">
            <label class="coord">
              <span class="axis">X</span>
              <input
                v-model.number="targetX"
                class="input mono"
                type="number"
                :title="t('border.field.targetX')"
                :aria-label="t('border.field.targetX')"
              />
            </label>
            <label class="coord">
              <span class="axis">Y</span>
              <input
                v-model.number="targetY"
                class="input mono"
                type="number"
                :title="t('border.field.targetY')"
                :aria-label="t('border.field.targetY')"
              />
            </label>
            <label class="coord">
              <span class="axis">Z</span>
              <input
                v-model.number="targetZ"
                class="input mono"
                type="number"
                :title="t('border.field.targetZ')"
                :aria-label="t('border.field.targetZ')"
              />
            </label>
          </div>
        </div>

        <div class="field">
          <label class="field-label">
            <span>{{ t('border.field.flightTime') }}</span>
            <span class="unit">gt</span>
          </label>
          <input v-model.number="flightTime" class="input mono" type="number" min="1" step="10" />
        </div>

        <div class="actions">
          <button class="btn primary" :disabled="busy" @click="calculate">
            {{ busy ? t('status.calculating') : t('border.action.calculate') }}
          </button>
        </div>

        <div class="secondary-actions">
          <button class="btn sm" @click="saveAsDefault">
            {{ t('action.saveAsDefault') }}
          </button>
          <button class="btn sm" @click="applySettings">
            {{ t('action.applyDefaults') }}
          </button>
        </div>

        <div class="tip muted">{{ t('border.panel.tip') }}</div>
      </div>
    </section>

    <section class="panel">
      <div class="panel-head">
        <span>{{ t('border.panel.result') }}</span>
        <span class="head-meta">
          <span v-if="rows.length && validCount === 0" class="badge warn">
            {{ t('border.msg.noValid') }}
          </span>
          <span class="muted">{{ rows.length }} {{ t('label.rows') }}</span>
        </span>
      </div>

      <div class="result-body">
        <DataTable
          :columns="tool.columns"
          :rows="tableRows"
          :selected="selected"
          @select="selectRow"
        />
      </div>

      <footer v-if="decoded" class="detail">
        <div v-if="!decoded.valid" class="invalid">
          <span class="badge warn">{{ t('border.decode.invalid') }}</span>
          <span class="muted">{{ decoded.reason }}</span>
          <span class="muted">{{ t('border.decode.invalidHint') }}</span>
        </div>

        <template v-else>
          <div class="detail-head">
            <span class="badge brand">{{ t('border.decode.title') }}</span>
            <span class="landing">
              <span class="landing-label">{{ t('border.decode.landing') }}</span>
              <span class="mono landing-value">
                <span>X = {{ decoded.landing?.x.toFixed(3) }}</span>
                <span>Z = {{ decoded.landing?.z.toFixed(3) }}</span>
              </span>
            </span>
            <button class="btn ghost sm" @click="copy(decoded.text ?? '')">
              {{ t('action.copy') }}
            </button>
          </div>

          <div class="detail-grid">
            <div v-for="index in 3" :key="index" class="detail-card">
              <div class="detail-title">{{ t('border.decode.tnt', { n: index }) }}</div>
              <div class="line">
                <span class="muted">{{ t('border.decode.small') }}</span>
                <span class="mono">{{ decoded.small?.[index - 1] }}</span>
              </div>
              <div class="line">
                <span class="muted">{{ t('border.decode.big') }}</span>
                <span class="mono">{{ decoded.big?.[index - 1] }}</span>
              </div>
            </div>
          </div>

          <div class="motion mono muted">
            {{ t('border.decode.motion') }}:
            {{ current?.mx.toFixed(6) }} / {{ current?.my.toFixed(6) }} / {{ current?.mz.toFixed(6) }}
          </div>
        </template>
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

.coord-block {
  margin-bottom: 12px;
  padding: 10px;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: var(--surface-2);
}

.coord-block.target {
  border-color: rgba(62, 224, 196, 0.35);
  background: var(--brand-soft);
}

.coord-head {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
  font-size: 12px;
}

.coord-block.target .coord-head {
  color: var(--brand);
}

.marker {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--muted);
}

.coord-block.target .marker {
  background: var(--brand);
}

.coord-title {
  font-weight: 500;
}

.coord-tag {
  margin-left: auto;
  color: var(--muted);
  font-size: 11px;
}

.coords {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.coord {
  display: flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
  padding: 0 8px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--bg);
}

.coord:focus-within {
  border-color: var(--brand-dim);
  box-shadow: 0 0 0 3px var(--brand-soft);
}

.coord .axis {
  color: var(--muted);
  font-family: var(--font-mono);
  font-size: 11px;
}

.coord .input {
  flex: 1;
  width: 100%;
  min-width: 0;
  height: 32px;
  padding: 0;
  border: none;
  background: transparent;
}

.coord .input:focus {
  box-shadow: none;
}

.actions {
  display: flex;
  gap: 8px;
  margin-top: 4px;
}

.actions .primary {
  flex: 1;
}

.secondary-actions {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}

.secondary-actions .btn {
  flex: 1;
}

.tip {
  margin-top: 14px;
  font-size: 11px;
  line-height: 1.7;
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

.detail {
  border-top: 1px solid var(--line);
  background: var(--surface-2);
  padding: 10px 12px;
  max-height: 42%;
  overflow: auto;
}

.detail-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}

.landing {
  display: inline-flex;
  align-items: baseline;
  gap: 6px;
  font-size: 12px;
}

.landing-label {
  color: var(--muted);
}

.landing-value {
  display: inline-flex;
  gap: 10px;
  color: var(--text);
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
}

.detail-card {
  padding: 8px 10px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--surface);
  min-width: 0;
}

.detail-title {
  color: var(--muted);
  font-size: 11px;
  margin-bottom: 4px;
}

.line {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 11px;
  word-break: break-all;
}

.motion {
  margin-top: 8px;
  font-size: 11px;
}

.invalid {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}
</style>
