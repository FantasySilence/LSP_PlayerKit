<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { t } from '../../platform/i18n'

interface Marker {
  x: number
  z: number
  rank: number
}

const props = withDefaults(
  defineProps<{
    cells: Uint8Array | null
    width: number
    height: number
    x0: number
    z0: number
    markers: Marker[]
    selected: number | null
    ringInner: number
    ringOuter: number
    heat?: Uint8Array | null
    perimeter?: { cx0: number; cz0: number; size: number } | null
  }>(),
  { heat: null, perimeter: null },
)

const emit = defineEmits<{ (e: 'select', index: number): void }>()

const wrap = ref<HTMLDivElement | null>(null)
const canvas = ref<HTMLCanvasElement | null>(null)
const scale = ref(4)
const offsetX = ref(0)
const offsetY = ref(0)
const hover = ref<{ cx: number; cz: number; bx: number; bz: number; slime: boolean } | null>(null)

let dragging = false
let dragStart = { x: 0, y: 0, ox: 0, oy: 0 }
let moved = false
// 用户手动缩放过 / 平移过时，容器尺寸变化只平移视口，不再重新 fit
let userView = false
let lastBox = { width: 0, height: 0 }

const mapWidth = computed(() => props.width * scale.value)
const mapHeight = computed(() => props.height * scale.value)

function fit(): void {
  const box = wrap.value
  const el = canvas.value
  if (!box || !el || !props.width || !props.height) return
  const rect = box.getBoundingClientRect()
  const s = Math.max(0.5, Math.min((rect.width - 12) / props.width, (rect.height - 12) / props.height))
  scale.value = s
  offsetX.value = (rect.width - props.width * s) / 2
  offsetY.value = (rect.height - props.height * s) / 2
  lastBox = { width: rect.width, height: rect.height }
  userView = false
  draw()
}

// 容器尺寸变化（窗口缩放、推荐面板开关、结果栏收放）时保持当前缩放与中心
function keepView(): void {
  const box = wrap.value
  const el = canvas.value
  if (!box || !el) {
    fit()
    return
  }
  const rect = box.getBoundingClientRect()
  if (!rect.width || !rect.height) return
  if (!lastBox.width || !lastBox.height) {
    fit()
    return
  }
  offsetX.value += (rect.width - lastBox.width) / 2
  offsetY.value += (rect.height - lastBox.height) / 2
  lastBox = { width: rect.width, height: rect.height }
  draw()
}

