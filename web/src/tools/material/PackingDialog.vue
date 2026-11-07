<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'

import { invoke } from '../../platform/bridge'
import { t } from '../../platform/i18n'
import { notify, notifyError } from '../../platform/toast'
import type { PackingEntry, PackingGroup, PackingResult } from '../../platform/types'
import PackEntry from './PackEntry.vue'

const props = defineProps<{ result: PackingResult }>()
const emit = defineEmits<{ (e: 'close'): void }>()

// 盒组数据：后端已把连续满装且只放单一材料的盒子合并成一组；
// 旧数据没有 groups 时按单盒补齐
const groups = computed<PackingGroup[]>(() => {
  if (props.result.groups?.length) return props.result.groups
  return props.result.boxes.map((box) => ({
    from: box.index,
    to: box.index,
    boxes: 1,
    capacity: box.capacity,
    used: box.used,
    entries: box.entries,
    merged: false,
  }))
})

// 视图模式：盒数多于 12 时默认用列表视图，否则用卡片视图
const listMode = ref(groups.value.length > 12)
const active = ref(0)
// 列表视图当前选中的盒组
const current = computed(() => groups.value[active.value] ?? groups.value[0])

// ------ 拼图式排布：细网格 + 按实测高度跨行 ------ #
// 卡片视图容器；ROW_UNIT 为网格行高，lastWidth 记录上次宽度用于跳过无意义重排
const grid = ref<HTMLElement | null>(null)
const ROW_UNIT = 4
let frame = 0
let lastWidth = 0

// 逐卡测量高度并换算成跨行数：先复位跨行再测量，避免上一次结果影响这次
function layoutCards(): void {
  const element = grid.value
  if (!element || listMode.value) return

  const styles = window.getComputedStyle(element)
  const gap = Number.parseFloat(styles.rowGap || styles.gap || "10") || 10

  element.querySelectorAll<HTMLElement>(".box-card").forEach((card) => {
    card.style.gridRowEnd = "auto"
    const height = card.getBoundingClientRect().height
    const span = Math.max(1, Math.ceil((height + gap) / (ROW_UNIT + gap)))
    card.style.gridRowEnd = `span ${span}`
  })

  lastWidth = element.clientWidth
}

// 用 requestAnimationFrame 合并多次重排请求，避免同一帧里反复测量
function scheduleLayout(): void {
  window.cancelAnimationFrame(frame)
  frame = window.requestAnimationFrame(() => {
    frame = 0
    layoutCards()
  })
}

// 只有宽度变化才重排（高度变化不影响跨行数）
function onResize(): void {
  const element = grid.value
  if (!element || element.clientWidth === lastWidth) return
  scheduleLayout()
}

// 视图切换或结果变化后，等 DOM 更新完再重排
watch(listMode, () => nextTick(scheduleLayout))
watch(() => props.result, () => nextTick(scheduleLayout))

// 盒号文案：合并组显示盒号区间，单盒显示盒号
function groupLabel(group: PackingGroup): string {
  return group.merged
    ? t('material.pack.boxRange', { from: group.from, to: group.to })
    : t('material.pack.box', { n: group.from })
}

// 用量文案：合并组显示 组数 × 每盒容量，单盒显示 已用 / 容量
function groupMeta(group: PackingGroup): string {
  return group.merged
    ? `${group.boxes} × ${group.capacity}/${group.capacity}`
    : `${group.used}/${group.capacity}`
}

// 整组的总槽位数（合并组要乘盒数）
function groupSlots(group: PackingGroup): number {
  return group.capacity * group.boxes
}

// 单条装填数量文案：整组与零散兼有 / 只有整组 / 只有零散
function entryText(entry: PackingEntry): string {
  if (entry.stacks && entry.items) {
    return t('material.pack.mixed', { stacks: entry.stacks, items: entry.items })
  }
  if (entry.stacks) return t('material.pack.stacks', { n: entry.stacks })
  return t('material.pack.items', { n: entry.items })
}

