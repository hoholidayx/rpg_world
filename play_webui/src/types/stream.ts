export const PLAY_STREAM_SCHEMA_VERSION = 'play_sse_v1'

export const PLAY_STREAM_EVENT_TYPE = {
  TURN_STARTED: 'turn_started',
  TEXT_DELTA: 'text_delta',
  TOOL_CALL: 'tool_call',
  TOOL_RESULT: 'tool_result',
  TURN_COMPLETED: 'turn_completed',
  ERROR: 'error',
} as const

export type PlayStreamEventType = (typeof PLAY_STREAM_EVENT_TYPE)[keyof typeof PLAY_STREAM_EVENT_TYPE]

export const PLAY_STREAM_EVENT_TYPES = Object.values(PLAY_STREAM_EVENT_TYPE) as PlayStreamEventType[]

export type PlayStreamEnvelope<TType extends PlayStreamEventType, TPayload extends Record<string, unknown>> = {
  schemaVersion: typeof PLAY_STREAM_SCHEMA_VERSION
  eventId: number
  sessionId: string
  turnId: string
  type: TType
  payload: TPayload
}

export type PlayTurnStartedPayload = {
  mode?: string
}

export type PlayTextDeltaPayload = {
  text: string
}

export type PlayToolCallPayload = {
  toolName?: string
  toolArguments?: string
  toolCallId?: string
}

export type PlayToolResultPayload = {
  toolName?: string
  toolResult?: string
  resultPreview?: string
}

export type PlayTurnCompletedPayload = {
  text: string
  usage?: unknown
  model?: string
  finishReason?: string
  durationMs?: number
}

export type PlayStreamErrorPayload = {
  message: string
  statusCode?: number
}

export type PlayStreamEvent =
  | PlayStreamEnvelope<typeof PLAY_STREAM_EVENT_TYPE.TURN_STARTED, PlayTurnStartedPayload>
  | PlayStreamEnvelope<typeof PLAY_STREAM_EVENT_TYPE.TEXT_DELTA, PlayTextDeltaPayload>
  | PlayStreamEnvelope<typeof PLAY_STREAM_EVENT_TYPE.TOOL_CALL, PlayToolCallPayload>
  | PlayStreamEnvelope<typeof PLAY_STREAM_EVENT_TYPE.TOOL_RESULT, PlayToolResultPayload>
  | PlayStreamEnvelope<typeof PLAY_STREAM_EVENT_TYPE.TURN_COMPLETED, PlayTurnCompletedPayload>
  | PlayStreamEnvelope<typeof PLAY_STREAM_EVENT_TYPE.ERROR, PlayStreamErrorPayload>

export type StreamStatus =
  | 'idle'
  | 'connecting'
  | 'streaming'
  | 'thinking'
  | 'tool_running'
  | 'done'
  | 'error'

export const TIMELINE_ITEM_TYPE = {
  USER: 'user',
  ASSISTANT: 'assistant',
  THINKING: 'thinking',
  TOOL: 'tool',
  ERROR: 'error',
  SYSTEM: 'system',
} as const

export type TimelineItemType = (typeof TIMELINE_ITEM_TYPE)[keyof typeof TIMELINE_ITEM_TYPE]

export type TimelineItem = {
  id: string
  type: TimelineItemType
  content: string
  createdAt: string
  metadata?: Record<string, unknown>
}
