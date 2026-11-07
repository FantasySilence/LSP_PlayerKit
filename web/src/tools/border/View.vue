<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { callTool, invoke } from '../../platform/bridge'
import { t } from '../../platform/i18n'
import { clone, getSettings, loadSettings, saveSettings } from '../../platform/settings'
import { notify, notifyError } from '../../platform/toast'
import type { BorderRow, ToolDef } from '../../platform/types'
import DataTable from '../../ui/DataTable.vue'

const props = defineProps<{ tool: ToolDef }>()

// 炮口坐标：X / Y / Z 三个分量
const originX = ref<number | string>(9996.24)
const originY = ref<number | string>(256)
const originZ = ref<number | string>(9999.24)
const targetX = ref<number | string>(0)
const targetY = ref<number | string>(128)
const targetZ = ref<number | string>(0)
// 预计飞行时间（gt），参与三元求解
const flightTime = ref<number | string>(1200)
// 方向判定基准：origin 真实炮口 / fixed 兼容旧版固定炮口（10000, 10000）
// 该值由设置决定，本页只在标题上展示
const directionMode = ref('origin')

// 三元求解得到的结果行（每行是一组 TNT 数量）与当前选中行
const rows = ref<BorderRow[]>([])
const selected = ref<number | null>(null)
const busy = ref(false)

// 解码 / 预报的返回结构：valid 为 false 时只有 reason；
// small / big 是三个 TNT 的小头与大头配置文本
interface DecodeResult {
  valid: boolean
  reason?: string
  small?: Record<string, string>
  big?: Record<string, string>
  landing?: { x: number; z: number; ticks: number }
  text?: string
  tnt?: number[]
  motion?: { x: number; y: number; z: number }
  time?: number
  atTime?: { tick: number; x: number; y: number; z: number } | null
  landedBefore?: boolean
}

// 解码结果；decodedSource 区分来源：row 选中行解码 / manual 手动落点预报
const decoded = ref<DecodeResult | null>(null)
const decodedSource = ref<'row' | 'manual'>('row')
// 当前选中行；解码面板里动量缺失时用它兜底
const current = computed(() => (selected.value === null ? null : rows.value[selected.value] ?? null))

// ------ 手动落点预报：三个 TNT + 手选方向 + 飞行时间，不需要先算结果 ------
// 手动预报可选的方向编码（八方），与后端方向表一一对应
const DIR_CODES = ['000', '100', '101', '111', '110', '010', '011', '001']
// 手动预报的三元 TNT 数量，以及手选的方向编码与飞行时间
const manualTnt = ref<[number | string, number | string, number | string]>([0, 0, 0])
const manualDir = ref('000')
const manualTime = ref<number | string>(400)

// 结果行补充一列可读的方向文本，列定义仍由后端提供
const tableRows = computed(() =>
  rows.value.map((row) => ({ ...row, dirText: t(`border.dir.${row.dirCode}`) })),
)

// 有效行数：三项 TNT 都不为负才算能生成阵列
const validCount = computed(
  () => rows.value.filter((row) => Math.min(row.t1, row.t2, row.t3) >= 0).length,
)

// 输入可能是空串或非数字，统一校验后返回数字
function toNumber(value: number | string, label: string): number {
  const parsed = Number(value)
  if (!Number.isFinite(parsed) || String(value).trim() === '') {
    throw new Error(`${label} 不是有效数字`)
  }
  return parsed
}

// 读取默认设置回填输入框；手动预报的飞行时间跟随默认飞行时间
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
  manualTime.value = data.flightTime
}

// 保存为默认：clone 已保存的设置，只覆盖本页字段，其余设置保持原值
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

// 计算：后端按炮口 / 目的地 / 飞行时间做三元求解，返回候选结果行
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
    // 自动选中第一条有效行；全部无效时退回第一行
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

