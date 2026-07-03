export type ContextPreviewTotals = {
  layerCount: number
  activeLayers: number
  tokenCount: number
  messageCount: number
}

export type ContextPreviewLayer = {
  index: number
  type: string
  role: string
  status: string
  charCount: number
  tokenCount: number
  description: string
  content: string
  [key: string]: unknown
}

export type ContextPreviewMessage = {
  role: string
  content: string
  uid?: number
  turn_id?: number
  seq_in_turn?: number
  tool_call_id?: string
  tool_calls?: unknown[]
  [key: string]: unknown
}

export type ContextPreviewPayload = {
  formatVersion: string
  sessionId: string
  hotHistoryRounds?: number | null
  totals: ContextPreviewTotals
  layers: ContextPreviewLayer[]
  messages: ContextPreviewMessage[]
  [key: string]: unknown
}
