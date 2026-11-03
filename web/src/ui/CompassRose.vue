<script setup lang="ts">
import { computed } from 'vue'

import { t } from '../platform/i18n'

const props = defineProps<{
  direction: string | null
  manual?: boolean
}>()

const emit = defineEmits<{ (e: 'select', direction: 'north' | 'east' | 'south' | 'west'): void }>()

const angle = computed(() => {
  switch (props.direction) {
    case 'north':
      return 0
    case 'east':
      return 90
    case 'south':
      return 180
    case 'west':
      return 270
    default:
      return null
  }
})
</script>

<template>
  <div class="compass">
    <svg viewBox="0 0 120 120" class="rose" @click.self="emit('select', 'north')">
      <circle cx="60" cy="60" r="52" class="ring" />
      <circle cx="60" cy="60" r="40" class="ring inner" />
      <text x="60" y="16" class="dir-label" @click="emit('select', 'north')">{{ t('compass.n') }}</text>
      <text x="106" y="64" class="dir-label" @click="emit('select', 'east')">{{ t('compass.e') }}</text>
      <text x="60" y="112" class="dir-label" @click="emit('select', 'south')">{{ t('compass.s') }}</text>
      <text x="14" y="64" class="dir-label" @click="emit('select', 'west')">{{ t('compass.w') }}</text>
      <g :style="{ transform: angle === null ? 'rotate(0deg)' : `rotate(${angle}deg)`, transformOrigin: '60px 60px' }">
        <polygon v-if="angle !== null" points="60,26 66,60 60,54 54,60" class="needle" />
        <polygon v-if="angle !== null" points="60,94 54,60 60,66 66,60" class="needle tail" />
      </g>
      <circle v-if="angle === null" cx="60" cy="60" r="5" class="idle" />
      <circle cx="60" cy="60" r="3" class="hub" />
    </svg>
    <div class="caption">
      <span v-if="direction" class="badge brand">{{ t(`direction.${direction}`) }}</span>
      <span v-else class="badge">{{ t('direction.unknown') }}</span>
      <span v-if="manual" class="badge warn">{{ t('direction.manual') }}</span>
    </div>
  </div>
</template>

<style scoped>
.compass {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.rose {
  width: 118px;
  height: 118px;
}

.ring {
  fill: var(--surface-2);
  stroke: var(--line-strong);
  stroke-width: 1.5;
}

.ring.inner {
  fill: none;
  stroke: var(--line);
}

.dir-label {
  fill: var(--muted);
  font-size: 10px;
  text-anchor: middle;
  cursor: pointer;
  user-select: none;
}

.dir-label:hover {
  fill: var(--brand);
}

.needle {
  fill: var(--brand);
}

.needle.tail {
  fill: var(--line-strong);
}

.idle {
  fill: var(--line-strong);
}

.hub {
  fill: var(--text);
}

.caption {
  display: flex;
  gap: 6px;
}
</style>
