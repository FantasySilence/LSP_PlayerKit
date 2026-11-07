<!--
  站点导入弹窗：把旧版 stops.json 或纯文本站点表并进当前站点表。

  流程：读文件（可选）→ 文本进编辑区（可继续手改）→ 选默认维度 → 提交给后端
  stations_import 识别格式、去重合并，成功后通过 done 事件把整张表交回父组件。
  文本行没写维度时，先看前缀里有没有维度片段（如 nether_wa），没有才用「默认维度」。
  识别不了的维度不报错，按默认维度导入并记一条 warning。
-->
<script setup lang="ts">
// ------------------------------ 依赖 ------------------------------ #
import { ref, watch } from 'vue'

import { callTool, invoke } from '../../platform/bridge'
import { t } from '../../platform/i18n'
import { notifyError } from '../../platform/toast'
import type { ImportResult, Station } from './types'

// ------------------------------ props / emits ------------------------------ #
// 只有显隐入参；导入结果（整张站点表 + 统计）通过 done 事件回传。
const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{
  (e: 'close'): void
  (e: 'done', stations: Station[], result: ImportResult): void
}>()

// ------------------------------ 常量 ------------------------------ #
// 默认维度的可选值，与站点弹窗、后端 constants.DIMENSIONS 保持一致。
const DIMENSIONS = ['overworld', 'the_nether', 'the_end']

// ------------------------------ 状态 ------------------------------ #
// 文本区内容：既可以直接粘贴，也可以读文件后继续编辑。
const text = ref('')
// 读进来的文件名，仅用于显示；纯手工粘贴时显示占位符。
const fileName = ref('')
// 文本行没有维度线索时的兜底维度（前缀里带 nether_ / end_ 等片段会优先）。
const defaultDimension = ref('overworld')
// 提交中：禁用确认按钮，防止重复导入。
const busy = ref(false)
// 导入失败时的错误提示，就地显示在弹窗里，不弹 toast。
const error = ref('')

// ------------------------------ 生命周期 ------------------------------ #
// 每次打开都清空上一次的内容，避免误把旧文本再导一次。
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

// ------------------------------ 事件 ------------------------------ #
// 选文件：走桥接的 file_open_text；用户取消（cancelled）时什么都不做。
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

// 提交：空文本直接提示；其余交给后端识别旧 stops.json 或纯文本格式。
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
  <!-- 区块：遮罩（点击空白处关闭） -->
  <div v-if="open" class="overlay" @click.self="emit('close')">
    <!-- 区块：弹窗本体 -->
    <div class="dialog">
      <!-- 区块：标题栏 -->
      <header class="dialog-head">
        <span>{{ t('puppet.import.title') }}</span>
        <button class="btn ghost sm" @click="emit('close')">✕</button>
      </header>

      <div class="dialog-body">
        <!-- 区块：格式说明（支持哪些写法） -->
        <p class="hint">{{ t('puppet.import.hint') }}</p>

        <!-- 区块：选择文件（读入后仍可手工修改） -->
        <div class="file-row">
          <button class="btn sm" @click="pickFile">{{ t('puppet.import.pickFile') }}</button>
          <span class="muted mono file-name">{{ fileName || '—' }}</span>
        </div>

        <!-- 区块：默认维度（文本与前缀都没有维度线索时才生效） -->
        <div class="field">
          <label class="field-label">{{ t('puppet.import.defaultDimension') }}</label>
          <select v-model="defaultDimension" class="input">
            <option v-for="dim in DIMENSIONS" :key="dim" :value="dim">
              {{ t(`puppet.dim.${dim}`) }}
            </option>
          </select>
        </div>

        <!-- 区块：文本编辑区（可直接粘贴旧 stops.json 或纯文本） -->
        <div class="field">
          <label class="field-label">{{ t('puppet.panel.stations') }}</label>
          <textarea v-model="text" class="input mono textarea" rows="8" spellcheck="false" />
        </div>

        <!-- 区块：错误提示 -->
        <p v-if="error" class="error">{{ error }}</p>
      </div>

      <!-- 区块：底部按钮（取消 / 导入） -->
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
/* 区块：遮罩 */
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

/* 区块：弹窗容器（比站点弹窗宽，便于看文本） */
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

/* 区块：标题栏与底栏共用排版 */
.dialog-head,
.dialog-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--line);
}

/* 区块：底栏（按钮靠右） */
.dialog-foot {
  border-bottom: none;
  border-top: 1px solid var(--line);
  justify-content: flex-end;
  gap: 8px;
}

/* 区块：内容区（纵向排列） */
.dialog-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px;
}

/* 区块：文件选择行（按钮 + 文件名） */
.file-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

/* 区块：文件名（单行省略） */
.file-name {
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 区块：文本编辑框（等宽、可纵向拉伸） */
.textarea {
  height: 150px;
  padding: 8px 10px;
  resize: vertical;
  line-height: 1.6;
}

/* 区块：说明文字 */
.hint {
  margin: 0;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.7;
}

/* 区块：错误提示 */
.error {
  margin: 0;
  color: var(--danger);
  font-size: 12px;
}
</style>