function draw(): void {
  const el = canvas.value
  const box = wrap.value
  if (!el || !box) return
  const ratio = window.devicePixelRatio || 1
  const rect = box.getBoundingClientRect()
  const width = Math.max(1, Math.floor(rect.width))
  const height = Math.max(1, Math.floor(rect.height))
  if (el.width !== Math.floor(width * ratio) || el.height !== Math.floor(height * ratio)) {
    el.width = Math.floor(width * ratio)
    el.height = Math.floor(height * ratio)
    el.style.width = `${width}px`
    el.style.height = `${height}px`
  }
  const ctx = el.getContext('2d')
  if (!ctx) return
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0)
  ctx.clearRect(0, 0, width, height)

  if (props.cells && props.width && props.height) {
    if (!offscreen.value || offscreen.value.width !== props.width || offscreen.value.height !== props.height) {
      offscreen.value = document.createElement('canvas')
      offscreen.value.width = props.width
      offscreen.value.height = props.height
      paintCells()
    }
    ctx.imageSmoothingEnabled = false
    ctx.drawImage(offscreen.value, offsetX.value, offsetY.value, mapWidth.value, mapHeight.value)

    if (props.heat && props.heat.length === props.width * props.height) {
      if (!heatCanvas.value || heatCanvas.value.width !== props.width || heatCanvas.value.height !== props.height) {
        heatCanvas.value = document.createElement('canvas')
        heatCanvas.value.width = props.width
        heatCanvas.value.height = props.height
        paintHeat()
      }
      ctx.globalAlpha = 0.45
      ctx.drawImage(heatCanvas.value, offsetX.value, offsetY.value, mapWidth.value, mapHeight.value)
      ctx.globalAlpha = 1
    }

    if (scale.value >= 10) {
      ctx.strokeStyle = 'rgba(120, 130, 145, 0.18)'
      ctx.lineWidth = 1
      for (let x = 0; x <= props.width; x += 1) {
        const px = Math.round(offsetX.value + x * scale.value) + 0.5
        ctx.beginPath()
        ctx.moveTo(px, offsetY.value)
        ctx.lineTo(px, offsetY.value + mapHeight.value)
        ctx.stroke()
      }
      for (let z = 0; z <= props.height; z += 1) {
        const py = Math.round(offsetY.value + z * scale.value) + 0.5
        ctx.beginPath()
        ctx.moveTo(offsetX.value, py)
        ctx.lineTo(offsetX.value + mapWidth.value, py)
        ctx.stroke()
      }
    }
  }

  if (props.perimeter) drawPerimeter(ctx)

  const selectedMarker = props.selected === null ? null : props.markers[props.selected] ?? null
  if (selectedMarker) {
    drawRing(ctx, selectedMarker)
  }

  props.markers.forEach((marker, index) => {
    const cx = marker.x / 16 - props.x0
    const cz = marker.z / 16 - props.z0
    if (cx < -1 || cz < -1 || cx > props.width + 1 || cz > props.height + 1) return
    const px = offsetX.value + cx * scale.value
    const py = offsetY.value + cz * scale.value
    const active = index === props.selected
    ctx.beginPath()
    ctx.arc(px, py, active ? 9 : 7, 0, Math.PI * 2)
    ctx.fillStyle = active ? '#ff6a4d' : 'rgba(15, 157, 138, 0.92)'
    ctx.fill()
    ctx.lineWidth = 2
    ctx.strokeStyle = 'rgba(255,255,255,0.9)'
    ctx.stroke()
    ctx.fillStyle = '#ffffff'
    ctx.font = 'bold 10px ui-monospace, Consolas, monospace'
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillText(String(marker.rank), px, py + 0.5)
  })

  drawAxes(ctx, width, height)
}

function drawPerimeter(ctx: CanvasRenderingContext2D): void {
  const area = props.perimeter
  if (!area) return
  const x = offsetX.value + (area.cx0 - props.x0) * scale.value
  const y = offsetY.value + (area.cz0 - props.z0) * scale.value
  const size = area.size * scale.value
  if (x > ctx.canvas.clientWidth || y > ctx.canvas.clientHeight || x + size < 0 || y + size < 0) {
    return
  }
  ctx.save()
  ctx.fillStyle = 'rgba(245, 158, 11, 0.10)'
  ctx.fillRect(x, y, size, size)
  ctx.setLineDash([8, 5])
  ctx.strokeStyle = 'rgba(217, 119, 6, 0.95)'
  ctx.lineWidth = 2
  ctx.strokeRect(x, y, size, size)
  ctx.setLineDash([])

  const label = t('slime.perimeter.label', { size: area.size })
  ctx.font = 'bold 11px ui-monospace, Consolas, monospace'
  ctx.textAlign = 'left'
  ctx.textBaseline = 'top'
  const textWidth = ctx.measureText(label).width
  const labelX = Math.max(4, x + 6)
  const labelY = Math.max(4, y + 6)
  ctx.fillStyle = 'rgba(255, 255, 255, 0.88)'
  ctx.fillRect(labelX - 3, labelY - 2, textWidth + 8, 16)
  ctx.fillStyle = '#b45309'
  ctx.fillText(label, labelX, labelY)
  ctx.restore()
}

const TICK_STEPS = [
  16, 32, 64, 128, 256, 512, 1024, 2048, 4096, 8192, 16384, 32768,
  65536, 131072, 262144, 524288, 1048576,
]

const AXIS_FONT = '600 12px ui-monospace, Consolas, monospace'
const AXIS_TICK = 8

