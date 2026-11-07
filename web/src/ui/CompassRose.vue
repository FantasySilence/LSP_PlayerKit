<!--
  CompassRose.vue —— 罗盘组件

  负责：把四个基本方向（north/east/south/west）换算成指针旋转角度，
  画出带 N/E/S/W 文字的罗盘；没有方向时隐藏指针、在中心显示一个小圆点。
  交互关系：
  - 依赖 platform/i18n.ts 的 t() 显示方位与“手动”状态文案；
  - 父组件（目前是 pearl 工具视图）通过 props.direction 传入当前方向，
    props.manual 表示该方向是否由用户手动指定；
  - 点击 N/E/S/W 文字或罗盘空白处会 emit('select', 方向)，父组件据此切换方向
    并进入手动模式。
  说明：指针只识别这四个基本方向；其他取值时指针隐藏，下方文字仍按
  direction.<值> 去词典里取文案。
-->

<script setup lang="ts">
import { computed } from 'vue'

import { t } from '../platform/i18n'

const props = defineProps<{
  // 当前方向；null 表示未知
  direction: string | null
  // 是否手动指定方向，为 true 时在下方显示“手动”徽标
  manual?: boolean
}>()

// 只对外提供四个基本方向的选择事件
const emit = defineEmits<{ (e: 'select', direction: 'north' | 'east' | 'south' | 'west'): void }>()

// 方向 → 指针角度：0 度为北，顺时针递增；未知方向返回 null
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
  <!-- 区块：罗盘（SVG 绘制圆环、四个方位文字、指针与中心轴） -->
  <div class="compass">
    <!-- 点击 SVG 空白处默认选中“北”；点在文字上时由文字的点击事件覆盖 -->
    <svg viewBox="0 0 120 120" class="rose" @click.self="emit('select', 'north')">
      <!-- 外圈与内圈 -->
      <circle cx="60" cy="60" r="52" class="ring" />
      <circle cx="60" cy="60" r="40" class="ring inner" />
      <!-- 区块：四个方位文字，点击即选择该方向 -->
      <text x="60" y="16" class="dir-label" @click="emit('select', 'north')">{{ t('compass.n') }}</text>
      <text x="106" y="64" class="dir-label" @click="emit('select', 'east')">{{ t('compass.e') }}</text>
      <text x="60" y="112" class="dir-label" @click="emit('select', 'south')">{{ t('compass.s') }}</text>
      <text x="14" y="64" class="dir-label" @click="emit('select', 'west')">{{ t('compass.w') }}</text>
      <!-- 区块：指针组，通过 CSS transform 绕圆心旋转到目标角度 -->
      <g :style="{ transform: angle === null ? 'rotate(0deg)' : `rotate(${angle}deg)`, transformOrigin: '60px 60px' }">
        <!-- 指针前半段（朝向目标方向） -->
        <polygon v-if="angle !== null" points="60,26 66,60 60,54 54,60" class="needle" />
        <!-- 指针后半段（尾翼） -->
        <polygon v-if="angle !== null" points="60,94 54,60 60,66 66,60" class="needle tail" />
      </g>
      <!-- 未知方向时用中心圆点代替指针 -->
      <circle v-if="angle === null" cx="60" cy="60" r="5" class="idle" />
      <!-- 中心轴，任何状态下都显示 -->
      <circle cx="60" cy="60" r="3" class="hub" />
    </svg>
    <!-- 区块：方向说明（当前方向徽标 + 可选“手动”徽标） -->
    <div class="caption">
      <span v-if="direction" class="badge brand">{{ t(`direction.${direction}`) }}</span>
      <span v-else class="badge">{{ t('direction.unknown') }}</span>
      <span v-if="manual" class="badge warn">{{ t('direction.manual') }}</span>
    </div>
  </div>
</template>

<style scoped>
/* 区块：整体布局（罗盘在上，说明在下） */
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

/* 区块：圆环 */
.ring {
  fill: var(--surface-2);
  stroke: var(--line-strong);
  stroke-width: 1.5;
}

.ring.inner {
  fill: none;
  stroke: var(--line);
}

/* 区块：方位文字 */
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

/* 区块：指针与中心 */
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

/* 区块：下方说明 */
.caption {
  display: flex;
  gap: 6px;
}
</style>
