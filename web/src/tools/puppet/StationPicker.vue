<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'

import { t } from '../../platform/i18n'
import type { Station } from './types'

const props = defineProps<{ modelValue: string; stations: Station[] }>()
const emit = defineEmits<{ (e: 'update:modelValue', value: string): void }>()

const root = ref<HTMLElement | null>(null)
const open = ref(false)
const activeGroup = ref('')

const selected = computed(
  () => props.stations.find((station) => station.id === props.modelValue) ?? null,
)

const groups = computed(() => {
  const result: string[] = []
  for (const station of props.stations) {
    const group = station.group ?? ''
    if (!result.includes(group)) result.push(group)
  }
  return result
})

const filtered = computed(() =>
  props.stations.filter((station) => (station.group ?? '') === activeGroup.value),
)

function groupLabel(group: string): string {
  return group || t('puppet.station.noGroup')
}

function toggle() {
  if (!open.value) {
    activeGroup.value = selected.value?.group ?? groups.value[0] ?? ''
    open.value = true
  } else {
    open.value = false
  }
}

function pick(station: Station) {
  emit('update:modelValue', station.id)
  open.value = false
}

function onPointerDown(event: MouseEvent) {
  if (open.value && root.value && !root.value.contains(event.target as Node)) {
    open.value = false
  }
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') open.value = false
}

watch(
  () => props.stations,
  () => {
    if (open.value && !groups.value.includes(activeGroup.value)) {
      activeGroup.value = groups.value[0] ?? ''
    }
  },
)

onMounted(() => {
  document.addEventListener('mousedown', onPointerDown)
  document.addEventListener('keydown', onKeydown)
})

onUnmounted(() => {
  document.removeEventListener('mousedown', onPointerDown)
  document.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <div ref="root" class="picker">
    <button type="button" class="input picker-trigger" @click="toggle">
      <span v-if="selected?.group" class="tag">{{ selected.group }}</span>
      <span class="value" :class="{ placeholder: !selected }">
        {{ selected?.name || t('puppet.station.pick') }}
      </span>
      <span class="caret">▾</span>
    </button>

    <div v-if="open" class="picker-panel">
      <div class="tag-row">
        <button
          v-for="group in groups"
          :key="group || '-none-'"
          type="button"
          class="group-chip"
          :class="{ active: group === activeGroup }"
          @click="activeGroup = group"
        >
          {{ groupLabel(group) }}
        </button>
      </div>

      <div class="option-list">
        <button
          v-for="station in filtered"
          :key="station.id"
          type="button"
          class="option-row"
          :class="{ selected: station.id === props.modelValue }"
          @click="pick(station)"
        >
          <span class="option-name">{{ station.name }}</span>
          <span class="option-dim">{{ t(`puppet.dim.${station.dimension}`) }}</span>
        </button>
        <div v-if="!filtered.length" class="option-empty">{{ t('puppet.empty.stations') }}</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.picker {
  position: relative;
}

.picker-trigger {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  text-align: left;
  cursor: pointer;
}

.picker-trigger .value {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.picker-trigger .value.placeholder {
  color: var(--muted);
}

.picker-trigger .caret {
  color: var(--muted);
  font-size: 10px;
}

.tag {
  flex: none;
  padding: 1px 7px;
  border-radius: 999px;
  background: var(--brand-soft);
  color: var(--brand);
  font-size: 10px;
  line-height: 1.6;
}

.picker-panel {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  right: 0;
  z-index: 30;
  max-height: 260px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid var(--line-strong);
  border-radius: var(--radius-sm);
  background: var(--surface);
  box-shadow: var(--shadow);
}

.tag-row {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  padding: 8px;
  border-bottom: 1px solid var(--line);
  background: var(--surface-2);
}

.group-chip {
  padding: 2px 8px;
  border: 1px solid transparent;
  border-radius: 999px;
  background: transparent;
  color: var(--muted);
  font-size: 11px;
  cursor: pointer;
}

.group-chip:hover {
  color: var(--text);
}

.group-chip.active {
  border-color: var(--brand-dim);
  background: var(--brand-soft);
  color: var(--brand);
}

.option-list {
  overflow-y: auto;
  padding: 4px;
}

.option-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  width: 100%;
  padding: 7px 10px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--text);
  font-size: 12px;
  text-align: left;
  cursor: pointer;
}

.option-row:hover {
  background: var(--surface-2);
}

.option-row.selected {
  background: var(--select-bg);
}

.option-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.option-dim {
  flex: none;
  color: var(--muted);
  font-size: 10px;
}

.option-empty {
  padding: 10px;
  color: var(--muted);
  font-size: 11px;
}
</style>
