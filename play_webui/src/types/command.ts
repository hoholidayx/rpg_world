export type InputMode = 'ic' | 'ooc' | 'gm'

export type CommandMode = InputMode | 'slash'

export type PlayCommand = {
  name: string
  description: string
  mode: CommandMode
}

export type SendMessagePayload = {
  sessionId: string
  text: string
  mode: InputMode
}
