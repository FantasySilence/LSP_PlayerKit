<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'

import { t } from '../platform/i18n'
import type { ColumnDef } from '../platform/types'

const props = defineProps<{
  columns: ColumnDef[]
  rows: Record<string, any>[]
  selected: number | null
  sortable?: string[]
  defaultSort?: { key: string; dir: 'asc' | 'desc' }
  highlightIndex?: number | null
  emptyKey?: string
}>()

const emit = defineEmits<{
  (e: 'select', index: number): void
  (e: 'sort-change', payload: { key: string; dir: 'asc' | 'desc' }): void
}>()

const sortKey = ref<string | null>(props.defaultSort?.key ?? null)
const sortDir = ref<'asc' | 'desc'>(props.defaultSort?.dir ?? 'asc')

const items = computed(() => {
  const list = props.rows.map((row, index) => ({ row, index }))
  const key = sortKey.value
  if (!key) return list

  const sign = sortDir.value === 'asc' ? 1 : -1
  return list.sort((a, b) => {
    const left = a.row[key]
    const right = b.row[key]
    if (typeof left === 'number' && typeof right === 'number') {
      return (left - right) * sign
    }
    return String(left ?? '').localeCompare(String(right ?? '')) * sign
  })
})

function canSort(column: ColumnDef): boolean {
  return props.sortable?.includes(column.key) ?? false
}

const wrap = ref<HTMLDivElement | null>(null)

function scrollToHighlight(): void {
  if (props.highlightIndex === null || props.highlightIndex === undefined) return
  nextTick(() => {
    const row = wrap.value?.querySelector('tr.target') as HTMLElement | null
    row?.scrollIntoView({ block: 'center' })
  })
}

onMounted(scrollToHighlight)
watch(() => [props.highlightIndex, props.rows.length], scrollToHighlight)

function onHeader(column: ColumnDef): void {
  if (!canSort(column)) return
  if (sortKey.value === column.key) {
    sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortKey.value = column.key
    sortDir.value = 'asc'
  }
  emit('sort-change', { key: column.key, dir: sortDir.value })
}

function display(value: unknown, column: ColumnDef): string {
  if (value === null || value === undefined) return '—'
  if (column.type === 'float') {
    const digits = column.digits ?? 6
    return Number(value).toFixed(digits)
  }
  if (column.type === 'int') return String(Math.round(Number(value)))
  return String(value)
}
</script>

<template>
  <div ref="wrap" class="table-wrap">
    <table class="data-table">
      <thead>
        <tr>
          <th
            v-for="column in columns"
            :key="column.key"
            :class="{ num: column.type !== 'string', sortable: canSort(column) }"
            @click="onHeader(column)"
          >
            <span>{{ t(column.nameKey) }}</span>
            <span v-if="sortKey === column.key" class="sort-arrow">
              {{ sortDir === 'asc' ? '▲' : '▼' }}
            </span>
          </th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="item in items"
          :key="item.index"
          :class="{ active: selected === item.index, target: highlightIndex === item.index }"
          @click="emit('select', item.index)"
        >
          <td
            v-for="column in columns"
            :key="column.key"
            :class="{ num: column.type !== 'string', strong: selected === item.index }"
          >
            {{ display(item.row[column.key], column) }}
          </td>
        </tr>
      </tbody>
    </table>
    <div v-if="!rows.length" class="empty">{{ t(props.emptyKey ?? 'table.empty') }}</div>
  </div>
</template>

<style scoped>
.table-wrap {
  height: 100%;
  overflow: auto;
  position: relative;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.data-table th {
  position: sticky;
  top: 0;
  z-index: 1;
  padding: 8px 10px;
  background: var(--surface-2);
  border-bottom: 1px solid var(--line-strong);
  color: var(--muted);
  font-weight: 500;
  text-align: center;
  white-space: nowrap;
}

.data-table th.sortable {
  cursor: pointer;
  user-select: none;
}

.data-table th.sortable:hover {
  color: var(--text);
}

.sort-arrow {
  margin-left: 4px;
  color: var(--brand);
  font-size: 9px;
}

.data-table td {
  padding: 6px 10px;
  border-bottom: 1px solid var(--line);
  color: var(--text);
  text-align: center;
}

.data-table tbody tr {
  cursor: pointer;
}

.data-table tbody tr:hover {
  background: var(--surface-2);
}

.data-table tbody tr.active {
  background: var(--brand-soft);
}

.data-table tbody tr.active td:first-child {
  box-shadow: inset 2px 0 0 var(--brand);
}

.data-table tbody tr.target {
  background: var(--accent-soft);
}

.data-table tbody tr.target td {
  color: var(--text);
  font-weight: 600;
}

.data-table tbody tr.target td:first-child {
  box-shadow: inset 2px 0 0 var(--accent);
}

.num {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
}

.strong {
  color: var(--brand);
}

.empty {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--muted);
}
</style>