function tickStep(ctx: CanvasRenderingContext2D, pxPerBlock: number): number {
  // 标签放大后按实测宽度留出间隔，避免相邻刻度数字贴在一起
  for (const step of TICK_STEPS) {
    const width = ctx.measureText(String(-step)).width
    if (step * pxPerBlock >= Math.max(64, width + 18)) return step
  }
  return TICK_STEPS[TICK_STEPS.length - 1]
}

function drawAxes(ctx: CanvasRenderingContext2D, width: number, height: number): void {
  if (!props.cells || !props.width || !props.height) return
  const pxPerBlock = scale.value / 16
  if (pxPerBlock <= 0) return
  const left = offsetX.value
  const top = offsetY.value
  const right = left + props.width * scale.value
  const bottom = top + props.height * scale.value
  const minBlockX = props.x0 * 16 + (Math.max(0, -left) / pxPerBlock)
  const maxBlockX = props.x0 * 16 + ((Math.min(width, right) - left) / pxPerBlock)
  const minBlockZ = props.z0 * 16 + (Math.max(0, -top) / pxPerBlock)
  const maxBlockZ = props.z0 * 16 + ((Math.min(height, bottom) - top) / pxPerBlock)

  ctx.save()
  ctx.font = AXIS_FONT
  ctx.lineWidth = 1
  ctx.strokeStyle = 'rgba(70, 84, 98, 0.55)'
  ctx.fillStyle = 'rgba(38, 47, 56, 0.95)'
  const step = tickStep(ctx, pxPerBlock)

  const firstX = Math.ceil(Math.max(minBlockX, props.x0 * 16) / step) * step
  ctx.textAlign = 'left'
  ctx.textBaseline = 'top'
  for (let block = firstX; block <= maxBlockX; block += step) {
    const px = left + (block / 16 - props.x0) * scale.value
    if (px < -1 || px > width + 1) continue
    ctx.beginPath()
    ctx.moveTo(Math.round(px) + 0.5, 0)
    ctx.lineTo(Math.round(px) + 0.5, AXIS_TICK)
    ctx.stroke()
    // 左上角留给纵向刻度数字，避免两轴标签叠在一起
    if (px < 46) continue
    const label = String(block)
    const labelWidth = ctx.measureText(label).width
    const labelX = Math.min(width - labelWidth - 2, Math.max(2, px + 3))
    ctx.lineWidth = 4
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.92)'
    ctx.strokeText(label, labelX, AXIS_TICK + 2)
    ctx.lineWidth = 1
    ctx.strokeStyle = 'rgba(70, 84, 98, 0.55)'
    ctx.fillText(label, labelX, AXIS_TICK + 2)
  }

  const firstZ = Math.ceil(Math.max(minBlockZ, props.z0 * 16) / step) * step
  ctx.textAlign = 'left'
  ctx.textBaseline = 'middle'
  for (let block = firstZ; block <= maxBlockZ; block += step) {
    const py = top + (block / 16 - props.z0) * scale.value
    if (py < -1 || py > height + 1) continue
    ctx.beginPath()
    ctx.moveTo(0, Math.round(py) + 0.5)
    ctx.lineTo(AXIS_TICK, Math.round(py) + 0.5)
    ctx.stroke()
    // 顶部一行留给横向刻度数字
    if (py < 24) continue
    const label = String(block)
    const labelY = Math.min(height - 9, Math.max(8, py))
    ctx.lineWidth = 4
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.92)'
    ctx.strokeText(label, AXIS_TICK + 2, labelY)
    ctx.lineWidth = 1
    ctx.strokeStyle = 'rgba(70, 84, 98, 0.55)'
    ctx.fillText(label, AXIS_TICK + 2, labelY)
  }
  ctx.restore()
}

