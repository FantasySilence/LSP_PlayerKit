<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'

import { invoke } from '../../platform/bridge'
import { t } from '../../platform/i18n'
import { notify, notifyError } from '../../platform/toast'
import type { PackingEntry, PackingGroup, PackingResult } from '../../platform/types'
import PackEntry from './PackEntry.vue'

const props = defineProps<{ result: PackingResult }>()
const emit = defineEmits<{ (e: 'close'): void }>()

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

const listMode = ref(groups.value.length > 12)
const active = ref(0)
const current = computed(() => groups.value[active.value] ?? groups.value[0])

// ------ 拼图式排布：细网格 + 按实测高度跨行 ------ #
const grid = ref<HTMLElement | null>(null)
const ROW_UNIT = 4
let frame = 0
let lastWidth = 0

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

function scheduleLayout(): void {
  window.cancelAnimationFrame(frame)
  frame = window.requestAnimationFrame(() => {
    frame = 0
    layoutCards()
  })
}

function onResize(): void {
  const element = grid.value
  if (!element || element.clientWidth === lastWidth) return
  scheduleLayout()
}

watch(listMode, () => nextTick(scheduleLayout))
watch(() => props.result, () => nextTick(scheduleLayout))

function groupLabel(group: PackingGroup): string {
  return group.merged
    ? t('material.pack.boxRange', { from: group.from, to: group.to })
    : t('material.pack.box', { n: group.from })
}

function groupMeta(group: PackingGroup): string {
  return group.merged
    ? `${group.boxes} × ${group.capacity}/${group.capacity}`
    : `${group.used}/${group.capacity}`
}

function groupSlots(group: PackingGroup): number {
  return group.capacity * group.boxes
}

function entryText(entry: PackingEntry): string {
  if (entry.stacks && entry.items) {
    return t('material.pack.mixed', { stacks: entry.stacks, items: entry.items })
  }
  if (entry.stacks) return t('material.pack.stacks', { n: entry.stacks })
  return t('material.pack.items', { n: entry.items })
}

function percent(used: number, capacity: number): string {
  return `${Math.min(100, Math.round((used / Math.max(1, capacity)) * 100))}%`
}

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

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    event.stopPropagation()
    emit('close')
  }
}

onMounted(() => {
  window.addEventListener('keydown', onKeydown)
  window.addEventListener('resize', onResize)
  nextTick(() => scheduleLayout())
})

onUnmounted(() => {
  window.removeEventListener('keydown', onKeydown)
  window.removeEventListener('resize', onResize)
  window.cancelAnimationFrame(frame)
})
</script>

<template>
  <div class="packing-backdrop" @click.self="emit('close')">
    <div class="packing" role="dialog" aria-modal="true">
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

      <div class="packing-hint">{{ t('material.pack.hint') }}</div>

      <div v-if="!listMode" ref="grid" class="packing-grid">
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
          <div class="box-bar">
            <span :style="{ width: percent(group.used, groupSlots(group)) }" />
          </div>
          <div class="box-list">
            <PackEntry v-for="entry in group.entries" :key="entry.name" :entry="entry" />
          </div>
          <div v-if="group.merged" class="box-merge-tag">
            {{ t('material.pack.mergedTag', { n: group.boxes }) }}
          </div>
          <div v-else-if="group.entries.length > 7" class="box-more">
            <span>▾</span>
            <span>{{ t('material.pack.scrollHint') }}</span>
          </div>
        </article>
      </div>

      <div v-else class="packing-split">
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

      <footer class="packing-foot">
        <span class="muted packing-tip">{{ t('material.pack.tip') }}</span>
        <button class="btn" @click="copyPlan">{{ t('material.pack.copy') }}</button>
        <button class="btn primary" @click="emit('close')">{{ t('action.close') }}</button>
      </footer>
    </div>
  </div>
</template>

<style scoped>
.packing-backdrop {
  position: fixed;
  inset: 0;
  z-index: 90;
  display: grid;
  place-items: center;
  padding: 24px;
  background: var(--scrim);
}

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

.packing-split {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 200px minmax(0, 1fr);
  border-top: 1px solid var(--line);
}

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
