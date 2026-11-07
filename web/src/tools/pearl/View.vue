<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { callTool, invoke } from '../../platform/bridge'
import { t } from '../../platform/i18n'
import { clone, getSettings, loadSettings, saveSettings } from '../../platform/settings'
import { notify, notifyError } from '../../platform/toast'
import type { ColumnDef, PearlRow, ToolDef } from '../../platform/types'
import CompassRose from '../../ui/CompassRose.vue'
import DataTable from '../../ui/DataTable.vue'

// 轨迹采样点：t 为游戏刻，x / y / z 为该刻的珍珠坐标
interface TracePoint {
  t: number
  x: number
  y: number
  z: number
}

const props = defineProps<{ tool: ToolDef }>()

// 输入：炮口与目标的水平坐标（高度由后端按平射 / 抛射模式决定）
const originX = ref<number | string>(0)
const originZ = ref<number | string>(0)
const targetX = ref<number | string>(0)
const targetZ = ref<number | string>(0)
// 参与搜索的 TNT 总数量上限
const maxTnt = ref<number | string>(3640)
// 发射模式：flat 平射 / eject 抛射；ejectionAvailable 表示炮架是否支持抛射
const mode = ref<'flat' | 'eject'>('flat')
const ejectionAvailable = ref(true)

// 计算结果行（每种 TNT 组合一行）与当前选中行下标
const rows = ref<PearlRow[]>([])
const selected = ref<number | null>(null)
// 炮口朝向：默认由后端算出；在罗盘上手动选择后 manualDirection 置为 true
const direction = ref<string | null>(null)
const manualDirection = ref(false)
// 结果区当前标签：table 结果表 / trace 轨迹表
const tab = ref<'table' | 'trace'>('table')
// 轨迹点与落地刻（landingTick 为 null 表示没有落地位置）
const points = ref<TracePoint[]>([])
const landingTick = ref<number | null>(null)
// 手动模拟的轨迹从第一行开始看（右侧结果仍高亮落地刻）
const traceAtTop = ref(false)
// 请求进行中标记：按钮禁用与文案切换用
const busy = ref(false)
// 每次计算后自增，作为结果表的 key 强制重建（复位默认排序与滚动位置）
const calcVersion = ref(0)
// 选中行的 TNT 拆解结果（蓝 / 红各拆成若干份），null 表示尚未解码
const decode = ref<{ blueText: string; redText: string; blue: number[]; red: number[] } | null>(null)

// ------ 手动模拟：不依赖结果表，直接按蓝 / 红 TNT 数量走弹道 ------
// 手动输入的蓝 / 红 TNT 数量；manualSummary 为模拟后的落地或滞空提示
const manualBlue = ref<number | string>(0)
const manualRed = ref<number | string>(0)
const manualSummary = ref('')

// 轨迹表列：刻 + 三轴坐标（坐标保留 3 位小数）
const traceColumns: ColumnDef[] = [
  { key: 't', nameKey: 'pearl.trace.col.t', type: 'int' },
  { key: 'x', nameKey: 'pearl.trace.col.x', type: 'float', digits: 3 },
  { key: 'y', nameKey: 'pearl.trace.col.y', type: 'float', digits: 3 },
  { key: 'z', nameKey: 'pearl.trace.col.z', type: 'float', digits: 3 },
]

// DataTable 需要索引签名，这里只做类型转换，不复制数据
const pointRows = computed(() => points.value as unknown as Record<string, any>[])

// 落地刻在轨迹点中的下标，用于表格高亮；找不到对应刻时为 null
const landingIndex = computed(() => {
  if (landingTick.value === null) return null
  const index = points.value.findIndex((point) => point.t === landingTick.value)
  return index >= 0 ? index : null
})

// 当前选中行；没有选中行时无法生成轨迹（canSimulate）
const current = computed(() => (selected.value === null ? null : rows.value[selected.value] ?? null))
const canSimulate = computed(() => current.value !== null)

// 输入框绑定的是 number | string，统一转成有限数字，否则抛错交给调用方提示
function toNumber(value: number | string, label: string): number {
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) throw new Error(`${label} 不是有效数字`)
  return parsed
}

// 读取该工具的默认设置并回填输入框；抛射模式只在炮架支持时才启用
async function applySettings() {
  const data = await loadSettings(props.tool.id)
  originX.value = data.originX
  originZ.value = data.originZ
  targetX.value = data.targetX ?? 0
  targetZ.value = data.targetZ ?? 0
  maxTnt.value = data.maxTnt
  ejectionAvailable.value = Boolean(data.ejectionAvailable)
  mode.value = data.fireMode === 'eject' && ejectionAvailable.value ? 'eject' : 'flat'
}

