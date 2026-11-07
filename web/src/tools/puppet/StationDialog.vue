<!--
  新增 / 编辑站点弹窗。

  同一个弹窗承担两种模式，由 station 是否为 null 区分：
  - null：新增，草稿取默认值（主世界、Y=64、坐标 0）；
  - 非 null：编辑，打开时用传入站点回填，保存时把整份草稿 emit 回父组件。

  字段口径：分组是选择器里的 tag，最多 32 字且不允许空白；名称是地名；
  前缀会拼进假人名，最多 12 位；备注仅展示，最多 60 字（后端超长会截断）。
-->
<script setup lang="ts">
// ------------------------------ 依赖 ------------------------------ #
import { reactive, watch } from 'vue'

import { t } from '../../platform/i18n'
import type { Station } from './types'

// ------------------------------ props / emits ------------------------------ #
// open 控制显隐；station 为 null 表示新增，否则是正在编辑的那条记录。
const props = defineProps<{ open: boolean; station: Station | null }>()
const emit = defineEmits<{
  (e: 'close'): void
  (e: 'save', station: Station): void
}>()

// ------------------------------ 常量 ------------------------------ #
// 维度下拉的取值，与后端 constants.DIMENSIONS 一致；显示名走 puppet.dim.* 的 i18n。
const DIMENSIONS = ['overworld', 'the_nether', 'the_end']

// ------------------------------ 表单状态 ------------------------------ #
// 本地草稿：编辑时不直接改传入的 station，取消即整体丢弃。
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

// ------------------------------ 事件 ------------------------------ #
// 用入参回填草稿：编辑态取原值，新增态给默认值（主世界、Y=64）。
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

// ------------------------------ 生命周期 ------------------------------ #
// 只在「打开」的那一下回填，避免外部 station 变化覆盖用户正在输入的内容。
watch(
  () => props.open,
  (open) => {
    if (open) reset()
  },
)

// 提交：id 优先沿用原 id；新增时没填 id 就用前缀兜底，保证删除 / 执行能引用。
function submit() {
  emit('save', {
    id: draft.id || draft.prefix.trim(),
    name: draft.name.trim(),
    group: draft.group.trim(),
    prefix: draft.prefix.trim(),
    dimension: draft.dimension,
    // 数字框允许字符串中间态，提交时统一转 Number，非法值交给后端校验。
    x: Number(draft.x),
    y: Number(draft.y),
    z: Number(draft.z),
    note: draft.note,
  })
}
</script>

<template>
  <!-- 区块：遮罩（点击空白处关闭） -->
  <div v-if="open" class="overlay" @click.self="emit('close')">
    <!-- 区块：弹窗本体（新增 / 编辑共用） -->
    <div class="dialog">
      <!-- 区块：标题栏（按是否有 station 切换新增 / 编辑文案） -->
      <header class="dialog-head">
        <span>{{ station ? t('puppet.station.titleEdit') : t('puppet.station.titleAdd') }}</span>
        <button class="btn ghost sm" @click="emit('close')">✕</button>
      </header>

      <!-- 区块：表单区 -->
      <div class="dialog-body">
        <!-- 区块：分组与名称（分组进选择器 tag，名称是地名） -->
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

        <!-- 区块：假名前缀与维度（前缀会拼进 bot_<origin>_<dest>_<index>） -->
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

        <!-- 区块：坐标（X / Z 允许半格，Y 取整） -->
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

        <!-- 区块：备注（最多 60 字，仅展示用，不计入命令） -->
        <div class="field">
          <label class="field-label">{{ t('puppet.station.note') }}</label>
          <input v-model="draft.note" class="input" type="text" maxlength="60" />
          <span class="hint">
            {{ t('puppet.station.noteHint') }} · {{ draft.note.length }}/60
          </span>
        </div>
      </div>

      <!-- 区块：底部按钮（取消 / 保存） -->
      <footer class="dialog-foot">
        <button class="btn" @click="emit('close')">{{ t('puppet.action.cancel') }}</button>
        <button class="btn primary" @click="submit">{{ t('puppet.action.save') }}</button>
      </footer>
    </div>
  </div>
</template>

<style scoped>
/* 区块：遮罩（居中弹窗、模糊背景） */
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

/* 区块：弹窗容器（固定宽度，窄屏按视口收窄） */
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

/* 区块：表单区（字段纵向排列） */
.dialog-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px;
}

/* 区块：字段提示文字 */
.hint {
  color: var(--muted);
  font-size: 11px;
}
</style>
