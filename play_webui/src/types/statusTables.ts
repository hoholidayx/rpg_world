export type StatusKind = 'scene' | 'normal'

export type StatusOrigin = 'template_copy' | 'session_native'

export type StatusRow = {
  key: string
  value: string
  runtimeKeyLocked: boolean
  metadata: Record<string, unknown>
}

export type StatusTable = {
  id: number
  name: string
  statusKind: StatusKind
  description: string
  keyColumn: string
  valueColumn: string
  rows: StatusRow[]
  metadata: Record<string, unknown>
  sortOrder: number
  version: number
  createdAt?: string | null
  updatedAt?: string | null
  workspaceId?: string | null
  sessionId?: string | null
  storyId?: number | null
  sourceTableId?: number | null
  origin?: StatusOrigin | null
}

export type StoryStatusMount = {
  id: number
  workspaceId: string
  storyId: number
  statusTableId: number
  tableName: string
  statusKind: StatusKind
  description: string
  sortOrder: number
  metadata: Record<string, unknown>
  version: number
  createdAt?: string | null
  updatedAt?: string | null
}

export type StatusTableInput = {
  name: string
  statusKind: StatusKind
  description?: string
  keyColumn?: string
  valueColumn?: string
  rows?: StatusRow[]
  metadata?: Record<string, unknown>
  sortOrder?: number
}

export type StatusTablePatch = {
  name?: string
  description?: string
  keyColumn?: string
  valueColumn?: string
  rows?: StatusRow[]
  metadata?: Record<string, unknown>
  sortOrder?: number
}
