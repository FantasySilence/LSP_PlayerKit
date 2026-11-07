/**
 * 假人搬货工具的共享类型。
 *
 * 这里只描述数据的形状，不含任何运行逻辑；字段名与后端 payload 一一对应，
 * 改名或增删字段需同步 src/lspkit/tools/puppet（constants / core / actions）。
 *
 * 分区：
 * - 站点：Station、SpawnStation；
 * - 计划：Plan、PlanCommand、PlanBatch（后端 `plan` 的返回）；
 * - 执行：RunState、RunMeta（`run_start` / `run_status` 的状态与元信息）；
 * - 台账与周边：Order、OrderDraft、ImportResult、DiagnoseCheck。
 */

/**
 * 站点表里的一条记录：一个可以生成假人的位置。
 * 站点表最多 200 条，由后端 constants.MAX_STATIONS 限制。
 */
export interface Station {
  /** 唯一标识；新增站点时前端默认取 prefix，编辑 / 删除 / 执行 meta 都用它。 */
  id: string
  /** 显示名（地名）；站点列表与两个选择器展示的是这一列。 */
  name: string
  /** 分组 tag（如「工业区」），允许空串；选择器先按它筛，再选具体站点。 */
  group: string
  /** 短前缀，拼进假人名 `bot_<origin>_<dest>_<index>`，最多 12 位。 */
  prefix: string
  /** 维度：overworld / the_nether / the_end，写进 `/execute in minecraft:<维度>`。 */
  dimension: string
  /** 站点横坐标 X；生成命令的 `spawn at <x> <y> <z>` 直接取这三个值。 */
  x: number
  /** 站点高度 Y；新建站点默认 64。 */
  y: number
  /** 站点纵深 Z。 */
  z: number
  /** 备注：只用于界面展示，超过 60 字由后端截断，不影响命令。 */
  note?: string
}

/**
 * 计划里的一条命令（生成与清除各一条，按假人一一对应）。
 */
export interface PlanCommand {
  /** 在本阶段命令列表里的序号，从 1 开始；命令列表第一列显示它。 */
  index: number
  /** 所属阶段：spawn 生成假人 / kill 清除假人。 */
  phase: 'spawn' | 'kill'
  /** 关联的假人序号，从 1 开始；从台账恢复的命令没有这个信息，填 0。 */
  bot: number
  /** 假人名；理论上每条命令都有，恢复态或异常数据可能为空串。 */
  name: string
  /** 直接发给游戏的完整命令文本（含 `/execute` 或 `/player` 前缀）。 */
  text: string
  /** 所属批次号（从 1 开始）；未分批或恢复态的命令为 0。 */
  batch: number
}

/**
 * 一个批次的假人区间，用于「每批 24 人」的分批执行。
 */
export interface PlanBatch {
  /** 批次号，从 1 开始。 */
  index: number
  /** 本批起始假人序号（含）。 */
  from: number
  /** 本批结束假人序号（含）。 */
  to: number
  /** 本批人数 = to - from + 1。 */
  count: number
}

/**
 * 一次「生成」得到的完整运单计划。
 *
 * 口径：盒数 → 人数 `ceil(boxes / boxesPerBot)`，再按 `botsPerBatch` 切批，
 * 每人生成一条 spawn 命令、一条 kill 命令。
 */
export interface Plan {
  /** 本张运单的盒数（整数，> 0）。 */
  boxes: number
  /** 需要的假人数 = ceil(盒数 / boxesPerBot)。 */
  bots: number
  /** 一个假人带多少盒（默认 36，等于背包容量，来自设置）。 */
  boxesPerBot: number
  /** 每批人数（默认 24，超过就分批，批与批之间等用户确认）。 */
  botsPerBatch: number
  /** 批次数，等于 batches.length。 */
  waves: number
  /** 每批的假人区间明细。 */
  batches: PlanBatch[]
  /** 全部假人名，下标 0 对应 1 号假人。 */
  names: string[]
  /** 生成阶段的命令，顺序与假人顺序一致。 */
  commands: PlanCommand[]
  /** 清除阶段的命令，与 commands 一一对应。 */
  killCommands: PlanCommand[]
  /** 操作口径：假人在始发地还是目的地生成。 */
  operation: 'spawn_at_origin' | 'spawn_at_dest'
  /** 假人实际生成位置（含分组、维度、坐标）；操作口径决定取始发还是目的站。 */
  spawnStation: { id: string; name: string; dimension: string; x: number; y: number; z: number }
  /** 另一端的站点（生成在始发地时是目的站，反之是始发站），只留 id 与名字。 */
  returnStation: { id: string; name: string }
  /** 耗时估算：perCommand 为单条命令秒数，另两项是两阶段各自的总秒数。 */
  estimate: { perCommand: number; spawnSeconds: number; killSeconds: number }
  /** 生成时生效的设置快照：命令间隔与是否允许自动输入。 */
  settings: { commandInterval: number; allowExecute: boolean }
}

/**
 * 假人生成位置的快照，随运单写进台账。
 *
 * 与 Station 的差别：只保留展示与恢复执行所需的字段，坐标不存；
 * 台账「生成于」列和中断后补 kill 都靠它。
 */
export interface SpawnStation {
  /** 站点 id；为空表示这条快照无效，spawnStationOf 会把它丢弃。 */
  id: string
  /** 站点名字（地名），台账里显示在分组后面；为空时该列显示占位符。 */
  name: string
  /** 分组 tag，可缺省；有值时显示成「分组 · 名称 · 维度」。 */
  group?: string
  /** 维度，用于在台账里补一段维度文案，便于区分同名站点。 */
  dimension: string
}

