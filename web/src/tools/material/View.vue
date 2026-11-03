<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

import { callTool, invoke } from '../../platform/bridge'
import { t } from '../../platform/i18n'
import { loadSettings, revision } from '../../platform/settings'
import { notify, notifyError } from '../../platform/toast'
import type { MaterialResult, MaterialRow, MaterialTotals, ToolDef } from '../../platform/types'
import DataTable from '../../ui/DataTable.vue'

const props = defineProps<{ tool: ToolDef }>()

const EXAMPLE = [
  'minecraft:white_wool 1728',
  'minecraft:oak_planks 512',
  'minecraft:redstone_block, 64',
  'minecraft:hopper 130',
].join('\n')

const text = ref('')
const rows = ref<MaterialRow[]>([])
const totals = ref<MaterialTotals | null>(null)
const warnings = ref<{ line: number; text: string }[]>([])
const skipped = ref(0)
const truncated = ref(false)
const perBox = ref(1728)
const busy = ref(false)

const hasInput = computed(() => text.value.trim().length > 0)
const currentWarnings = computed(() => warnings.value.slice(0, 3))

async function refreshPerBox() {
  const data = await loadSettings(props.tool.id)
  perBox.value = Number(data.stackSize) * Number(data.shulkerSlots)
}

async function convert() {
  if (!hasInput.value) {
    notify('info', t('material.msg.noInput'))
    return
  }
  busy.value = true
  try {
    const result = await callTool<MaterialResult>(props.tool.id, 'convert', {
      text: text.value,
    })
    rows.value = result.items
    totals.value = result.totals
    warnings.value = result.warnings
    skipped.value = result.skipped
    truncated.value = result.truncated
  } catch (error) {
    rows.value = []
    totals.value = null
    warnings.value = []
    notifyError(error)
  } finally {
    busy.value = false
  }
}

async function readFile() {
  try {
    const result = await invoke<{ cancelled?: boolean; name?: string; text?: string }>(
      'file_open_text',
    )
    if (result?.cancelled || typeof result?.text !== 'string') return
    text.value = result.text
    notify('success', t('material.msg.loaded', { name: result.name ?? '' }))
    await convert()
  } catch (error) {
    notifyError(error)
  }
}

async function loadExample() {
  text.value = EXAMPLE
  await convert()
}

function clearAll() {
  text.value = ''
  rows.value = []
  totals.value = null
  warnings.value = []
  skipped.value = 0
  truncated.value = false
}

function csvCell(value: unknown): string {
  const cell = String(value ?? '')
  return /[",\r\n]/.test(cell) ? `"${cell.replaceAll('"', '""')}"` : cell
}

async function exportCsv() {
  if (!rows.value.length || !totals.value) {
    notify('info', t('material.msg.exportEmpty'))
    return
  }
  const header = [
    t('material.col.name'),
    t('material.col.count'),
    t('material.col.shulkers'),
    t('material.col.stacks'),
    t('material.col.items'),
  ]
  const body = rows.value.map((row) => [
    row.name,
    row.count,
    row.shulkers,
    row.stacks,
    row.items,
  ])
  const total = [
    t('material.row.total'),
    totals.value.count,
    totals.value.shulkers,
    totals.value.stacks,
    totals.value.items,
  ]
  const csv = [header, ...body, total]
    .map((line) => line.map(csvCell).join(','))
    .join('\r\n')

  try {
    const result = await invoke<{ cancelled?: boolean }>('file_save_text', 'materials.csv', csv)
    if (result?.cancelled) return
    notify('success', t('material.msg.exported'))
  } catch (error) {
    notifyError(error)
  }
}

watch(
  () => revision[props.tool.id],
  () => {
    void refreshPerBox().catch(() => undefined)
  },
)

onMounted(async () => {
  try {
    await refreshPerBox()
  } catch (error) {
    notifyError(error)
  }
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
        <div class="field">
          <label class="field-label">
            <span>{{ t('material.field.list') }}</span>
            <span class="unit">{{ t('material.field.listHint') }}</span>
          </label>
          <textarea
            v-model="text"
            class="input mono textarea"
            spellcheck="false"
            :placeholder="t('material.field.placeholder')"
            @keydown.ctrl.enter.prevent="convert"
          />
        </div>

        <div class="source-actions">
          <button class="btn sm" @click="readFile">{{ t('material.action.openFile') }}</button>
          <button class="btn sm" @click="loadExample">{{ t('material.action.example') }}</button>
          <button class="btn sm" :disabled="!hasInput && !rows.length" @click="clearAll">
            {{ t('material.action.clear') }}
          </button>
        </div>

        <div class="actions">
          <button class="btn primary" :disabled="busy" @click="convert">
            {{ busy ? t('status.calculating') : t('material.action.convert') }}
          </button>
          <button class="btn" :disabled="!rows.length" @click="exportCsv">
            {{ t('material.action.export') }}
          </button>
        </div>

        <div class="tip muted">{{ t('material.panel.tip') }}</div>
      </div>
    </section>

    <section class="panel">
      <div class="panel-head">
        <span>{{ t('material.panel.result') }}</span>
        <span class="head-meta">
          <span v-if="truncated" class="badge warn">{{ t('material.msg.truncated') }}</span>
          <span v-if="totals" class="muted">
            {{ totals.kinds }} {{ t('material.unit.kinds') }} · {{ totals.count }}
            {{ t('material.unit.items') }}
          </span>
        </span>
      </div>

      <div class="result-body">
        <DataTable
          :columns="tool.columns"
          :rows="rows"
          :selected="null"
          empty-key="material.empty"
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

.textarea {
  height: 260px;
  min-height: 160px;
  padding: 10px;
  line-height: 1.7;
  resize: vertical;
}

.source-actions {
  display: flex;
  gap: 8px;
  margin: -4px 0 14px;
}

.source-actions .btn {
  flex: 1;
}

.actions {
  display: flex;
  gap: 8px;
  margin-top: 4px;
}

.actions .primary {
  flex: 1.4;
}

.actions .btn:not(.primary) {
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
