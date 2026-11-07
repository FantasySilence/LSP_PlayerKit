<!--
  史莱姆区块查找器 · Canvas 地图（SlimeMap.vue）

  只负责画图与视图交互，不请求数据：位图、热力、标记、空置域、查看点、搜索中心都由 props 传入。
  坐标换算：区块 = 方块 / 16；屏幕像素 = offset + (区块 - x0) * scale。
  chunkSize 表示「每格代表 N 个区块」（概览图降采样），只有为 1 时才是逐区块的精确视图。

  绘制顺序（后画的盖住先画的）：格子位图 → 热力 → 网格 → 空置域 → 圆环 → 结果标记
  → 查看点 → 搜索中心 → 坐标轴。整幅画布每次 draw() 重绘。
-->

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { t } from '../../platform/i18n'

// ===== 组件契约 =====
// 一个结果标记：x / z 为方块坐标（内部会除以 16 换成区块），rank 用来写在圆点里
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
    probe?: { x: number; z: number } | null
    chunkSize?: number
    center?: { x: number; z: number } | null
  }>(),
  { heat: null, perimeter: null, probe: null, chunkSize: 1, center: null },
)

// 交给父组件的唯一事件：点中标记时回传它在 markers 中的下标
const emit = defineEmits<{ (e: 'select', index: number): void }>()

// ===== 视图变换状态 =====
const wrap = ref<HTMLDivElement | null>(null)
const canvas = ref<HTMLCanvasElement | null>(null)
// scale：每个区块占多少像素；offsetX / offsetY：位图左上角在画布中的像素位置
const scale = ref(4)
const offsetX = ref(0)
const offsetY = ref(0)
// 鼠标悬停的区块 / 方块坐标；slime 表示该格是否为史莱姆区块
const hover = ref<{ cx: number; cz: number; bx: number; bz: number; slime: boolean } | null>(null)

// 拖动状态：dragging 为按住中，moved 用来区分「拖动」与「点击」
let dragging = false
let dragStart = { x: 0, y: 0, ox: 0, oy: 0 }
let moved = false
// 用户手动缩放过 / 平移过时，容器尺寸变化只平移视口，不再重新 fit
let userView = false
// 上一次的容器尺寸，keepView 用它算中心偏移
let lastBox = { width: 0, height: 0 }

// 地图实际覆盖的区块数 = 格数 × 每格区块数（chunkSize）
const chunksW = computed(() => props.width * (props.chunkSize || 1))
const chunksH = computed(() => props.height * (props.chunkSize || 1))
// 缩放后的位图像素尺寸
const mapWidth = computed(() => chunksW.value * scale.value)
const mapHeight = computed(() => chunksH.value * scale.value)

// 全图适配：取横纵两个方向的较小缩放，留 12px 边距后居中；
// 会清掉 userView，之后容器尺寸变化重新走 fit
function fit(): void {
  const box = wrap.value
  const el = canvas.value
  if (!box || !el || !props.width || !props.height) return
  const rect = box.getBoundingClientRect()
  const s = Math.max(1e-6, Math.min((rect.width - 12) / chunksW.value, (rect.height - 12) / chunksH.value))
  scale.value = s
  // 居中：两侧剩余空间各分一半
  offsetX.value = (rect.width - chunksW.value * s) / 2
  offsetY.value = (rect.height - chunksH.value * s) / 2
  lastBox = { width: rect.width, height: rect.height }
  userView = false
  draw()
}

// 容器尺寸变化（窗口缩放、推荐面板开关、结果栏收放）时保持当前缩放与中心：
// 只按容器宽高的变化量平移 offset，scale 不动，视觉中心留在原处
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

