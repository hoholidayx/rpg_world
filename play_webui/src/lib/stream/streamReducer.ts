import { PLAY_STREAM_EVENT_TYPE, TIMELINE_ITEM_TYPE, type PlayStreamEvent, type StreamStatus, type TimelineItem } from '@/types/stream'

type StreamState = {
  timeline: TimelineItem[]
  status: StreamStatus
  debugEvents: PlayStreamEvent[]
}

function now() {
  return new Date().toISOString()
}

function appendAssistantText(items: TimelineItem[], content: string): TimelineItem[] {
  const last = items.at(-1)
  if (last?.type === TIMELINE_ITEM_TYPE.ASSISTANT) {
    return [...items.slice(0, -1), { ...last, content: `${last.content}${content}` }]
  }
  return [...items, { id: crypto.randomUUID(), type: TIMELINE_ITEM_TYPE.ASSISTANT, content, createdAt: now() }]
}

export function reducePlayStreamEvent(state: StreamState, event: PlayStreamEvent): StreamState {
  const debugEvents = [...state.debugEvents, event]
  switch (event.type) {
    case PLAY_STREAM_EVENT_TYPE.TURN_STARTED:
      return { ...state, status: 'connecting', debugEvents }
    case PLAY_STREAM_EVENT_TYPE.TEXT_DELTA:
      return {
        timeline: appendAssistantText(state.timeline, event.payload.text),
        status: 'streaming',
        debugEvents,
      }
    case PLAY_STREAM_EVENT_TYPE.TOOL_CALL:
    case PLAY_STREAM_EVENT_TYPE.TOOL_RESULT: {
      const toolContent = event.type === PLAY_STREAM_EVENT_TYPE.TOOL_RESULT
        ? event.payload.resultPreview ?? event.payload.toolResult ?? event.payload.toolName ?? '工具事件'
        : event.payload.toolArguments ?? event.payload.toolName ?? '工具事件'
      return {
        timeline: [
          ...state.timeline,
          {
            id: crypto.randomUUID(),
            type: TIMELINE_ITEM_TYPE.TOOL,
            content: toolContent,
            createdAt: now(),
            metadata: { event },
          },
        ],
        status: 'tool_running',
        debugEvents,
      }
    }
    case PLAY_STREAM_EVENT_TYPE.TURN_COMPLETED:
      return {
        timeline: state.timeline.length > 0
          ? state.timeline.map((item, index) =>
              index === state.timeline.length - 1 && item.type === TIMELINE_ITEM_TYPE.ASSISTANT
                ? { ...item, content: item.content || event.payload.text, metadata: event.payload.metadata }
                : item,
            )
          : appendAssistantText(state.timeline, event.payload.text || '已完成。'),
        status: 'done',
        debugEvents,
      }
    case PLAY_STREAM_EVENT_TYPE.ERROR:
      return {
        timeline: [
          ...state.timeline,
          { id: crypto.randomUUID(), type: TIMELINE_ITEM_TYPE.ERROR, content: event.payload.message || '流式请求失败', createdAt: now() },
        ],
        status: 'error',
        debugEvents,
      }
  }
}

export function createInitialStreamState(): StreamState {
  return { timeline: [], status: 'idle', debugEvents: [] }
}