/**
 * 随一次执行一起保存的元信息：执行结束时写进台账，也用于切回来时接续界面。
 *
 * 注意 origin / dest 存的是站点 **id** 而不是名字，
 * 台账显示时要用站点表反查，查不到才退回显示 id 本身。
 */
export interface RunMeta {
  /** 始发站 id。 */
  origin: string
  /** 目的站 id。 */
  dest: string
  /** 本张运单的盒数。 */
  boxes: number
  /** 本次涉及（或计划涉及）的假人数。 */
  bots: number
  /** 假人名，按生成顺序；中断后按已发送条数截取前缀来补 kill。 */
  names: string[]
  /** 假人生成位置的快照；恢复执行与台账「生成于」列都用它。 */
  spawnStation?: SpawnStation | null
}

/**
 * 一次执行的实时状态，由后端 `run_status` 每 300ms 返回一份完整快照。
 */
export interface RunState {
  /** 执行线程 id，即 `run_start` 返回的 runId；后续 run_continue / run_stop 都带它。 */
  id: string
  /** running 执行中 / done 全部完成 / aborted 被中断 / error 出错 / idle 空闲。 */
  state: 'running' | 'done' | 'aborted' | 'error' | 'idle'
  /** 当前阶段：spawn 生成假人 / kill 清除假人。 */
  phase: 'spawn' | 'kill'
  /** 本次要发送的命令总条数，进度条的分母。 */
  total: number
  /** 已成功发送的条数，进度条的分子。 */
  sent: number
  /** 正在发送的命令序号（从 1 开始）。 */
  index: number
  /** 当前命令文本；界面只显示一行，超出部分省略。 */
  current: string
  /** 日志行；后端只回最近 40 行，够看当前进度即可。 */
  logs: string[]
  /** 开始时间（秒级时间戳）。 */
  startedAt: number
  /** 结束时间；还在跑时为 null。 */
  finishedAt: number | null
  /** 已用秒数，后端按「当前时间或结束时间 - 开始时间」算好。 */
  elapsed: number
  /** 出错信息；正常执行时为空串。 */
  error: string
  /** 这次执行的元信息，结束后原样写进台账。 */
  meta: RunMeta
  /** 每批命令数；0 表示不分批，一次发完。 */
  batchSize?: number
  /** 当前批次号（从 1 开始）；未分批时为 0。 */
  batch?: number
  /** 总批次数；未分批时为 0。 */
  batches?: number
  /** 是否停在批间闸门：为 true 时发送线程在等用户点「继续下一批」。 */
  waiting?: boolean
}

/**
 * 订单区草稿：把上次填好的始发 / 目的 / 数量 / 操作留在本地，下次打开直接恢复。
 */
export interface OrderDraft {
  /** 始发站 id；已被删除的 id 会被后端丢弃，不影响页面加载。 */
  origin: string
  /** 目的站 id；与始发站相同时同样会被丢弃。 */
  dest: string
  /** 盒数（>= 0 的整数）。 */
  boxes: number
  /** 操作口径：假人在始发地还是目的地生成。 */
  operation: 'spawn_at_origin' | 'spawn_at_dest'
  /** 后端写入草稿的时间；前端只透传，不参与计算。 */
  savedAt?: string
}

/**
 * 台账里的一张运单。最多保留 200 条，最早的会被挤掉。
 */
export interface Order {
  /** 台账序号，从 1 递增。 */
  no: number
  /** 记录时分，形如 12:30。 */
  at: string
  /** 记录日期，形如 2026-11-07。 */
  date: string
  /** 始发站 id，显示前用站点表反查名字。 */
  origin: string
  /** 目的站 id。 */
  dest: string
  /** 盒数。 */
  boxes: number
  /** 假人数。 */
  bots: number
  /** 这张运单执行的阶段。 */
  phase: 'spawn' | 'kill'
  /** 结束状态：done / aborted / error 等，直接拼成 i18n key 显示。 */
  state: string
  /** 实际发送条数。 */
  sent: number
  /** 计划发送条数。 */
  total: number
  /** 保存下来的命令文本，最多 200 条；点击台账行可恢复它们。 */
  commands?: string[]
  /** 命令超过 200 条被截断时为 true，此时恢复不完整。 */
  truncated?: boolean
  /** 执行时的元信息（站点 id、盒数、假人名等）。 */
  meta?: RunMeta
  /** 生成位置快照；与 meta.spawnStation 内容相同，旧数据可能只有这一份。 */
  spawnStation?: SpawnStation | null
}

/**
 * 环境自检的一项结果，对应「自检」弹窗里的一行。
 */
export interface DiagnoseCheck {
  /** 检查项标识（如剪贴板、窗口焦点），直接显示在行内。 */
  id: string
  /** true 通过 / false 失败 / null 未知（无法判定）。 */
  ok: boolean | null
  /** 结果说明，失败时通常会给出可以怎么修。 */
  detail: string
}

/**
 * 站点导入的汇总结果：后端识别格式后逐行解析，这里回报各计数。
 */
export interface ImportResult {
  /** 导入后的整张站点表，前端直接整体替换。 */
  stations: Station[]
  /** 识别出的格式名：json（含旧 stops.json）或 lines（纯文本逐行）。 */
  format: string
  /** 新增条数。 */
  added: number
  /** 覆盖同 id 条目的条数。 */
  updated: number
  /** 判定为重复而合并的条数。 */
  duplicated: number
  /** 被跳过的行：source 是行号或站点名，reason 是原因。 */
  skipped: { source: string; reason: string }[]
  /** 非致命提示（例如某行维度无法识别，已回落到默认维度）。 */
  warnings: string[]
}
