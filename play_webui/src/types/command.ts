export type InputMode = 'ic' | 'ooc' | 'gm' | 'slash'

export type PlayCommand = {
  name: string
  description: string
  mode: InputMode | 'slash'
}

export type SendMessagePayload = {
  sessionId: string
  text: string
  mode: InputMode
}
