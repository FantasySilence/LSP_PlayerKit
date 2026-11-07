/**
 * 前后端共享的数据结构（只含 TypeScript 类型，编译后不产生运行时代码）
 *
 * 字段名与后端返回的 JSON 一一对应：
 * - FieldDef / GroupDef / SchemaDef：设置抽屉据此动态渲染表单；
 * - ColumnDef：通用表格 DataTable 的列定义；
 * - ToolDef：单个工具的描述，App.vue 用它生成工具轨与工作区；
 * - AppState：启动时 app_state 返回的整个应用状态；
 * - StorageInfo：数据目录信息（设置抽屉的“存储”页使用）；
 * - 其余 *Row / *Result：各工具的业务数据形状，供对应工具 View 使用。
 *
 * 修改字段时需同步检查 src/lspkit 中对应的 Python 定义，避免前后端不一致。
 */

// ------ 设置 schema ------ //

/**
 * 一个设置字段的描述符。type 决定设置抽屉渲染成什么控件：
 * - int / float：数字输入框（step 未给出时由类型与 digits 推导）
 * - bool：勾选框
 * - enum：下拉框，候选项来自 options
 * - string：单行文本框
 * - path：单行文本框 + “选择目录”按钮（调后端 storage_pick_dir）
 */
export interface FieldDef {
  // 字段路径，支持点号嵌套，如 flat.xzMotion
  key: string
  // 字段标题的 i18n key
  label: string
  type: 'int' | 'float' | 'bool' | 'enum' | 'string' | 'path'
  // 默认值：后端生成默认设置、重置设置时使用
  default: unknown
  // 数字下限 / 上限；null 表示不限
  min: number | null
  max: number | null
  // 数字输入框的步长；null 表示由前端按类型推导
  step: number | null
  // 小数位数：前端在 step 未给出时用它推导数字输入框的步长
  digits: number
  // 单位文案：可能直接显示，也可能是一个 i18n key（含 '.' 时前端会翻译）
  unit: string
  // enum 的候选项；非 enum 字段为 null
  options: { value: string; label: string }[] | null
  // 字段下方的说明文案（i18n key），空串表示不显示
  hint: string
}

// 设置分组：设置抽屉按组渲染小标题与字段列表
export interface GroupDef {
  id: string
  // 分组标题的 i18n key
  label: string
  fields: FieldDef[]
}

// 一个工具的完整设置结构：version 是设置格式版本号，字段结构变化时递增
// （前端目前只读取 groups，version 暂未参与判断）
export interface SchemaDef {
  version: number
  groups: GroupDef[]
}

// ------ 表格与工具声明 ------ //

/**
 * 表格列定义。
 * type 决定数字列的字体与显示格式：int 取整、float 按 digits 保留小数、string 原样输出。
 */
export interface ColumnDef {
  // 对应数据行里的字段名
  key: string
  // 表头文案的 i18n key
  nameKey: string
  type: 'int' | 'float' | 'string'
  // 浮点列的小数位数；省略时表格用 6 位
  digits?: number
}

// 工具动作声明：id 对应后端注册的处理器，labelKey 是按钮文案的 i18n key
export interface ActionDef {
  id: string
  labelKey: string
}

// 单个工具的完整声明，由后端 manifest 下发，决定侧栏入口与工具视图的元信息
export interface ToolDef {
  // 工具 id，必须与 web/src/tools/<id>/ 目录名一致
  id: string
  // 工具名与描述的 i18n key
  nameKey: string
  descriptionKey: string
  // 图标名，对应 App.vue 里 ICONS 表的键
  icon: string
  // 侧栏排序值，越小越靠前（后端已按它排好序）
  order: number
  // 工具版本号（由后端 manifest 声明）
  version: string
  // 动作清单：每个 id 对应后端注册的一个处理器
  actions: ActionDef[]
  // 结果表格的列定义，供各工具 View 传给 DataTable
  columns: ColumnDef[]
  // 该工具的设置 schema，设置抽屉按它渲染表单
  settingsSchema: SchemaDef
}

// ------ 应用状态 ------ //