// 进度条百分比，超过容量按 100% 截断
function percent(used: number, capacity: number): string {
  return `${Math.min(100, Math.round((used / Math.max(1, capacity)) * 100))}%`
}

// 生成可复制的纯文本方案：一行汇总 + 每盒（组）的明细
function planText(): string {
  const totals = props.result.totals
  const lines = [
    t('material.pack.summary', {
      boxes: totals.boxes,
      slots: totals.slots,
      capacity: totals.capacity,
    }),
  ]
  for (const group of groups.value) {
    lines.push('')
    lines.push(`${groupLabel(group)} (${groupMeta(group)})`)
    for (const entry of group.entries) {
      lines.push(
        `  - ${entry.name}: ${entryText(entry)} (${t('material.pack.slots', { n: entry.slots })})`,
      )
    }
  }
  return lines.join('\n')
}

// 复制方案文本：优先浏览器剪贴板，失败时退回后端接口
async function copyPlan() {
  const text = planText()
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
    } else {
      await invoke('clipboard_write', text)
    }
    notify('success', t('material.pack.copied'))
  } catch (error) {
    try {
      await invoke('clipboard_write', text)
      notify('success', t('material.pack.copied'))
    } catch (fallbackError) {
      notifyError(fallbackError)
    }
  }
}

// Esc 关闭弹窗
function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    event.stopPropagation()
    emit('close')
  }
}

// 挂载后首次排布，并监听窗口缩放
onMounted(() => {
  window.addEventListener('keydown', onKeydown)
  window.addEventListener('resize', onResize)
  nextTick(() => scheduleLayout())
})

// 卸载时移除监听并取消待执行的重排
onUnmounted(() => {
  window.removeEventListener('keydown', onKeydown)
  window.removeEventListener('resize', onResize)
  window.cancelAnimationFrame(frame)
})
</script>