// ===== 分层绘制 =====
function draw(): void {
  const el = canvas.value
  const box = wrap.value
  if (!el || !box) return
  // 按 devicePixelRatio 调整画布实际像素，否则高分屏上会发虚
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
  // 先放大坐标系，之后所有绘制都按 CSS 像素计算
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0)
  ctx.clearRect(0, 0, width, height)

  if (props.cells && props.width && props.height) {
    // 1) 格子位图：离屏 canvas 缓存原尺寸位图，再整体缩放贴到主画布；
    //    缓存尺寸与位图不一致时才重画，避免每帧遍历全部格子
    if (!offscreen.value || offscreen.value.width !== props.width || offscreen.value.height !== props.height) {
      offscreen.value = document.createElement('canvas')
      offscreen.value.width = props.width
      offscreen.value.height = props.height
      paintCells()
    }
    // 关闭平滑，放大后仍是清晰的小方块
    ctx.imageSmoothingEnabled = false
    ctx.drawImage(offscreen.value, offsetX.value, offsetY.value, mapWidth.value, mapHeight.value)

    // 2) 热力图：与位图同尺寸，半透明叠加在上面
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

    // 3) 网格线：只在逐区块视图（chunkSize=1）且放大到 10px/区块以上时画，
    //    概览图一格 N 区块，画网格会误导
    if (scale.value >= 10 && (props.chunkSize || 1) === 1) {
      ctx.strokeStyle = 'rgba(120, 130, 145, 0.18)'
      ctx.lineWidth = 1
      for (let x = 0; x <= props.width; x += 1) {
        // +0.5 让 1px 线落在像素中心，避免发虚
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

  // 4) 空置域方框（虚线琥珀色）
  if (props.perimeter) drawPerimeter(ctx)

  const selectedMarker = props.selected === null ? null : props.markers[props.selected] ?? null
  if (selectedMarker) {
    drawRing(ctx, selectedMarker)
  }
  // 5) 查看点也按「挂机点」画 24 / 128 圆环
  if (props.probe) {
    drawRing(ctx, { x: props.probe.x, z: props.probe.z, rank: 0 })
  }

  // 6) 结果标记：屏幕坐标 = offset + (区块 - x0) * scale，越界的直接跳过
  props.markers.forEach((marker, index) => {
    const cx = marker.x / 16 - props.x0
    const cz = marker.z / 16 - props.z0
    if (cx < -1 || cz < -1 || cx > chunksW.value + 1 || cz > chunksH.value + 1) return
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
    // 圆点中央写名次
    ctx.fillStyle = '#ffffff'
    ctx.font = 'bold 10px ui-monospace, Consolas, monospace'
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillText(String(marker.rank), px, py + 0.5)
  })

  // 7) 查看点（白色十字 + 蓝点）与搜索中心（橙色小环）
  if (props.probe) drawProbe(ctx)
  if (props.center) drawCenter(ctx)

  // 8) 坐标轴最后画，刻度数字压在最上层
  drawAxes(ctx, width, height)
}

// 搜索中心：橙色小圆环，配合概览图定位
function drawCenter(ctx: CanvasRenderingContext2D): void {
  const point = props.center
  if (!point) return
  const cx = point.x / 16 - props.x0
  const cz = point.z / 16 - props.z0
  if (cx < -1 || cz < -1 || cx > chunksW.value + 1 || cz > chunksH.value + 1) return
  const px = offsetX.value + cx * scale.value
  const py = offsetY.value + cz * scale.value
  ctx.save()
  ctx.beginPath()
  ctx.arc(px, py, 7, 0, Math.PI * 2)
  ctx.lineWidth = 2.2
  ctx.strokeStyle = 'rgba(255, 255, 255, 0.95)'
  ctx.stroke()
  ctx.beginPath()
  ctx.arc(px, py, 7, 0, Math.PI * 2)
  ctx.lineWidth = 1.4
  ctx.strokeStyle = '#d97706'
  ctx.stroke()
  ctx.beginPath()
  ctx.arc(px, py, 1.8, 0, Math.PI * 2)
  ctx.fillStyle = '#d97706'
  ctx.fill()
  ctx.restore()
}

// 手动查看的坐标：白色十字 + 蓝色圆点，和「挂机点」区分开
function drawProbe(ctx: CanvasRenderingContext2D): void {
  const point = props.probe
  if (!point) return
  const cx = point.x / 16 - props.x0
  const cz = point.z / 16 - props.z0
  if (cx < -1 || cz < -1 || cx > chunksW.value + 1 || cz > chunksH.value + 1) return
  const px = offsetX.value + cx * scale.value
  const py = offsetY.value + cz * scale.value
  ctx.save()
  ctx.beginPath()
  ctx.moveTo(px - 13, py)
  ctx.lineTo(px - 4, py)
  ctx.moveTo(px + 4, py)
  ctx.lineTo(px + 13, py)
  ctx.moveTo(px, py - 13)
  ctx.lineTo(px, py - 4)
  ctx.moveTo(px, py + 4)
  ctx.lineTo(px, py + 13)
  ctx.lineWidth = 3.2
  ctx.strokeStyle = 'rgba(10, 30, 60, 0.55)'
  ctx.stroke()
  ctx.lineWidth = 1.7
  ctx.strokeStyle = 'rgba(255, 255, 255, 0.95)'
  ctx.stroke()
  ctx.beginPath()
  ctx.arc(px, py, 3.4, 0, Math.PI * 2)
  ctx.fillStyle = '#2f80ed'
  ctx.fill()
  ctx.lineWidth = 1.6
  ctx.strokeStyle = 'rgba(255, 255, 255, 0.95)'
  ctx.stroke()
  ctx.restore()
}

// 空置域：半透明填充 + 虚线边框 + 左上角尺寸标签；完全在视口外时跳过
function drawPerimeter(ctx: CanvasRenderingContext2D): void {
  const area = props.perimeter
  if (!area) return
  // 左上角区块坐标是 cx0 / cz0，换算成屏幕像素
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

// ===== 坐标轴 =====
// 候选刻度间距（方块）：都是 2 的幂，从 16（一个区块）到 2^20
const TICK_STEPS = [
  16, 32, 64, 128, 256, 512, 1024, 2048, 4096, 8192, 16384, 32768,
  65536, 131072, 262144, 524288, 1048576,
]

const AXIS_FONT = '600 12px ui-monospace, Consolas, monospace'
const AXIS_TICK = 8

// 自适应刻度：从最小间距开始试，直到「间距 × 每方块像素」能放下标签
// （最窄 64px，且不小于实测文字宽度 + 18）
function tickStep(ctx: CanvasRenderingContext2D, pxPerBlock: number): number {
  // 标签放大后按实测宽度留出间隔，避免相邻刻度数字贴在一起
  for (const step of TICK_STEPS) {
    const width = ctx.measureText(String(-step)).width
    if (step * pxPerBlock >= Math.max(64, width + 18)) return step
  }
  return TICK_STEPS[TICK_STEPS.length - 1]
}

// 坐标轴：顶边标 X、左边标 Z，单位都是方块；两轴在左上角互相避让——
// 顶边前 46px 不写数字（留给纵向标签），左边前 24px 不写数字（留给横向标签）
function drawAxes(ctx: CanvasRenderingContext2D, width: number, height: number): void {
  if (!props.cells || !props.width || !props.height) return
  // 每方块多少像素 = 每区块像素 / 16
  const pxPerBlock = scale.value / 16
  if (pxPerBlock <= 0) return
  const left = offsetX.value
  const top = offsetY.value
  const right = left + chunksW.value * scale.value
  const bottom = top + chunksH.value * scale.value
  // 视口可见范围换算成方块坐标：位图原点 + 被裁掉的那部分像素折算
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

  // 第一个刻度：从可见起点向上取整到 step 的整数倍
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

// 挂机圆环：内径画红虚线、外径画绿虚线；半径单位是方块，先除 16 换成区块再乘缩放比
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

// 离屏缓存：位图与热力各一张，只有在尺寸变化时才重新绘制
const offscreen = ref<HTMLCanvasElement | null>(null)
const heatCanvas = ref<HTMLCanvasElement | null>(null)

// 把 0/1 位图画进离屏 canvas：1 = 史莱姆区块（绿色），0 保持透明
function paintCells(): void {
  const el = offscreen.value
  if (!el || !props.cells) return
  const ctx = el.getContext('2d')
  if (!ctx) return
  const image = ctx.createImageData(props.width, props.height)
  for (let i = 0; i < props.cells.length; i += 1) {
    if (!props.cells[i]) continue
    const offset = i * 4
    // RGBA：16,185,129 是史莱姆绿，215 为不透明度
    image.data[offset] = 16
    image.data[offset + 1] = 185
    image.data[offset + 2] = 129
    image.data[offset + 3] = 215
  }
  ctx.putImageData(image, 0, 0)
}

// 把热力字节画进离屏 canvas：统一橙色，alpha 直接取热力值（0 = 透明）
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

// 数据、选中项或圆环参数变化：离屏缓存失效，整幅重绘
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

// 位图范围变化（换了区域或 stride）：缓存失效，并重新全图适配
watch(
  () => [props.width, props.height, props.x0, props.z0],
  () => {
    offscreen.value = null
    heatCanvas.value = null
    fit()
  },
)

// ===== 交互：缩放 / 平移 / 悬停 / 点选 =====
// 以 (cx, cy) 为锚点缩放：换算 offset 让锚点下的地图内容原地不动
function zoomAt(factor: number, cx: number, cy: number): void {
  const next = Math.min(40, Math.max(0.4, scale.value * factor))
  const ratio = next / scale.value
  offsetX.value = cx - (cx - offsetX.value) * ratio
  offsetY.value = cy - (cy - offsetY.value) * ratio
  scale.value = next
  userView = true
  draw()
}

// 滚轮缩放：向上（deltaY < 0）放大 1.15 倍，向下缩小；锚点取光标位置
function onWheel(event: WheelEvent): void {
  event.preventDefault()
  const rect = canvas.value?.getBoundingClientRect()
  if (!rect) return
  zoomAt(event.deltaY < 0 ? 1.15 : 1 / 1.15, event.clientX - rect.left, event.clientY - rect.top)
}

// 按下开始拖动，并捕获指针，保证移出画布后仍能收到 move / up
function onPointerDown(event: PointerEvent): void {
  dragging = true
  moved = false
  dragStart = { x: event.clientX, y: event.clientY, ox: offsetX.value, oy: offsetY.value }
  canvas.value?.setPointerCapture(event.pointerId)
}

// 拖动中：按位移整体平移（超过 3px 记为「拖动过」，抬起时不再触发点选）；
// 未拖动时：把光标位置换算成区块 / 方块坐标写进 hover
function onPointerMove(event: PointerEvent): void {
  if (dragging) {
    const dx = event.clientX - dragStart.x
    const dy = event.clientY - dragStart.y
    // 用位移绝对值之和做阈值，判断是拖动还是点击
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
  // 光标减去画布原点与 offset，再除以 scale 得到格下标；越界则清空 hover
  const cx = Math.floor((event.clientX - rect.left - offsetX.value) / scale.value)
  const cz = Math.floor((event.clientY - rect.top - offsetY.value) / scale.value)
  if (cx < 0 || cz < 0 || cx >= chunksW.value || cz >= chunksH.value) {
    hover.value = null
    return
  }
  // 区块坐标 = 位图原点 + 格下标；方块坐标用未取整的像素位置 × 16 换算
  hover.value = {
    cx: props.x0 + cx,
    cz: props.z0 + cz,
    bx: Math.floor(props.x0 * 16 + ((event.clientX - rect.left - offsetX.value) / scale.value) * 16),
    bz: Math.floor(props.z0 * 16 + ((event.clientY - rect.top - offsetY.value) / scale.value) * 16),
    slime: Boolean(props.cells[cz * props.width + cx]),
  }
}

// 抬起：拖动过就只结束拖动；否则当作点击，取 14px 内最近的结果标记并上报选中项
function onPointerUp(event: PointerEvent): void {
  if (!dragging) return
  dragging = false
  canvas.value?.releasePointerCapture(event.pointerId)
  if (moved) return
  const rect = canvas.value?.getBoundingClientRect()
  if (!rect) return
  // 指针位置换算成容器内坐标，再与各标记的屏幕位置比距离
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

// 工具栏「＋」：以容器中心为锚点放大
function zoomIn(): void {
  const rect = wrap.value?.getBoundingClientRect()
  if (!rect) return
  zoomAt(1.3, rect.width / 2, rect.height / 2)
}

// 工具栏「－」：以容器中心为锚点缩小
function zoomOut(): void {
  const rect = wrap.value?.getBoundingClientRect()
  if (!rect) return
  zoomAt(1 / 1.3, rect.width / 2, rect.height / 2)
}

// 复位：回到全图适配
function reset(): void {
  fit()
}

// 聚焦某个方块坐标：让该点落在容器中心，按 spanChunks 个区块铺满短边；
// span 先夹到 [16, 160] 区间，缩放上限 40px/区块
function focusPoint(x: number, z: number, spanChunks = 40): void {
  const box = wrap.value
  if (!box) return
  const rect = box.getBoundingClientRect()
  const span = Math.max(16, Math.min(160, spanChunks))
  const next = Math.max(0.4, Math.min(40, Math.min(rect.width, rect.height) / span))
  scale.value = next
  // 反解 offset，使 (x, z) 恰好位于容器中心
  offsetX.value = rect.width / 2 - (x / 16 - props.x0) * next
  offsetY.value = rect.height / 2 - (z / 16 - props.z0) * next
  // 记录新尺寸并标记为用户视图，之后容器变化走 keepView
  lastBox = { width: rect.width, height: rect.height }
  userView = true
  draw()
}

// 按结果下标聚焦，默认取 40×40 区块的范围
function focus(index: number, spanChunks = 40): void {
  const marker = props.markers[index]
  if (!marker) return
  focusPoint(marker.x, marker.z, spanChunks)
}

// 暴露给父组件 View.vue 调用（复位 / 聚焦 / 缩放）
defineExpose({ zoomIn, zoomOut, reset, focus, focusPoint })

// 容器尺寸观察者：用户没动过视图就重新 fit，动过则只平移保持中心
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

// 卸载时断开观察者，避免回调继续执行
onBeforeUnmount(() => {
  observer?.disconnect()
  observer = null
})
</script>

<template>
  <!-- 区块：画布容器（canvas 负责绘制，下方 div 显示悬停坐标） -->
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
    <!-- 悬停信息：区块坐标 · 方块坐标 · 该格是否为史莱姆 -->
    <div v-if="hover" class="map-hover mono">
      {{ t('slime.hover.chunk') }} ({{ hover.cx }}, {{ hover.cz }})
      · {{ t('slime.hover.block') }} ({{ hover.bx }}, {{ hover.bz }})
      · {{ hover.slime ? t('slime.legend.slime') : t('slime.legend.normal') }}
    </div>
  </div>
</template>

<style scoped>
/* 区块：画布容器（裁剪溢出，保证缩放后不画出面板） */
.map-wrap {
  position: relative;
  flex: 1;
  min-height: 0;
  overflow: hidden;
  background: var(--surface-2);
}

/* 区块：画布与光标形态（可拖动 / 拖动中） */
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

/* 区块：悬停信息条（不拦截指针事件） */
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
