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
  selectionWeight: number
  candidateBatchSize: number
  cooldownMinutes: number
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
  deadlineTime: SceneTimeValue | null
  position: number
  selectionWeight: number
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
  selectionOrigin: 'scheduler' | 'manual'
  sceneTime: SceneTimeValue | null
  sceneTimeOrdinal: number | null
  eventSnapshot: Record<string, unknown>
  reason: string
  errorCode: string
  errorMessage: string
  version: number
  createdAt: string
  updatedAt: string
}

export type PlotPoolCooldown = {
  poolId: number
  cooldownMinutes: number
  status: 'inactive' | 'ready' | 'cooling_down' | 'scene_time_unavailable'
  blocksAutomaticSelection: boolean
  elapsedMinutes: number | null
  remainingMinutes: number | null
  reasonCode: string
  reason: string
  anchorDecisionId: number | null
  anchorTurnId: number | null
  anchorEventId: number | null
  anchorSceneTime: SceneTimeValue | null
}

export type PlotEventBinding = {
  eventId: number
  outlineBound: boolean
  outlineNodeReferenceCount: number
  poolLaneEligibleByBinding: boolean
}

export type SessionPlotSchedule = {
  sessionId: string
  sceneTime: SceneTimeValue | null
  sceneTimeError: string
  schedule: PlotSchedule
  overrides: PlotOverrides
  decisions: PlotScheduleDecision[]
  poolCooldowns: PlotPoolCooldown[]
  eventBindings: PlotEventBinding[]
  nextBeforeId: number | null
}

export type PlotStoryEventDetail = {
  eventId: number
  title: string
  description: string
  directive: string
  suitabilityHint: string
  dispatchMode: PlotDispatchMode
  scheduledTime: SceneTimeValue | null
  deadlineTime: SceneTimeValue | null
  allowRepeat: boolean
  repeatCooldownMinutes: number
  eventEnabled: boolean
}

export type PlotStoryNode = {
  slotKey: string
  position: number
  revealed: boolean
  enabled: boolean
  sessionDisabled: boolean
  eventInjected: boolean
  eventInjectionCount: number
  lastEventInjectionTurnId: number | null
  sourceInjected: boolean
  sourceInjectionCount: number
  lastSourceInjectionTurnId: number | null
  eventDetail: PlotStoryEventDetail | null
}

export type PlotStoryLine = {
  kind: 'outline' | 'pool'
  id: number
  name: string
  description: string
  enabled: boolean
  nodes: PlotStoryNode[]
}

export type SessionPlotStory = {
  sessionId: string
  spoilerProtectionEnabled: boolean
  outlines: PlotStoryLine[]
  pools: PlotStoryLine[]
}

export type PlotPoolInput = {
  name: string
  description: string
  selectionMode: PlotPoolMode
  selectionWeight: number
  candidateBatchSize: number
  cooldownMinutes: number
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
  deadlineTime: SceneTimeValue | null
  selectionWeight: number
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
