<script setup lang="ts">
import { ref, watch } from 'vue'

import { callTool, invoke } from '../../platform/bridge'
import { t } from '../../platform/i18n'
import { notifyError } from '../../platform/toast'
import type { ImportResult, Station } from './types'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{
  (e: 'close'): void
  (e: 'done', stations: Station[], result: ImportResult): void
}>()

const DIMENSIONS = ['overworld', 'the_nether', 'the_end']

const text = ref('')
const fileName = ref('')
const defaultDimension = ref('overworld')
const busy = ref(false)
const error = ref('')

watch(
  () => props.open,
  (open) => {
    if (open) {
      text.value = ''
      fileName.value = ''
      error.value = ''
    }
  },
)

async function pickFile() {
  try {
    const result = await invoke<{ cancelled?: boolean; name?: string; text?: string }>(
      'file_open_text',
    )
    if (!result || result.cancelled) return
    text.value = result.text ?? ''
    fileName.value = result.name ?? ''
  } catch (err) {
    notifyError(err)
  }
}

async function submit() {
  if (!text.value.trim()) {
    error.value = t('puppet.import.empty')
    return
  }
  busy.value = true
  error.value = ''
  try {
    const result = await callTool<ImportResult>('puppet', 'stations_import', {
      text: text.value,
      defaultDimension: defaultDimension.value,
    })
    emit('done', result.stations, result)
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div v-if="open" class="overlay" @click.self="emit('close')">
    <div class="dialog">
      <header class="dialog-head">
        <span>{{ t('puppet.import.title') }}</span>
        <button class="btn ghost sm" @click="emit('close')">✕</button>
      </header>

      <div class="dialog-body">
        <p class="hint">{{ t('puppet.import.hint') }}</p>

        <div class="file-row">
          <button class="btn sm" @click="pickFile">{{ t('puppet.import.pickFile') }}</button>
          <span class="muted mono file-name">{{ fileName || '—' }}</span>
        </div>

        <div class="field">
          <label class="field-label">{{ t('puppet.import.defaultDimension') }}</label>
          <select v-model="defaultDimension" class="input">
            <option v-for="dim in DIMENSIONS" :key="dim" :value="dim">
              {{ t(`puppet.dim.${dim}`) }}
            </option>
          </select>
        </div>

        <div class="field">
          <label class="field-label">{{ t('puppet.panel.stations') }}</label>
          <textarea v-model="text" class="input mono textarea" rows="8" spellcheck="false" />
        </div>

        <p v-if="error" class="error">{{ error }}</p>
      </div>

      <footer class="dialog-foot">
        <button class="btn" @click="emit('close')">{{ t('puppet.action.cancel') }}</button>
        <button class="btn primary" :disabled="busy" @click="submit">
          {{ t('puppet.import.confirm') }}
        </button>
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
  width: 560px;
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

.file-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.file-name {
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.textarea {
  height: 150px;
  padding: 8px 10px;
  resize: vertical;
  line-height: 1.6;
}

.hint {
  margin: 0;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.7;
}

.error {
  margin: 0;
  color: var(--danger);
  font-size: 12px;
}
</style>
