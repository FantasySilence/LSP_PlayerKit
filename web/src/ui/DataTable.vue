<!--
  DataTable.vue —— 通用数据表格

  负责：按列定义渲染表格，支持：
  - 表头点击排序（只有 sortable 里列出的列可排；再次点击同列切换升/降序）；
  - 行选中（点击行 emit('select', 原始行下标)）；
  - 空态提示（没有数据时显示一句居中文字）；
  - 自动滚动到高亮行（用于“定位到某条结果”；scrollToTarget 为 false 时回到顶部）。

  交互关系：
  - 列定义来自 platform/types.ts 的 ColumnDef，通常由工具 manifest 的 columns 提供；
  - 文案通过 platform/i18n.ts 的 t() 读取；
  - 各工具 View.vue 传入 rows/selected/sortable 等 props，并监听 select/sort-change。
-->

<script setup lang="ts">
// nextTick 用于等列表渲染完再滚动；watch 用于高亮行或数据变化后重新定位
import { computed, nextTick, onMounted, ref, watch } from 'vue'

import { t } from '../platform/i18n'
import type { ColumnDef } from '../platform/types'

// ------ props / emits ------ //

const props = defineProps<{
  // 列定义：顺序即表头顺序
  columns: ColumnDef[]
  // 数据行；每行是“字段名 → 值”的映射
  rows: Record<string, any>[]
  // 当前选中行的原始下标；null 表示没有选中
  selected: number | null
  // 允许点击排序的列 key 列表；省略表示所有列都不可排序
  sortable?: string[]
  // 初始排序；省略则保持数据原顺序
  defaultSort?: { key: string; dir: 'asc' | 'desc' }
  // 需要高亮并滚动到的行下标；null/undefined 表示不高亮
  highlightIndex?: number | null
  // 空态文案的 i18n key；省略时用 table.empty
  emptyKey?: string
  /** 是否自动滚动到高亮行；false 时回到第一行（手动模拟用） */
  scrollToTarget?: boolean
}>()

const emit = defineEmits<{
  // 点击某一行：参数是原始数据下标（排序后仍对应 props.rows 的下标）
  (e: 'select', index: number): void
  // 排序变化：把当前排序列与方向告诉父组件
  (e: 'sort-change', payload: { key: string; dir: 'asc' | 'desc' }): void
}>()

// ------ 状态 ------ //

// 当前排序列；初始值来自 defaultSort
const sortKey = ref<string | null>(props.defaultSort?.key ?? null)
// 当前排序方向
const sortDir = ref<'asc' | 'desc'>(props.defaultSort?.dir ?? 'asc')

// ------ 计算属性：排序后的行 ------ //

/**
 * 把 props.rows 映射成 { row, index } 再排序：
 * 带上原始下标 index，排序后行点击仍能拿到正确的位置。
 * 值为数字时按数值比较，其他按字符串本地化比较；方向由 sortDir 决定正负。
 */
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

// 该列是否允许排序：由父组件通过 sortable 显式列出
function canSort(column: ColumnDef): boolean {
  return props.sortable?.includes(column.key) ?? false
}

// ------ 滚动定位 ------ //

// 表格外层容器，用来读取或设置滚动位置
const wrap = ref<HTMLDivElement | null>(null)

// 滚动到高亮行：nextTick 保证 DOM 已按最新数据渲染完成
function scrollToHighlight(): void {
  nextTick(() => {
    if (props.scrollToTarget === false) {
      // 手动模拟：列表从第一行开始看，落地行只做高亮
      if (wrap.value) wrap.value.scrollTop = 0
      return
    }
    if (props.highlightIndex === null || props.highlightIndex === undefined) return
    // 模板里高亮行带 .target 类，按类名找到它并滚到视口中间
    const row = wrap.value?.querySelector('tr.target') as HTMLElement | null
    row?.scrollIntoView({ block: 'center' })
  })
}

// 首次挂载与相关 props 变化（高亮行、行数、是否自动滚动）时都重新定位
onMounted(scrollToHighlight)
watch(
  () => [props.highlightIndex, props.rows.length, props.scrollToTarget],
  scrollToHighlight,
)

// ------ 事件处理 ------ //

// 点击表头：同一列再点切换方向，换列则从升序开始，并通知父组件
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

// 单元格显示：空值用破折号；float 按 digits 保留小数；int 四舍五入
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
  <!-- 区块：表格容器（自身滚动，空态提示绝对定位在其上） -->
  <div ref="wrap" class="table-wrap">
    <table class="data-table">
      <thead>
        <tr>
          <!-- 表头：可排序列显示 ▲/▼，点击列头调用 onHeader 切换排序 -->
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
        <!-- 区块：数据行（点击选中；选中用 active 类，高亮用 target 类） -->
        <tr
          v-for="item in items"
          :key="item.index"
          :class="{ active: selected === item.index, target: highlightIndex === item.index }"
          @click="emit('select', item.index)"
        >
          <!-- 单元格：数字列套用 num 类，使用等宽字体与等宽数字 -->
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
    <!-- 区块：空态（没有数据时覆盖在表格区域中央） -->
    <div v-if="!rows.length" class="empty">{{ t(props.emptyKey ?? 'table.empty') }}</div>
  </div>
</template>

<style scoped>
/* 区块：表格容器 */
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

/* 区块：表头（吸顶显示，滚动时保持可见） */
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

/* 可排序表头：手型光标 + 悬停变亮 */
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

/* 区块：单元格与行状态 */
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

/* 数字列：等宽字体 + 等宽数字，方便纵向对齐 */
.num {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
}

.strong {
  color: var(--brand);
}

/* 区块：空态 */
.empty {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--muted);
}
</style>