// 保存为默认：基于已保存的设置做浅拷贝，只覆盖本页填写过的字段，其余字段保持原值
async function saveAsDefault() {
  try {
    const data = clone(getSettings(props.tool.id))
    data.originX = toNumber(originX.value, '炮口 X')
    data.originZ = toNumber(originZ.value, '炮口 Z')
    data.targetX = toNumber(targetX.value, '目标 X')
    data.targetZ = toNumber(targetZ.value, '目标 Z')
    data.maxTnt = toNumber(maxTnt.value, '最大 TNT')
    data.fireMode = mode.value
    await saveSettings(props.tool.id, data)
    notify('success', t('action.defaultSaved'))
  } catch (error) {
    notifyError(error)
  }
}

// 计算：把炮口 / 目标 / 最大 TNT / 模式交给后端，返回方向与候选结果行
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
    manualSummary.value = ''
    // 有结果时默认选中误差最小的行（error 最小），没有结果就提示
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

// 选中行：记录下标并请求该行的 TNT 拆解，供底部解码条显示
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

// 罗盘手动选向：直接覆盖后端给出的方向，并标记为手动
function selectDirection(value: 'north' | 'east' | 'south' | 'west') {
  direction.value = value
  manualDirection.value = true
}

// 按选中行的 TNT 组合生成轨迹：ticks 多加 50 以保证能看到落地，并高亮落地刻
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
    traceAtTop.value = false
    tab.value = 'trace'
  } catch (error) {
    notifyError(error)
  } finally {
    busy.value = false
  }
}

// 手动模拟：不依赖结果行，按手填蓝 / 红 TNT 与方向推算，返回落地信息或滞空提示
async function simulateManual() {
  if (!direction.value) {
    notify('info', t('pearl.manual.needDirection'))
    return
  }
  busy.value = true
  try {
    const result = await callTool<{
      points: TracePoint[]
      landing: { tick: number; x: number; y: number; z: number } | null
      distance: number
      ticks: number
      total: number
      groundY: number
    }>(props.tool.id, 'simulate', {
      origin: { x: toNumber(originX.value, '炮口 X'), z: toNumber(originZ.value, '炮口 Z') },
      direction: direction.value,
      mode: mode.value,
      blue: toNumber(manualBlue.value, '蓝色 TNT'),
      red: toNumber(manualRed.value, '红色 TNT'),
      ticks: 400,
    })
    points.value = result.points
    landingTick.value = result.landing ? result.landing.tick : null
    traceAtTop.value = true
    manualSummary.value = result.landing
      ? t('pearl.manual.landed', {
          tick: result.landing.tick,
          x: result.landing.x.toFixed(1),
          z: result.landing.z.toFixed(1),
          distance: Math.round(result.distance),
          ground: result.groundY,
        })
      : t('pearl.manual.airborne', { ticks: result.ticks })
    decode.value = null
    tab.value = 'trace'
  } catch (error) {
    notifyError(error)
  } finally {
    busy.value = false
  }
}

// 把拆解出的份数拼成「a + b = 总数」，只有一份时直接显示总数
function formatParts(parts: number[]): string {
  const total = parts.reduce((sum, part) => sum + part, 0)
  if (parts.length <= 1) return String(total)
  return `${parts.join(' + ')} = ${total}`
}

// 复制到剪贴板：优先浏览器 API，不可用或失败时退回后端剪贴板接口
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