function drawRing(ctx: CanvasRenderingContext2D, marker: Marker): void {
  const cx = offsetX.value + (marker.x / 16 - props.x0) * scale.value
  const cz = offsetY.value + (marker.z / 16 - props.z0) * scale.value
  const chunkPx = scale.value
  const inner = (props.ringInner / 16) * chunkPx
  const outer = (props.ringOuter / 16) * chunkPx
  ctx.save()
  ctx.setLineDash([5, 4])
  ctx.strokeStyle = 'rgba(255, 106, 77, 0.9)'
  ctx.lineWidth = 1.6
  ctx.beginPath()
  ctx.arc(cx, cz, inner, 0, Math.PI * 2)
  ctx.stroke()
  ctx.strokeStyle = 'rgba(15, 157, 138, 0.75)'
  ctx.beginPath()
  ctx.arc(cx, cz, outer, 0, Math.PI * 2)
  ctx.stroke()
  ctx.restore()
}

const offscreen = ref<HTMLCanvasElement | null>(null)
const heatCanvas = ref<HTMLCanvasElement | null>(null)

function paintCells(): void {
  const el = offscreen.value
  if (!el || !props.cells) return
  const ctx = el.getContext('2d')
  if (!ctx) return
  const image = ctx.createImageData(props.width, props.height)
  for (let i = 0; i < props.cells.length; i += 1) {
    if (!props.cells[i]) continue
    const offset = i * 4
    image.data[offset] = 16
    image.data[offset + 1] = 185
    image.data[offset + 2] = 129
    image.data[offset + 3] = 215
  }
  ctx.putImageData(image, 0, 0)
}

function paintHeat(): void {
  const el = heatCanvas.value
  if (!el || !props.heat) return
  const ctx = el.getContext('2d')
  if (!ctx) return
  const image = ctx.createImageData(props.width, props.height)
  for (let i = 0; i < props.heat.length; i += 1) {
    const value = props.heat[i]
    if (!value) continue
    const offset = i * 4
    image.data[offset] = 245
    image.data[offset + 1] = 158
    image.data[offset + 2] = 11
    image.data[offset + 3] = Math.min(255, value)
  }
  ctx.putImageData(image, 0, 0)
}

watch(
  () => [
    props.cells,
    props.heat,
    props.markers,
    props.selected,
    props.ringInner,
    props.ringOuter,
    props.perimeter,
  ],
  () => {
    offscreen.value = null
    heatCanvas.value = null
    draw()
  },
)

watch(
  () => [props.width, props.height, props.x0, props.z0],
  () => {
    offscreen.value = null
    heatCanvas.value = null
    fit()
  },
)

function zoomAt(factor: number, cx: number, cy: number): void {
  const next = Math.min(40, Math.max(0.4, scale.value * factor))
  const ratio = next / scale.value
  offsetX.value = cx - (cx - offsetX.value) * ratio
  offsetY.value = cy - (cy - offsetY.value) * ratio
  scale.value = next
  userView = true
  draw()
}

function onWheel(event: WheelEvent): void {
  event.preventDefault()
  const rect = canvas.value?.getBoundingClientRect()
  if (!rect) return
  zoomAt(event.deltaY < 0 ? 1.15 : 1 / 1.15, event.clientX - rect.left, event.clientY - rect.top)
}

function onPointerDown(event: PointerEvent): void {
  dragging = true
  moved = false
  dragStart = { x: event.clientX, y: event.clientY, ox: offsetX.value, oy: offsetY.value }
  canvas.value?.setPointerCapture(event.pointerId)
}

function onPointerMove(event: PointerEvent): void {
  if (dragging) {
    const dx = event.clientX - dragStart.x
    const dy = event.clientY - dragStart.y
    if (Math.abs(dx) + Math.abs(dy) > 3) {
      moved = true
      userView = true
    }
    offsetX.value = dragStart.ox + dx
    offsetY.value = dragStart.oy + dy
    draw()
    return
  }
  const rect = canvas.value?.getBoundingClientRect()
  if (!rect || !props.cells) return
  const cx = Math.floor((event.clientX - rect.left - offsetX.value) / scale.value)
  const cz = Math.floor((event.clientY - rect.top - offsetY.value) / scale.value)
  if (cx < 0 || cz < 0 || cx >= props.width || cz >= props.height) {
    hover.value = null
    return
  }
  hover.value = {
    cx: props.x0 + cx,
    cz: props.z0 + cz,
    bx: Math.floor(props.x0 * 16 + ((event.clientX - rect.left - offsetX.value) / scale.value) * 16),
    bz: Math.floor(props.z0 * 16 + ((event.clientY - rect.top - offsetY.value) / scale.value) * 16),
    slime: Boolean(props.cells[cz * props.width + cx]),
  }
}

