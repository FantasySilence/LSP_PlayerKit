<!--
  站点选择器（自绘下拉）：先选分组 tag，再选该分组下的站点。

  为什么不用原生 select：站点按「分组 · 地名」两级组织，分组只是筛选维度，
  原生的 option group 无法把「分组」当成可点的胶囊；这里用按钮 + 绝对定位面板自绘。

  交互约定：
  - 展开时自动定位到当前已选站点所在分组；
  - 点面板外部或按 Esc 收起；点另一个选择器会先被 document 上的 mousedown 收起，
    因此页面上两个选择器天然互斥，同一时刻只展开一个；
  - 选中即 emit update:modelValue，由父组件（View.vue）决定绑定哪个字段。
-->
<script setup lang="ts">
// ------------------------------ 依赖 ------------------------------ #
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'

import { t } from '../../platform/i18n'
import type { Station } from './types'

// ------------------------------ props / emits ------------------------------ #
// modelValue：当前选中站点的 id；stations：整张站点表，分组与选项都从它派生。
const props = defineProps<{ modelValue: string; stations: Station[] }>()
const emit = defineEmits<{ (e: 'update:modelValue', value: string): void }>()

// ------------------------------ 状态 ------------------------------ #
// 组件根节点：判断点击是否落在面板内部，作为收起的依据。
const root = ref<HTMLElement | null>(null)
// 面板是否展开；页面上同一时刻只会有一个选择器处于展开状态。
const open = ref(false)
// 当前筛选的分组 tag；空串是合法值，代表「未分组」。
const activeGroup = ref('')

// ------------------------------ 计算属性 ------------------------------ #
// 已选站点的对象；id 为空或指向已删除的站点时为 null。
const selected = computed(
  () => props.stations.find((station) => station.id === props.modelValue) ?? null,
)

// 站点表里出现过的分组，按出现顺序去重；空串同样保留，后面显示成「未分组」。
const groups = computed(() => {
  const result: string[] = []
  for (const station of props.stations) {
    const group = station.group ?? ''
    if (!result.includes(group)) result.push(group)
  }
  return result
})

// 当前分组下的站点；两级结构里「分组」只是筛选条件，不参与搜索。
const filtered = computed(() =>
  props.stations.filter((station) => (station.group ?? '') === activeGroup.value),
)

// ------------------------------ 事件 ------------------------------ #
// 空分组在界面上显示成「未分组」，避免出现空白胶囊。
function groupLabel(group: string): string {
  return group || t('puppet.station.noGroup')
}

// 点击触发器：已展开就收起；首次展开先把分组定位到已选站点，减少翻找。
function toggle() {
  if (!open.value) {
    activeGroup.value = selected.value?.group ?? groups.value[0] ?? ''
    open.value = true
  } else {
    open.value = false
  }
}

// 选中站点：回写 v-model 并立即收起面板。
function pick(station: Station) {
  emit('update:modelValue', station.id)
  open.value = false
}

// 点面板外面收起：监听的是 document，所以要排除根节点内部的点击。
function onPointerDown(event: MouseEvent) {
  if (open.value && root.value && !root.value.contains(event.target as Node)) {
    open.value = false
  }
}

// Esc 收起面板，与其它弹层的关闭方式保持一致。
function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') open.value = false
}

// ------------------------------ 生命周期与副作用 ------------------------------ #
// 站点表变化（新增 / 删除 / 导入）后，若当前分组已不存在就回落到第一个分组。
watch(
  () => props.stations,
  () => {
    if (open.value && !groups.value.includes(activeGroup.value)) {
      activeGroup.value = groups.value[0] ?? ''
    }
  },
)

// 收起逻辑依赖 document 级监听：挂载时注册，卸载时必须移除，否则会泄漏。
onMounted(() => {
  document.addEventListener('mousedown', onPointerDown)
  document.addEventListener('keydown', onKeydown)
})

onUnmounted(() => {
  document.removeEventListener('mousedown', onPointerDown)
  document.removeEventListener('keydown', onKeydown)
})
</script>

<!-- 区块：触发器（显示已选分组与站点名，占位文案走 i18n） -->
<template>
  <div ref="root" class="picker">
    <button type="button" class="input picker-trigger" @click="toggle">
      <span v-if="selected?.group" class="tag">{{ selected.group }}</span>
      <span class="value" :class="{ placeholder: !selected }">
        {{ selected?.name || t('puppet.station.pick') }}
      </span>
      <span class="caret">▾</span>
    </button>

    <!-- 区块：下拉面板（上排分组 tag，下排当前分组的站点） -->
    <div v-if="open" class="picker-panel">
      <!-- 区块：分组 tag 行（单选，点击即切换下方列表） -->
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

      <!-- 区块：站点列表（每行：地名 + 维度） -->
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
        <!-- 区块：空状态（该分组下没有站点） -->
        <div v-if="!filtered.length" class="option-empty">{{ t('puppet.empty.stations') }}</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* 区块：触发器与面板的定位基准（relative） */
.picker {
  position: relative;
}

/* 区块：触发器外观（撑满宽度、左对齐、可点） */
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

/* 区块：分组 tag 胶囊（品牌色底，单行） */
.tag {
  flex: none;
  padding: 1px 7px;
  border-radius: 999px;
  background: var(--brand-soft);
  color: var(--brand);
  font-size: 10px;
  line-height: 1.6;
}

/* 区块：下拉面板（绝对定位 + 最大高度，超出由列表滚动） */
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

/* 区块：分组 tag 行（自动换行） */
.tag-row {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  padding: 8px;
  border-bottom: 1px solid var(--line);
  background: var(--surface-2);
}

/* 区块：分组胶囊（默认透明，选中时描边并染色） */
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

/* 区块：站点选项列表（可滚动） */
.option-list {
  overflow-y: auto;
  padding: 4px;
}

/* 区块：单个站点选项（名称与维度两端对齐） */
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

/* 区块：空状态文字 */
.option-empty {
  padding: 10px;
  color: var(--muted);
  font-size: 11px;
}
</style>
