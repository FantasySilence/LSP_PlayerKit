<script setup lang="ts">
import { t } from '../../platform/i18n'
import type { PackingEntry } from '../../platform/types'

// 单条装填明细：材料名、整组数量、零散数量与占用槽位
const props = defineProps<{ entry: PackingEntry }>()

// 数量文案：整组与零散兼有时显示「a 组 + b 个」
function entryText(entry: PackingEntry): string {
  if (entry.stacks && entry.items) {
    return t('material.pack.mixed', { stacks: entry.stacks, items: entry.items })
  }
  if (entry.stacks) return t('material.pack.stacks', { n: entry.stacks })
  return t('material.pack.items', { n: entry.items })
}
</script>

<template>
  <!-- 区块：单条装填明细（材料名 / 数量文案 / 槽位数） -->
  <div class="pack-entry">
    <span class="entry-name" :title="props.entry.name">{{ props.entry.name }}</span>
    <span class="entry-qty mono">{{ entryText(props.entry) }}</span>
    <span class="entry-slots mono">{{ t('material.pack.slots', { n: props.entry.slots }) }}</span>
  </div>
</template>

<style scoped>
/* 区块：单条装填明细 */
.pack-entry {
  display: flex;
  align-items: baseline;
  gap: 6px;
  min-width: 0;
}

/* 材料名最多两行，超出省略 */
.entry-name {
  flex: 1;
  min-width: 0;
  font-size: 12px;
  line-height: 1.3;
  white-space: normal;
  overflow-wrap: break-word;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.entry-qty {
  flex: 0 0 auto;
  color: var(--text);
  font-size: 11px;
  white-space: nowrap;
}

.entry-slots {
  flex: 0 0 auto;
  color: var(--muted);
  font-size: 10px;
  white-space: nowrap;
}

/* 槽位数前的间隔点 */
.entry-slots::before {
  content: '·';
  margin-right: 4px;
  color: var(--line-strong);
}
</style>