function onPointerUp(event: PointerEvent): void {
  if (!dragging) return
  dragging = false
  canvas.value?.releasePointerCapture(event.pointerId)
  if (moved) return
  const rect = canvas.value?.getBoundingClientRect()
  if (!rect) return
  const px = event.clientX - rect.left
  const py = event.clientY - rect.top
  let best = -1
  let bestDistance = 14
  props.markers.forEach((marker, index) => {
    const mx = offsetX.value + (marker.x / 16 - props.x0) * scale.value
    const my = offsetY.value + (marker.z / 16 - props.z0) * scale.value
    const distance = Math.hypot(mx - px, my - py)
    if (distance < bestDistance) {
      bestDistance = distance
      best = index
    }
  })
  if (best >= 0) emit('select', best)
}

function zoomIn(): void {
  const rect = wrap.value?.getBoundingClientRect()
  if (!rect) return
  zoomAt(1.3, rect.width / 2, rect.height / 2)
}

function zoomOut(): void {
  const rect = wrap.value?.getBoundingClientRect()
  if (!rect) return
  zoomAt(1 / 1.3, rect.width / 2, rect.height / 2)
}

function reset(): void {
  fit()
}

function focus(index: number, spanChunks = 40): void {
  const marker = props.markers[index]
  const box = wrap.value
  if (!marker || !box) return
  const rect = box.getBoundingClientRect()
  const span = Math.max(16, Math.min(160, spanChunks))
  const next = Math.max(0.4, Math.min(40, Math.min(rect.width, rect.height) / span))
  scale.value = next
  offsetX.value = rect.width / 2 - (marker.x / 16 - props.x0) * next
  offsetY.value = rect.height / 2 - (marker.z / 16 - props.z0) * next
  lastBox = { width: rect.width, height: rect.height }
  userView = true
  draw()
}

defineExpose({ zoomIn, zoomOut, reset, focus })

let observer: ResizeObserver | null = null

onMounted(() => {
  fit()
  if (wrap.value) {
    observer = new ResizeObserver(() => {
      if (userView) keepView()
      else fit()
    })
    observer.observe(wrap.value)
  }
})

onBeforeUnmount(() => {
  observer?.disconnect()
  observer = null
})
</script>

<template>
  <div ref="wrap" class="map-wrap">
    <canvas
      ref="canvas"
      class="map-canvas"
      @wheel="onWheel"
      @pointerdown="onPointerDown"
      @pointermove="onPointerMove"
      @pointerup="onPointerUp"
      @pointerleave="hover = null"
    />
    <div v-if="hover" class="map-hover mono">
      {{ t('slime.hover.chunk') }} ({{ hover.cx }}, {{ hover.cz }})
      · {{ t('slime.hover.block') }} ({{ hover.bx }}, {{ hover.bz }})
      · {{ hover.slime ? t('slime.legend.slime') : t('slime.legend.normal') }}
    </div>
  </div>
</template>

<style scoped>
.map-wrap {
  position: relative;
  flex: 1;
  min-height: 0;
  overflow: hidden;
  background: var(--surface-2);
}

.map-canvas {
  width: 100%;
  height: 100%;
  display: block;
  cursor: grab;
  touch-action: none;
}

.map-canvas:active {
  cursor: grabbing;
}

.map-hover {
  position: absolute;
  left: 10px;
  bottom: 10px;
  padding: 3px 8px;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: var(--surface);
  color: var(--muted);
  font-size: 11px;
  pointer-events: none;
}
</style>
