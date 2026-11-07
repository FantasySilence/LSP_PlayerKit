<!--
  AboutDialog.vue —— 关于弹窗

  负责：展示应用名称、版本号与三条简介信息，并提供“打开说明文件”“GitHub 仓库”
  “关闭”三个按钮。
  交互关系：
  - 由 App.vue 在点击左侧工具轨底部的“关于”时渲染，版本号通过 props.version 传入；
  - 关闭时 emit('close')，由 App.vue 把 aboutOpen 置回 false；
  - “打开说明文件”调后端 open_manual（按当前语言打开对应 PDF），
    “GitHub 仓库”调 open_external（后端只允许 http/https 链接）；
  - 失败统一交给 platform/toast.ts 的 notifyError 显示。
-->

<script setup lang="ts">
import { invoke } from '../platform/bridge'
import { locale, t } from '../platform/i18n'
import { notifyError } from '../platform/toast'

// 父组件传入的版本号，用于显示成 v 加版本号
const props = defineProps<{ version: string }>()

// 只声明一个 close 事件，模板里的按钮与父组件都按这个名字对接
const emit = defineEmits<{ (e: 'close'): void }>()

// 项目仓库地址：后端 open_external 只放行 http(s) 链接
const REPO_URL = 'https://github.com/FantasySilence/LSP_PlayerKit'

// 打开说明文档：把当前语言传给后端，由后端选择中文或英文 PDF
async function openDoc() {
  try {
    await invoke('open_manual', locale.value)
  } catch (error) {
    notifyError(error)
  }
}

// 打开项目仓库：交给系统默认浏览器
async function openRepo() {
  try {
    await invoke('open_external', REPO_URL)
  } catch (error) {
    notifyError(error)
  }
}
</script>

<template>
  <!-- 遮罩：@click.self 保证只有点到遮罩本身才关闭，点弹窗内容不会误关 -->
  <div class="overlay" @click.self="emit('close')">
    <!-- 区块：关于内容 -->
    <section class="about">
      <!-- 标题区：图标、应用名、版本号 -->
      <div class="mark">◆</div>
      <h2>LSP PlayerKit</h2>
      <div class="version mono">v{{ props.version }}</div>

      <!-- 简介与三条要点（技术栈、数据处理方式、开源协议），文案都来自 i18n -->
      <p class="intro">{{ t('about.intro') }}</p>

      <ul class="facts">
        <li>{{ t('about.tech') }}</li>
        <li>{{ t('about.data') }}</li>
        <li>{{ t('about.license') }}</li>
      </ul>

      <!-- 区块：操作按钮 -->
      <div class="actions">
        <button class="btn" @click="openDoc">{{ t('about.docs') }}</button>
        <button class="btn" @click="openRepo">{{ t('about.repo') }}</button>
        <button class="btn primary" @click="emit('close')">{{ t('action.close') }}</button>
      </div>
    </section>
  </div>
</template>

<style scoped>
/* 区块：遮罩与居中对齐 */
.overlay {
  position: fixed;
  inset: 0;
  z-index: 70;
  display: grid;
  place-items: center;
  background: var(--scrim);
  backdrop-filter: blur(2px);
}

/* 区块：弹窗卡片 */
.about {
  width: 440px;
  max-width: 92vw;
  padding: 24px;
  border: 1px solid var(--line);
  border-radius: var(--radius-lg);
  background: var(--surface);
  box-shadow: var(--shadow);
}

/* 区块：标题区 */
.mark {
  display: grid;
  place-items: center;
  width: 46px;
  height: 46px;
  margin-bottom: 12px;
  border-radius: 12px;
  background: var(--brand-soft);
  color: var(--brand);
  font-size: 20px;
}

h2 {
  margin: 0 0 4px;
  font-size: 18px;
}

.version {
  margin-bottom: 14px;
  color: var(--muted);
  font-size: 12px;
}

/* 区块：简介与要点列表 */
.intro {
  margin: 0 0 12px;
  font-size: 13px;
  line-height: 1.7;
}

.facts {
  margin: 0 0 20px;
  padding-left: 18px;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.9;
}

/* 区块：底部按钮 */
.actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}
</style>
