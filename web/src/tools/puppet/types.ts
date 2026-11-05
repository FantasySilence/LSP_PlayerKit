export interface Station {
  id: string
  name: string
  group: string
  prefix: string
  dimension: string
  x: number
  y: number
  z: number
  note?: string
}

export interface PlanCommand {
  index: number
  phase: 'spawn' | 'kill'
  bot: number
  name: string
  text: string
  batch: number
}

export interface PlanBatch {
  index: number
  from: number
  to: number
  count: number
}

export interface Plan {
  boxes: number
  bots: number
  boxesPerBot: number
  botsPerBatch: number
  waves: number
  batches: PlanBatch[]
  names: string[]
  commands: PlanCommand[]
  killCommands: PlanCommand[]
  operation: 'spawn_at_origin' | 'spawn_at_dest'
  spawnStation: { id: string; name: string; dimension: string; x: number; y: number; z: number }
  returnStation: { id: string; name: string }
  estimate: { perCommand: number; spawnSeconds: number; killSeconds: number }
  settings: { commandInterval: number; allowExecute: boolean }
}

export interface SpawnStation {
  id: string
  name: string
  group?: string
  dimension: string
}

export interface RunMeta {
  origin: string
  dest: string
  boxes: number
  bots: number
  names: string[]
  spawnStation?: SpawnStation | null
}

export interface RunState {
  id: string
  state: 'running' | 'done' | 'aborted' | 'error' | 'idle'
  phase: 'spawn' | 'kill'
  total: number
  sent: number
  index: number
  current: string
  logs: string[]
  startedAt: number
  finishedAt: number | null
  elapsed: number
  error: string
  meta: RunMeta
}

export interface Order {
  no: number
  at: string
  date: string
  origin: string
  dest: string
  boxes: number
  bots: number
  phase: 'spawn' | 'kill'
  state: string
  sent: number
  total: number
  commands?: string[]
  truncated?: boolean
  meta?: RunMeta
  spawnStation?: SpawnStation | null
}

export interface DiagnoseCheck {
  id: string
  ok: boolean | null
  detail: string
}

export interface ImportResult {
  stations: Station[]
  format: string
  added: number
  updated: number
  duplicated: number
  skipped: { source: string; reason: string }[]
  warnings: string[]
}