<template>
  <!-- 区块：装填方案弹窗（点击遮罩或按 Esc 关闭） -->
  <div class="packing-backdrop" @click.self="emit('close')">
    <div class="packing" role="dialog" aria-modal="true">
      <!-- 标题、汇总与卡片 / 列表视图切换 -->
      <header class="packing-head">
        <div class="packing-titles">
          <div class="packing-title">{{ t('material.pack.title') }}</div>
          <div class="packing-summary">
            {{ t('material.pack.summary', {
              boxes: result.totals.boxes,
              slots: result.totals.slots,
              capacity: result.totals.capacity,
            }) }}
          </div>
        </div>
        <div class="packing-tools">
          <div class="view-switch">
            <button :class="{ active: !listMode }" @click="listMode = false">
              {{ t('material.pack.cards') }}
            </button>
            <button :class="{ active: listMode }" @click="listMode = true">
              {{ t('material.pack.list') }}
            </button>
          </div>
          <button class="btn ghost sm" :title="t('action.close')" @click="emit('close')">✕</button>
        </div>
      </header>

      <!-- 操作提示 -->
      <div class="packing-hint">{{ t('material.pack.hint') }}</div>

      <!-- 卡片视图：一盒一张卡片，合并组显示盒号区间 -->
      <div v-if="!listMode" ref="grid" class="packing-grid">
        <!-- 单盒卡片：盒号、用量、进度条与装填明细 -->
        <article
          v-for="group in groups"
          :key="`${group.from}-${group.to}`"
          class="box-card"
          :class="{ full: group.used >= groupSlots(group), merged: group.merged }"
        >
          <div class="box-head">
            <span class="box-no">{{ groupLabel(group) }}</span>
            <span class="box-meta">
              <span class="mono">{{ groupMeta(group) }}</span>
              <span class="box-kinds">· {{ group.entries.length }} {{ t('material.unit.kinds') }}</span>
            </span>
          </div>
          <!-- 装填进度条：满盒用品牌色，未满用强调色 -->
          <div class="box-bar">
            <span :style="{ width: percent(group.used, groupSlots(group)) }" />
          </div>
          <div class="box-list">
            <PackEntry v-for="entry in group.entries" :key="entry.name" :entry="entry" />
          </div>
          <!-- 合并组标记：显示该组合并了多少盒 -->
          <div v-if="group.merged" class="box-merge-tag">
            {{ t('material.pack.mergedTag', { n: group.boxes }) }}
          </div>
          <!-- 明细超过 7 条时提示可滚动 -->
          <div v-else-if="group.entries.length > 7" class="box-more">
            <span>▾</span>
            <span>{{ t('material.pack.scrollHint') }}</span>
          </div>
        </article>
      </div>

      <!-- 列表视图：左侧盒号索引 + 右侧明细 -->
      <div v-else class="packing-split">
        <!-- 盒号索引：点击切换右侧明细 -->
        <div class="box-index">
          <button
            v-for="(group, index) in groups"
            :key="`${group.from}-${group.to}`"
            class="box-index-item"
            :class="{ active: index === active, merged: group.merged }"
            @click="active = index"
          >
            <span class="box-index-no">{{ groupLabel(group) }}</span>
            <span class="box-index-meta mono">{{ groupMeta(group) }}</span>
          </button>
        </div>
        <!-- 选中盒组的明细 -->
        <div class="box-detail">
          <div class="detail-head">
            <span class="box-no">{{ groupLabel(current) }}</span>
            <span class="box-meta">
              <span class="mono">{{ groupMeta(current) }}</span>
              <span class="box-kinds">· {{ current.entries.length }} {{ t('material.unit.kinds') }}</span>
            </span>
          </div>
          <div class="detail-list">
            <PackEntry v-for="entry in current.entries" :key="entry.name" :entry="entry" />
          </div>
        </div>
      </div>

      <!-- 底部提示与复制 / 关闭 -->
      <footer class="packing-foot">
        <span class="muted packing-tip">{{ t('material.pack.tip') }}</span>
        <button class="btn" @click="copyPlan">{{ t('material.pack.copy') }}</button>
        <button class="btn primary" @click="emit('close')">{{ t('action.close') }}</button>
      </footer>
    </div>
  </div>
</template>

<style scoped>
/* 区块：全屏遮罩 */
.packing-backdrop {
  position: fixed;
  inset: 0;
  z-index: 90;
  display: grid;
  place-items: center;
  padding: 24px;
  background: var(--scrim);
}

/* 弹窗容器 */
.packing {
  width: min(1120px, 94vw);
  max-height: 92vh;
  display: flex;
  flex-direction: column;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 14px;
  box-shadow: var(--shadow);
  overflow: hidden;
}

/* 区块：标题栏 */
.packing-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 18px 8px;
}

.packing-titles {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.packing-title {
  font-size: 15px;
  font-weight: 600;
}

.packing-summary {
  color: var(--brand);
  font-size: 12px;
  font-family: var(--font-mono);
}

.packing-hint {
  padding: 0 18px 8px;
  color: var(--muted);
  font-size: 11px;
}

/* 区块：卡片视图网格（4px 细行，卡片按实测高度跨行） */
.packing-grid {
  flex: 0 1 auto;
  min-height: 0;
  overflow: auto;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  grid-auto-rows: 4px;
  align-items: start;
  align-content: start;
  row-gap: 10px;
  column-gap: 10px;
  padding: 0 18px 14px;
}

/* 单盒卡片 */
.box-card {
  display: flex;
  flex-direction: column;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: var(--surface-2);
  overflow: hidden;
}

.box-card.full {
  border-color: rgba(62, 224, 196, 0.3);
}

.box-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 10px 0;
}

.box-no {
  color: var(--brand);
  font-size: 12px;
  font-weight: 600;
}

.box-slots {
  color: var(--muted);
  font-size: 11px;
}

/* 装填进度条 */
.box-bar {
  height: 3px;
  margin: 6px 10px 8px;
  border-radius: 999px;
  background: var(--line);
  overflow: hidden;
}

