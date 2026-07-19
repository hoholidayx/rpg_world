export const PLOT_DISPATCH_MODE = {
  FORCED: 'forced',
  SOFT: 'soft',
} as const

export const PLOT_POOL_MODE = {
  RANDOM: 'random',
  SEQUENTIAL: 'sequential',
} as const

export type PlotDispatchMode = (typeof PLOT_DISPATCH_MODE)[keyof typeof PLOT_DISPATCH_MODE]
export type PlotPoolMode = (typeof PLOT_POOL_MODE)[keyof typeof PLOT_POOL_MODE]

export type SceneTimeValue = {
  year: number
  month: number
  day: number
  hour: number
  minute: number
}

export type PlotEventPool = {
  id: number
  storyId: number
  name: string
  description: string
  selectionMode: PlotPoolMode
  priority: number
  enabled: boolean
  version: number
  createdAt: string
  updatedAt: string
}

export type PlotEvent = {
  id: number
  storyId: number
  poolId: number
  title: string
  directive: string
  description: string
  suitabilityHint: string
  dispatchMode: PlotDispatchMode
  scheduledTime: SceneTimeValue | null
  position: number
  enabled: boolean
  allowRepeat: boolean
  repeatCooldownMinutes: number
  version: number
  createdAt: string
  updatedAt: string
}

export type PlotOutlineNode = {
  id: number
  storyId: number
  outlineId: number
  eventId: number
  scheduledTime: SceneTimeValue
  dispatchMode: PlotDispatchMode
  position: number
  enabled: boolean
  version: number
  createdAt: string
  updatedAt: string
}

export type PlotOutline = {
  id: number
  storyId: number
  name: string
  description: string
  priority: number
  enabled: boolean
  nodes: PlotOutlineNode[]
  version: number
  createdAt: string
  updatedAt: string
}

export type PlotSchedule = {
  storyId: number
  pools: PlotEventPool[]
  events: PlotEvent[]
  outlines: PlotOutline[]
}

export type PlotOverrides = {
  sessionId: string
  disabledEventIds: number[]
  disabledOutlineNodeIds: number[]
}

export type PlotScheduleDecision = {
  id: number
  sessionId: string
  turnId: number
  sourceKind: 'outline' | 'pool'
  sourceId: number
  eventId: number
  containerId: number
  decisionStatus: 'triggered' | 'deferred' | 'error'
  dispatchMode: PlotDispatchMode
  sceneTime: SceneTimeValue
  sceneTimeOrdinal: number
  eventSnapshot: Record<string, unknown>
  reason: string
  errorCode: string
  errorMessage: string
  createdAt: string
}

export type SessionPlotSchedule = {
  sessionId: string
  sceneTime: SceneTimeValue | null
  sceneTimeError: string
  schedule: PlotSchedule
  overrides: PlotOverrides
  decisions: PlotScheduleDecision[]
  nextBeforeId: number | null
}

export type PlotPoolInput = {
  name: string
  description: string
  selectionMode: PlotPoolMode
  priority: number
  enabled: boolean
}

export type PlotEventInput = {
  poolId: number
  title: string
  directive: string
  description: string
  suitabilityHint: string
  dispatchMode: PlotDispatchMode
  scheduledTime: SceneTimeValue | null
  enabled: boolean
  allowRepeat: boolean
  repeatCooldownMinutes: number
}

export type PlotOutlineInput = {
  name: string
  description: string
  priority: number
  enabled: boolean
}

export type PlotNodeInput = {
  eventId: number
  scheduledTime: SceneTimeValue
  dispatchMode: PlotDispatchMode
  enabled: boolean
}
