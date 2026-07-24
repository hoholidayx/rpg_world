export const STATUS_KIND = {
  SCENE: 'scene',
  NORMAL: 'normal',
} as const

export type StatusKind = (typeof STATUS_KIND)[keyof typeof STATUS_KIND]

export const STATUS_ORIGIN = {
  STORY_COPY: 'story_copy',
  SESSION_NATIVE: 'session_native',
} as const

export type StatusOrigin = (typeof STATUS_ORIGIN)[keyof typeof STATUS_ORIGIN]

export type StatusRow = {
  key: string
  value: string
  runtimeKeyLocked: boolean
  updateRule: string
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
  storyCharacterId?: number | null
  sourceStoryStatusTableId?: number | null
  origin?: StatusOrigin | null
}

export type StatusTableInput = {
  name: string
  statusKind: StatusKind
  storyCharacterId?: number | null
  description?: string
  keyColumn?: string
  valueColumn?: string
  rows?: StatusRow[]
  metadata?: Record<string, unknown>
  sortOrder?: number
}

export type StatusTablePatch = {
  name?: string
  statusKind?: StatusKind
  storyCharacterId?: number | null
  description?: string
  keyColumn?: string
  valueColumn?: string
  rows?: StatusRow[]
  metadata?: Record<string, unknown>
  sortOrder?: number
}