// 选中行：用该行的 TNT 数量、动量与方向请求解码，来源记为 row
async function selectRow(index: number) {
  selected.value = index
  const row = rows.value[index]
  if (!row) return
  decodedSource.value = 'row'
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

// 落点预报：手填三个 TNT + 手选方向，直接算动量与落点；来源记为 manual 并清空选中
async function forecast() {
  busy.value = true
  try {
    const result = await callTool<DecodeResult>(props.tool.id, 'forecast', {
      tnt: manualTnt.value.map((value, index) => toNumber(value, `第 ${index + 1} 个 TNT`)),
      dirCode: manualDir.value,
      time: Math.max(0, Math.trunc(toNumber(manualTime.value, '预计飞行时间'))),
      origin: {
        x: toNumber(originX.value, '炮口 X'),
        y: toNumber(originY.value, '炮口 Y'),
        z: toNumber(originZ.value, '炮口 Z'),
      },
    })
    decoded.value = result
    decodedSource.value = 'manual'
    selected.value = null
  } catch (error) {
    notifyError(error)
  } finally {
    busy.value = false
  }
}

// 复制解码文本：优先浏览器剪贴板，失败时退回后端接口
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
    <!-- 区块：输入参数（炮口 / 目的地 / 飞行时间） -->
    <section class="panel">
      <div class="panel-head">
        <span>{{ t('border.panel.input') }}</span>
        <span class="badge" :title="t('border.msg.directionModeHint')">
          {{ directionMode === 'origin' ? t('border.option.directionOrigin') : t('border.option.directionFixed') }}
        </span>
      </div>
      <div class="panel-body">
        <!-- 炮口坐标卡片 -->
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

        <!-- 目的地坐标卡片 -->
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

        <!-- 预计飞行时间（gt） -->
        <div class="field">
          <label class="field-label">
            <span>{{ t('border.field.flightTime') }}</span>
            <span class="unit">gt</span>
          </label>
          <input v-model.number="flightTime" class="input mono" type="number" min="1" step="10" />
        </div>

        <!-- 手动落点预报：三项 TNT + 方向编码 + 飞行时间 -->
        <div class="coord-block manual">
          <div class="coord-head">
            <span class="marker" />
            <span class="coord-title">{{ t('border.manual.title') }}</span>
            <span class="coord-tag">{{ t('border.manual.tag') }}</span>
          </div>
          <div class="coords">
            <label class="coord">
              <span class="axis">1</span>
              <input
                v-model.number="manualTnt[0]"
                class="input mono"
                type="number"
                min="0"
                step="1"
                :title="t('border.manual.tnt1')"
                :aria-label="t('border.manual.tnt1')"
              />
            </label>
            <label class="coord">
              <span class="axis">2</span>
              <input
                v-model.number="manualTnt[1]"
                class="input mono"
                type="number"
                min="0"
                step="1"
                :title="t('border.manual.tnt2')"
                :aria-label="t('border.manual.tnt2')"
              />
            </label>
            <label class="coord">
              <span class="axis">3</span>
              <input
                v-model.number="manualTnt[2]"
                class="input mono"
                type="number"
                min="0"
                step="1"
                :title="t('border.manual.tnt3')"
                :aria-label="t('border.manual.tnt3')"
              />
            </label>
          </div>
          <!-- 方向编码与飞行时间 -->
          <div class="field-row manual-row">
            <div class="field">
              <label class="field-label">{{ t('border.manual.direction') }}</label>
              <select v-model="manualDir" class="input">
                <option v-for="code in DIR_CODES" :key="code" :value="code">
                  {{ t(`border.dir.${code}`) }}
                </option>
              </select>
            </div>
            <div class="field">
              <label class="field-label">
                <span>{{ t('border.manual.flightTime') }}</span>
                <span class="unit">gt</span>
              </label>
              <input
                v-model.number="manualTime"
                class="input mono"
                type="number"
                min="0"
                step="10"
              />
            </div>
          </div>
          <!-- 直接预报落点，不需要先算出结果行 -->
          <button class="btn block" :disabled="busy" @click="forecast">
            {{ t('border.action.forecast') }}
          </button>
          <div class="manual-hint">{{ t('border.manual.hint') }}</div>
        </div>

        <!-- 计算三元求解 -->
        <div class="actions">
          <button class="btn primary" :disabled="busy" @click="calculate">
            {{ busy ? t('status.calculating') : t('border.action.calculate') }}
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

        <!-- 使用提示 -->
        <div class="tip muted">{{ t('border.panel.tip') }}</div>
      </div>
    </section>

    <!-- 区块：结果表与解码面板 -->
    <section class="panel">
      <div class="panel-head">
        <span>{{ t('border.panel.result') }}</span>
        <!-- 表头信息：全部行无效时的提醒 + 总行数 -->
        <span class="head-meta">
          <span v-if="rows.length && validCount === 0" class="badge warn">
            {{ t('border.msg.noValid') }}
          </span>
          <span class="muted">{{ rows.length }} {{ t('label.rows') }}</span>
        </span>
      </div>

      <div class="result-body">
        <!-- 三元求解结果表（列由后端定义），点击行触发解码 -->
        <DataTable
          :columns="tool.columns"
          :rows="tableRows"
          :selected="selected"
          @select="selectRow"
        />
      </div>

      <!-- 解码面板：无效时只显示原因，有效时显示落点与三元配置 -->
      <footer v-if="decoded" class="detail">
        <div v-if="!decoded.valid" class="invalid">
          <span class="badge warn">{{ t('border.decode.invalid') }}</span>
          <span class="muted">{{ decoded.reason }}</span>
          <span class="muted">{{ t('border.decode.invalidHint') }}</span>
        </div>

        <template v-else>
          <!-- 标题（来源不同文案不同）+ 预计落点 + 复制 -->
          <div class="detail-head">
            <span class="badge brand">
              {{ decodedSource === 'manual' ? t('border.manual.resultTitle') : t('border.decode.title') }}
            </span>
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

          <!-- 手动预报：显示手填飞行时间对应的珍珠位置 -->
          <div v-if="decodedSource === 'manual'" class="at-time mono">
            <template v-if="decoded.atTime">
              {{ t('border.manual.atTime', { time: decoded.time ?? 0 }) }}：X
              {{ decoded.atTime.x.toFixed(3) }} / Y {{ decoded.atTime.y.toFixed(3) }} / Z
              {{ decoded.atTime.z.toFixed(3) }}
            </template>
            <span v-else-if="decoded.landedBefore" class="muted">
              {{ t('border.manual.atTimeLanded', { time: decoded.time ?? 0 }) }}
            </span>
          </div>

          <!-- 三个 TNT 各自的配置：小头（满当量蓄力后剩余的 TNT）与大头（按 780 满当量蓄力次数） -->
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

          <!-- 动量三元组：优先用解码结果，缺失时退回选中行 -->
          <div class="motion mono muted">
            {{ t('border.decode.motion') }}:
            {{ (decoded.motion?.x ?? current?.mx ?? 0).toFixed(6) }} /
            {{ (decoded.motion?.y ?? current?.my ?? 0).toFixed(6) }} /
            {{ (decoded.motion?.z ?? current?.mz ?? 0).toFixed(6) }}
          </div>
        </template>
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

/* 区块：坐标卡片（炮口 / 目的地 / 手动预报） */
.coord-block {
  margin-bottom: 12px;
  padding: 10px;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: var(--surface-2);
}

/* 目的地卡片用品牌色区分 */
.coord-block.target {
  border-color: rgba(62, 224, 196, 0.35);
  background: var(--brand-soft);
}

/* 手动预报卡片用虚线边框区分 */
.coord-block.manual {
  border-style: dashed;
}

.manual-dir {
  margin-top: 8px;
}

.manual-row {
  margin-top: 8px;
}

.at-time {
  margin: -2px 0 8px;
  padding: 6px 10px;
  border-radius: 8px;
  background: var(--brand-soft);
  color: var(--brand);
  font-size: 11px;
  word-break: break-all;
}

.coord-block.manual .btn.block {
  margin-top: 10px;
}

.manual-hint {
  margin-top: 8px;
  color: var(--muted);
  font-size: 11px;
  line-height: 1.6;
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

/* 三个轴的坐标输入排成一行 */
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

/* 区块：按钮组 */
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

/* 使用提示 */
.tip {
  margin-top: 14px;
  font-size: 11px;
  line-height: 1.7;
}

/* 区块：结果表容器 */
.result-body {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

/* 表头信息：无效行提醒与行数 */
.head-meta {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* 区块：解码面板（可滚动，最多占结果区 42% 高度） */
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

/* 三个 TNT 的配置卡片 */
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

/* 无效配置提示 */
.invalid {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}
</style>