// 数据目录信息，设置抽屉的“存储”页展示
export interface StorageInfo {
  // 数据目录绝对路径
  path: string
  // 目录来源：cli / env / portable / user / default / fallback
  source: string
  // 是否为便携模式（由 portable.json 指定）
  portable: boolean
  // 目录当前是否可写
  writable: boolean
  // 备注文案：例如默认目录不可写而回退到用户目录时的说明
  note: string
  // 前端静态资源目录
  webviewDir: string
  // 应用版本号
  version: string
}

// 启动时 app_state 返回的整个应用状态
export interface AppState {
  version: string
  language: string
  theme: 'dark' | 'light'
  // 上次使用的工具 id，启动时优先恢复
  lastTool: string
  // 工具清单，后端已按 order 升序排好
  tools: ToolDef[]
  storage: StorageInfo
}

// ------ 各工具的业务数据 ------ //

// 珍珠炮计算的一行结果：误差、模拟 tick、蓝色/红色 TNT 数量与合计
export interface PearlRow {
  error: number
  ticks: number
  blue: number
  red: number
  total: number
}

// 边境炮计算的一行结果：飞行 tick、三组 TNT 取整数量、动量分量（mx/my/mz）与方向
export interface BorderRow {
  tick: number
  t1: number
  t2: number
  t3: number
  mx: number
  my: number
  mz: number
  // 方向代码（三位字符串，如 000/100，由各工具定义）与已翻译的文案
  dirCode: string
  dirLabel: string
}

// 材料换算：单种材料的一行结果
export interface MaterialRow {
  name: string
  // 该材料的单组堆叠上限
  stack: number
  // 需求总数
  count: number
  // 换算结果：潜影盒数、整组数、零散个数
  shulkers: number
  stacks: number
  items: number
}

// 材料换算：整份清单的合计
export interface MaterialTotals {
  // 材料种数
  kinds: number
  count: number
  shulkers: number
  stacks: number
  items: number
  // 按默认堆叠数与每盒格数算出的单盒容量
  perBox: number
  // 保守估计所需盒数（每种材料的零头各占一盒）
  boxesNeeded: number
}

// 被忽略的材料：name 名称、count 数量、stack 单组上限
export interface MaterialIgnored {
  name: string
  count: number
  stack: number
}

// 多份清单合并时的来源摘要：文件名、材料种数、总个数
export interface MaterialSourceSummary {
  name: string
  kinds: number
  items: number
}

// 材料换算动作的完整返回
export interface MaterialResult {
  items: MaterialRow[]
  totals: MaterialTotals
  ignoredItems: MaterialIgnored[]
  // 解析警告：line 为行号，text 为出问题的原文片段
  warnings: { line: number; text: string }[]
  // 被跳过的条目数（无法解析或数量为 0 的行/条目；空行不计入）
  skipped: number
  // 材料种类超过上限、只保留了先出现的部分时为 true
  truncated: boolean
  sources?: MaterialSourceSummary[]
}

// 装箱结果：单个盒子内某种材料的占用明细
export interface PackingEntry {
  name: string
  // 单组堆叠上限
  stack: number
  // 整组数、零散个数、占用格数、总个数
  stacks: number
  items: number
  slots: number
  count: number
}

// 装好的一个盒子：编号、容量（格）、已用格数与内容
export interface PackingBox {
  index: number
  capacity: number
  used: number
  entries: PackingEntry[]
}

// 连续且满装的单材料盒子合并后的分组：from/to 为盒号区间，merged 表示是否由多盒合并
export interface PackingGroup {
  from: number
  to: number
  boxes: number
  capacity: number
  used: number
  entries: PackingEntry[]
  merged: boolean
}

// 装箱动作的完整返回
export interface PackingResult {
  boxes: PackingBox[]
  groups?: PackingGroup[]
  // 合计：盒数、总占用格数、单盒容量、材料种数
  totals: { boxes: number; slots: number; capacity: number; kinds: number }
  ignoredItems: MaterialIgnored[]
  warnings: { line: number; text: string }[]
  skipped: number
  truncated: boolean
  sources?: MaterialSourceSummary[]
}
