export interface FieldDef {
  key: string
  label: string
  type: 'int' | 'float' | 'bool' | 'enum' | 'string'
  default: unknown
  min: number | null
  max: number | null
  step: number | null
  digits: number
  unit: string
  options: { value: string; label: string }[] | null
  hint: string
}

export interface GroupDef {
  id: string
  label: string
  fields: FieldDef[]
}

export interface SchemaDef {
  version: number
  groups: GroupDef[]
}

export interface ColumnDef {
  key: string
  nameKey: string
  type: 'int' | 'float' | 'string'
  digits?: number
}

export interface ActionDef {
  id: string
  labelKey: string
}

export interface ToolDef {
  id: string
  nameKey: string
  descriptionKey: string
  icon: string
  order: number
  version: string
  actions: ActionDef[]
  columns: ColumnDef[]
  settingsSchema: SchemaDef
}

export interface StorageInfo {
  path: string
  source: string
  portable: boolean
  writable: boolean
  note: string
  webviewDir: string
  version: string
}

export interface AppState {
  version: string
  language: string
  theme: 'dark' | 'light'
  lastTool: string
  tools: ToolDef[]
  storage: StorageInfo
}

export interface PearlRow {
  error: number
  ticks: number
  blue: number
  red: number
  total: number
}

export interface BorderRow {
  tick: number
  t1: number
  t2: number
  t3: number
  mx: number
  my: number
  mz: number
  dirCode: string
  dirLabel: string
}

export interface MaterialRow {
  name: string
  count: number
  shulkers: number
  stacks: number
  items: number
}

export interface MaterialTotals {
  kinds: number
  count: number
  shulkers: number
  stacks: number
  items: number
  perBox: number
  boxesNeeded: number
}

export interface MaterialResult {
  items: MaterialRow[]
  totals: MaterialTotals
  warnings: { line: number; text: string }[]
  skipped: number
  truncated: boolean
}
