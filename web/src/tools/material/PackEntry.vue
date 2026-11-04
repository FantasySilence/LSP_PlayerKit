<script setup lang="ts">
import { t } from '../../platform/i18n'
import type { PackingEntry } from '../../platform/types'

const props = defineProps<{ entry: PackingEntry }>()

function entryText(entry: PackingEntry): string {
  if (entry.stacks && entry.items) {
    return t('material.pack.mixed', { stacks: entry.stacks, items: entry.items })
  }
  if (entry.stacks) return t('material.pack.stacks', { n: entry.stacks })
  return t('material.pack.items', { n: entry.items })
}
</script>

<template>
  <div class="pack-entry">
    <span class="entry-name" :title="props.entry.name">{{ props.entry.name }}</span>
    <span class="entry-qty mono">{{ entryText(props.entry) }}</span>
    <span class="entry-slots mono">{{ t('material.pack.slots', { n: props.entry.slots }) }}</span>
  </div>
</template>

<style scoped>
.pack-entry {
  display: flex;
  align-items: baseline;
  gap: 6px;
  min-width: 0;
}

.entry-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
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

.entry-slots::before {
  content: '·';
  margin-right: 4px;
  color: var(--line-strong);
}
</style>
