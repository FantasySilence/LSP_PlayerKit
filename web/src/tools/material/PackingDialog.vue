<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'

import { invoke } from '../../platform/bridge'
import { t } from '../../platform/i18n'
import { notify, notifyError } from '../../platform/toast'
import type { PackingEntry, PackingResult } from '../../platform/types'
import PackEntry from './PackEntry.vue'

const props = defineProps<{ result: PackingResult }>()
const emit = defineEmits<{ (e: 'close'): void }>()

const listMode = ref(props.result.boxes.length > 12)
const active = ref(0)
const current = computed(() => props.result.boxes[active.value] ?? props.result.boxes[0])

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
  for (const box of props.result.boxes) {
    lines.push('')
    lines.push(
      `${t('material.pack.box', { n: box.index })} (${box.used}/${box.capacity})`,
    )
    for (const entry of box.entries) {
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

onMounted(() => window.addEventListener('keydown', onKeydown))
onUnmounted(() => window.removeEventListener('keydown', onKeydown))
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

      <div v-if="!listMode" class="packing-grid">
        <article
          v-for="box in result.boxes"
          :key="box.index"
          class="box-card"
          :class="{ full: box.used >= box.capacity }"
        >
          <div class="box-head">
            <span class="box-no">{{ t('material.pack.box', { n: box.index }) }}</span>
            <span class="box-meta">
              <span class="mono">{{ box.used }}/{{ box.capacity }}</span>
              <span class="box-kinds">· {{ box.entries.length }} {{ t('material.unit.kinds') }}</span>
            </span>
          </div>
          <div class="box-bar">
            <span :style="{ width: percent(box.used, box.capacity) }" />
          </div>
          <div class="box-list">
            <PackEntry v-for="entry in box.entries" :key="entry.name" :entry="entry" />
          </div>
          <div v-if="box.entries.length > 7" class="box-more">
            <span>▾</span>
            <span>{{ t('material.pack.scrollHint') }}</span>
          </div>
        </article>
      </div>

      <div v-else class="packing-split">
        <div class="box-index">
          <button
            v-for="(box, index) in result.boxes"
            :key="box.index"
            class="box-index-item"
            :class="{ active: index === active }"
            @click="active = index"
          >
            <span class="box-index-no">{{ t('material.pack.box', { n: box.index }) }}</span>
            <span class="box-index-meta mono">{{ box.used }}/{{ box.capacity }}</span>
          </button>
        </div>
        <div class="box-detail">
          <div class="detail-head">
            <span class="box-no">{{ t('material.pack.box', { n: current.index }) }}</span>
            <span class="box-meta">
              <span class="mono">{{ current.used }}/{{ current.capacity }}</span>
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
  align-items: start;
  gap: 10px;
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
