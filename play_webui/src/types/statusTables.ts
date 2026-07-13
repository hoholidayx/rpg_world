export const STATUS_KIND = {
  SCENE: 'scene',
  NORMAL: 'normal',
} as const

export type StatusKind = (typeof STATUS_KIND)[keyof typeof STATUS_KIND]

export const STATUS_ORIGIN = {
  TEMPLATE_COPY: 'template_copy',
  SESSION_NATIVE: 'session_native',
} as const

export type StatusOrigin = (typeof STATUS_ORIGIN)[keyof typeof STATUS_ORIGIN]

export const STATUS_UPDATE_FREQUENCY = {
  REALTIME: 'realtime',
  EVENT_DRIVEN: 'event_driven',
  DEFERRED: 'deferred',
  MANUAL: 'manual',
} as const

export type StatusUpdateFrequency = (typeof STATUS_UPDATE_FREQUENCY)[keyof typeof STATUS_UPDATE_FREQUENCY]

export const STORY_STATUS_MOUNT_ORIGIN = {
  SYSTEM: 'system_mount',
  STORY_TEMPLATE: 'story_template',
} as const

export type StoryStatusMountOrigin = (typeof STORY_STATUS_MOUNT_ORIGIN)[keyof typeof STORY_STATUS_MOUNT_ORIGIN]

export type StatusRow = {
  key: string
  value: string
  runtimeKeyLocked: boolean
  metadata: Record<string, unknown>
  updateFrequency: StatusUpdateFrequency
  updateRule: string
  deferredIntervalTurns: number | null
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
  characterMountId: number | null
  mountOrigin: StoryStatusMountOrigin
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

export type StoryStatusTemplateInput = StatusTableInput & {
  characterMountId?: number | null
}

export type StoryStatusMountPatch = {
  characterMountId: number | null
}
