import type { CurrentAgentStreamEvent } from '@/types/stream'

export function parseAgentEvent(raw: string): CurrentAgentStreamEvent | null {
  const trimmed = raw.trim()
  if (!trimmed || trimmed === '[DONE]') return null
  return JSON.parse(trimmed) as CurrentAgentStreamEvent
}