.box-bar span {
  display: block;
  height: 100%;
  background: var(--brand);
}

.box-card:not(.full) .box-bar span {
  background: var(--accent);
}

.box-card.merged {
  border-color: var(--brand-dim);
}

.box-merge-tag {
  margin: 0 10px 8px;
  padding: 2px 8px;
  border-radius: 999px;
  background: var(--brand-soft);
  color: var(--brand);
  font-size: 10px;
  text-align: center;
}

.box-meta {
  display: inline-flex;
  align-items: baseline;
  gap: 4px;
  color: var(--muted);
  font-size: 11px;
}

.box-kinds {
  font-size: 10px;
}

.box-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 170px;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: 0 10px 10px;
}

.box-list::-webkit-scrollbar {
  width: 8px;
}

.box-list::-webkit-scrollbar-track {
  border-radius: 999px;
  background: var(--surface-3);
}

.box-list::-webkit-scrollbar-thumb {
  border: none;
  border-radius: 999px;
  background: var(--brand-dim);
}

.box-more {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 3px;
  margin: 0 10px 8px;
  padding-top: 4px;
  border-top: 1px dashed var(--line);
  color: var(--brand);
  font-size: 10px;
}

.box-entry {
  display: flex;
  align-items: baseline;
  gap: 6px;
  min-width: 0;
}

/* 视图切换与关闭按钮 */
.packing-tools {
  display: flex;
  align-items: center;
  gap: 10px;
}

.view-switch {
  display: inline-flex;
  gap: 2px;
  padding: 2px;
  border-radius: 6px;
  background: var(--surface-2);
}

.view-switch button {
  height: 22px;
  padding: 0 10px;
  border: none;
  border-radius: 4px;
  background: transparent;
  color: var(--muted);
  font-size: 11px;
  cursor: pointer;
}

.view-switch button.active {
  background: var(--surface-3);
  color: var(--brand);
}

/* 区块：列表视图（左侧索引 + 右侧明细） */
.packing-split {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 200px minmax(0, 1fr);
  border-top: 1px solid var(--line);
}

/* 盒号索引 */
.box-index {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  overscroll-behavior: contain;
  padding: 8px;
  border-right: 1px solid var(--line);
  background: var(--surface-2);
}

.box-index::-webkit-scrollbar,
.detail-list::-webkit-scrollbar,
.packing-grid::-webkit-scrollbar {
  width: 8px;
}

.box-index::-webkit-scrollbar-thumb,
.detail-list::-webkit-scrollbar-thumb,
.packing-grid::-webkit-scrollbar-thumb {
  border: none;
  border-radius: 999px;
  background: var(--brand-dim);
}

.box-index::-webkit-scrollbar-track,
.detail-list::-webkit-scrollbar-track,
.packing-grid::-webkit-scrollbar-track {
  border-radius: 999px;
  background: var(--surface-3);
}

.box-index-item {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  padding: 6px 8px;
  border: 1px solid transparent;
  border-radius: 6px;
  background: transparent;
  color: var(--muted);
  font-size: 11px;
  text-align: left;
  cursor: pointer;
}

.box-index-item:hover {
  background: var(--surface-3);
  color: var(--text);
}

.box-index-item.active {
  background: var(--brand-soft);
  border-color: rgba(62, 224, 196, 0.35);
  color: var(--brand);
}

.box-index-meta {
  font-size: 10px;
  color: var(--muted);
}

/* 选中盒组的明细 */
.box-detail {
  display: flex;
  flex-direction: column;
  min-height: 0;
  padding: 10px 18px 14px;
}

.detail-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--line);
}

.detail-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  overscroll-behavior: contain;
  display: flex;
  flex-direction: column;
  gap: 5px;
  padding-top: 8px;
}

/* 区块：底部操作栏 */
.packing-foot {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 18px;
  border-top: 1px solid var(--line);
  background: var(--surface-2);
}

.packing-tip {
  flex: 1;
  font-size: 11px;
}
</style>
