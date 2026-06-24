import type { CurrentAgentStreamEvent, StreamStatus, TimelineItem } from '@/types/stream'

type StreamState = {
  timeline: TimelineItem[]
  status: StreamStatus
  debugEvents: CurrentAgentStreamEvent[]
}

function now() {
  return new Date().toISOString()
}

function appendAssistantText(items: TimelineItem[], content: string): TimelineItem[] {
  const last = items.at(-1)
  if (last?.type === 'assistant') {
    return [...items.slice(0, -1), { ...last, content: `${last.content}${content}` }]
  }
  return [...items, { id: crypto.randomUUID(), type: 'assistant', content, createdAt: now() }]
}

export function reduceAgentEvent(state: StreamState, event: CurrentAgentStreamEvent): StreamState {
  const debugEvents = [...state.debugEvents, event]
  switch (event.kind) {
    case 'text':
      return {
        timeline: appendAssistantText(state.timeline, event.content ?? ''),
        status: 'streaming',
        debugEvents,
      }
    case 'thinking':
      return {
        timeline: [
          ...state.timeline,
          { id: crypto.randomUUID(), type: 'thinking', content: event.content ?? '思考中...', createdAt: now() },
        ],
        status: 'thinking',
        debugEvents,
      }
    case 'tool_call':
    case 'tool_result':
      return {
        timeline: [
          ...state.timeline,
          {
            id: crypto.randomUUID(),
            type: 'tool',
            content: event.tool_result_preview ?? event.tool_name ?? '工具事件',
            createdAt: now(),
            metadata: { event },
          },
        ],
        status: 'tool_running',
        debugEvents,
      }
    case 'done':
      return { ...state, status: 'done', debugEvents }
    case 'error':
      return {
        timeline: [
          ...state.timeline,
          { id: crypto.randomUUID(), type: 'error', content: event.content ?? '流式请求失败', createdAt: now() },
        ],
        status: 'error',
        debugEvents,
      }
    default:
      return { ...state, debugEvents }
  }
}

export function createInitialStreamState(): StreamState {
  return { timeline: [], status: 'idle', debugEvents: [] }
}
