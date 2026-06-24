export type CurrentAgentStreamEvent = {
  kind:
    | 'text'
    | 'thinking'
    | 'tool_call'
    | 'tool_result'
    | 'round_start'
    | 'round_end'
    | 'done'
    | 'error'
  content?: string
  tool_name?: string
  tool_arguments?: string
  tool_result_preview?: string
  round_index?: number
  usage?: unknown
  model?: string
  finish_reason?: string
  duration_ms?: number
}

export type StreamStatus =
  | 'idle'
  | 'connecting'
  | 'streaming'
  | 'thinking'
  | 'tool_running'
  | 'done'
  | 'error'

export type TimelineItem = {
  id: string
  type: 'user' | 'assistant' | 'thinking' | 'tool' | 'error' | 'system'
  content: string
  createdAt: string
  metadata?: Record<string, unknown>
}
