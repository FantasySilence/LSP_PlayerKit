<script setup lang="ts">
import { reactive, watch } from 'vue'

import { t } from '../../platform/i18n'
import type { Station } from './types'

const props = defineProps<{ open: boolean; station: Station | null }>()
const emit = defineEmits<{
  (e: 'close'): void
  (e: 'save', station: Station): void
}>()

const DIMENSIONS = ['overworld', 'the_nether', 'the_end']

const draft = reactive({
  id: '',
  name: '',
  group: '',
  prefix: '',
  dimension: 'overworld',
  x: 0 as number | string,
  y: 64 as number | string,
  z: 0 as number | string,
  note: '',
})

function reset() {
  const source = props.station
  draft.id = source?.id ?? ''
  draft.name = source?.name ?? ''
  draft.group = source?.group ?? ''
  draft.prefix = source?.prefix ?? ''
  draft.dimension = source?.dimension ?? 'overworld'
  draft.x = source?.x ?? 0
  draft.y = source?.y ?? 64
  draft.z = source?.z ?? 0
  draft.note = source?.note ?? ''
}

watch(
  () => props.open,
  (open) => {
    if (open) reset()
  },
)

function submit() {
  emit('save', {
    id: draft.id || draft.prefix.trim(),
    name: draft.name.trim(),
    group: draft.group.trim(),
    prefix: draft.prefix.trim(),
    dimension: draft.dimension,
    x: Number(draft.x),
    y: Number(draft.y),
    z: Number(draft.z),
    note: draft.note,
  })
}
</script>

<template>
  <div v-if="open" class="overlay" @click.self="emit('close')">
    <div class="dialog">
      <header class="dialog-head">
        <span>{{ station ? t('puppet.station.titleEdit') : t('puppet.station.titleAdd') }}</span>
        <button class="btn ghost sm" @click="emit('close')">✕</button>
      </header>

      <div class="dialog-body">
        <div class="field-row">
          <div class="field">
            <label class="field-label">{{ t('puppet.station.group') }}</label>
            <input v-model="draft.group" class="input" type="text" maxlength="32" />
            <span class="hint">{{ t('puppet.station.groupHint') }}</span>
          </div>
          <div class="field">
            <label class="field-label">{{ t('puppet.station.name') }}</label>
            <input v-model="draft.name" class="input" type="text" maxlength="64" />
          </div>
        </div>

        <div class="field-row">
          <div class="field">
            <label class="field-label">{{ t('puppet.station.prefix') }}</label>
            <input v-model="draft.prefix" class="input mono" type="text" maxlength="12" />
            <span class="hint">{{ t('puppet.station.prefixHint') }}</span>
          </div>
          <div class="field">
            <label class="field-label">{{ t('puppet.station.dimension') }}</label>
            <select v-model="draft.dimension" class="input">
              <option v-for="dim in DIMENSIONS" :key="dim" :value="dim">
                {{ t(`puppet.dim.${dim}`) }}
              </option>
            </select>
          </div>
        </div>

        <div class="field-row">
          <div class="field">
            <label class="field-label">{{ t('puppet.station.x') }}</label>
            <input v-model="draft.x" class="input mono" type="number" step="0.5" />
          </div>
          <div class="field">
            <label class="field-label">{{ t('puppet.station.y') }}</label>
            <input v-model="draft.y" class="input mono" type="number" step="1" />
          </div>
          <div class="field">
            <label class="field-label">{{ t('puppet.station.z') }}</label>
            <input v-model="draft.z" class="input mono" type="number" step="0.5" />
          </div>
        </div>

        <div class="field">
          <label class="field-label">{{ t('puppet.station.note') }}</label>
          <input v-model="draft.note" class="input" type="text" maxlength="60" />
          <span class="hint">
            {{ t('puppet.station.noteHint') }} · {{ draft.note.length }}/60
          </span>
        </div>
      </div>

      <footer class="dialog-foot">
        <button class="btn" @click="emit('close')">{{ t('puppet.action.cancel') }}</button>
        <button class="btn primary" @click="submit">{{ t('puppet.action.save') }}</button>
      </footer>
    </div>
  </div>
</template>

<style scoped>
.overlay {
  position: fixed;
  inset: 0;
  z-index: 50;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--scrim);
  backdrop-filter: blur(2px);
}

.dialog {
  width: 460px;
  max-width: 92vw;
  display: flex;
  flex-direction: column;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
}

.dialog-head,
.dialog-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--line);
}

.dialog-foot {
  border-bottom: none;
  border-top: 1px solid var(--line);
  justify-content: flex-end;
  gap: 8px;
}

.dialog-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px;
}

.hint {
  color: var(--muted);
  font-size: 11px;
}
</style>
