import { createStreamRequest } from '@/lib/api/chat'
import type { SendMessagePayload } from '@/types/command'
import type { CurrentAgentStreamEvent } from '@/types/stream'
import { parseAgentEvent } from './parseAgentEvent'

export async function consumeChatStream(
  payload: SendMessagePayload,
  handlers: {
    signal?: AbortSignal
    onEvent: (event: CurrentAgentStreamEvent) => void
  },
) {
  const response = await createStreamRequest(payload, handlers.signal)
  if (!response.ok || !response.body) throw new Error('无法建立 Play API 流式连接')

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const chunks = buffer.split('\n\n')
    buffer = chunks.pop() ?? ''
    for (const chunk of chunks) {
      const data = chunk
        .split('\n')
        .filter((line) => line.startsWith('data:'))
        .map((line) => line.slice(5).trim())
        .join('\n')
      const event = parseAgentEvent(data)
      if (event) handlers.onEvent(event)
    }
  }
}
