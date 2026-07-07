export type InputMode = 'ic' | 'ooc' | 'gm'

export type CommandMode = InputMode | 'slash'

export type PlayCommand = {
  name: string
  description: string
  mode: CommandMode
}

export const TURN_CANCEL_STATUS = {
  CANCELLED: 'cancelled',
  NOT_RUNNING: 'not_running',
  STALE: 'stale',
} as const

export type TurnCancelStatus = (typeof TURN_CANCEL_STATUS)[keyof typeof TURN_CANCEL_STATUS]

export type SendMessagePayload = {
  sessionId: string
  text: string
  mode: InputMode
  requestId?: string
}