// 首次挂载时读取默认设置
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
    <!-- 区块：输入参数（炮口 / 目标 / 最大 TNT / 模式 / 方向） -->
    <section class="panel">
      <div class="panel-head">
        <span>{{ t('pearl.panel.input') }}</span>
        <span class="badge">{{ mode === 'flat' ? t('pearl.mode.flat') : t('pearl.mode.eject') }}</span>
      </div>
      <div class="panel-body">
        <!-- 炮口 X / Z：步进为 1/16 格 -->
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

        <!-- 目标 X / Z -->
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

        <!-- 参与搜索的最大 TNT 总数 -->
        <div class="field">
          <label class="field-label">
            <span>{{ t('pearl.field.maxTnt') }}</span>
            <span class="unit">{{ t('pearl.unit.tnt') }}</span>
          </label>
          <input v-model.number="maxTnt" class="input mono" type="number" min="1" step="10" />
        </div>

        <!-- 平射 / 抛射切换；炮架不支持抛射时按钮禁用 -->
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

        <!-- 方向罗盘：手动点选后标记为手动，模拟时优先采用 -->
        <div class="field direction-field">
          <label class="field-label">
            <span>{{ t('pearl.field.direction') }}</span>
            <span v-if="manualDirection" class="badge warn">{{ t('direction.manual') }}</span>
          </label>
          <CompassRose :direction="direction" :manual="manualDirection" @select="selectDirection" />
        </div>

        <!-- 手动模拟：直接给蓝 / 红 TNT 与方向，不依赖结果表 -->
        <div class="manual-block">
          <div class="manual-head">
            <span class="manual-title">{{ t('pearl.manual.title') }}</span>
            <span class="manual-hint">{{ t('pearl.manual.hint') }}</span>
          </div>
          <div class="field-row">
            <div class="field">
              <label class="field-label">
                <span>{{ t('pearl.field.blueTnt') }}</span>
                <span class="unit">{{ t('pearl.unit.tnt') }}</span>
              </label>
              <input v-model.number="manualBlue" class="input mono" type="number" min="0" step="1" />
            </div>
            <div class="field">
              <label class="field-label">
                <span>{{ t('pearl.field.redTnt') }}</span>
                <span class="unit">{{ t('pearl.unit.tnt') }}</span>
              </label>
              <input v-model.number="manualRed" class="input mono" type="number" min="0" step="1" />
            </div>
          </div>
          <button
            class="btn block"
            :disabled="busy || !direction"
            :title="direction ? '' : t('pearl.manual.needDirection')"
            @click="simulateManual"
          >
            {{ t('pearl.action.simulateManual') }}
          </button>
          <div v-if="manualSummary" class="manual-summary mono">{{ manualSummary }}</div>
        </div>

        <!-- 计算与生成轨迹 -->
        <div class="actions">
          <button class="btn primary" :disabled="busy" @click="calculate">
            {{ busy ? t('status.calculating') : t('pearl.action.calculate') }}
          </button>
          <button class="btn" :disabled="busy || !canSimulate" @click="simulate">
            {{ t('pearl.action.trace') }}
          </button>
        </div>

        <!-- 保存为默认 / 应用默认值 -->
        <div class="secondary-actions">
          <button class="btn sm" @click="saveAsDefault">
            {{ t('action.saveAsDefault') }}
          </button>
          <button class="btn sm" @click="applySettings">
            {{ t('action.applyDefaults') }}
          </button>
        </div>
      </div>
    </section>

    <!-- 区块：结果与轨迹（结果表 / 轨迹表两个标签页） -->
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
          {{ tab === 'trace' ? points.length : rows.length }} {{ t('label.rows') }}
        </span>
      </div>

      <div class="result-body">
        <!-- 结果表：仅误差与刻可排序，默认按刻升序 -->
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
        <!-- 轨迹表：到达行高亮；手动模拟时从第 1 行开始看，不自动滚动 -->
        <div v-else class="trace-panel">
          <DataTable
            :columns="traceColumns"
            :rows="pointRows"
            :selected="null"
            :highlight-index="landingIndex"
            :scroll-to-target="!traceAtTop"
          />
        </div>
      </div>

      <!-- 解码条：蓝 / 红 TNT 的拆解份数，可分别复制 -->
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
/* 区块：整体布局（左侧参数 360px + 右侧结果） */
.workbench {
  height: 100%;
  display: grid;
  grid-template-columns: 360px minmax(0, 1fr);
  gap: 14px;
  min-height: 0;
  min-width: 0;
}

/* 窄屏改为上下两栏并允许纵向滚动 */
@media (max-width: 1080px) {
  .workbench {
    grid-template-columns: 1fr;
    grid-template-rows: auto 1fr;
    overflow: auto;
  }
}

/* 区块：分段按钮（平射 / 抛射） */
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

/* 区块：方向罗盘与手动模拟面板 */
.direction-field {
  align-items: center;
}

.manual-block {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 4px;
  padding: 10px;
  border: 1px dashed var(--line-strong);
  border-radius: 10px;
  background: var(--surface-2);
}

.manual-head {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.manual-title {
  font-size: 12px;
}

.manual-hint {
  color: var(--muted);
  font-size: 11px;
  line-height: 1.5;
}

.manual-summary {
  padding: 6px 8px;
  border-radius: 6px;
  background: var(--brand-soft);
  color: var(--brand);
  font-size: 11px;
  line-height: 1.6;
  word-break: break-all;
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
