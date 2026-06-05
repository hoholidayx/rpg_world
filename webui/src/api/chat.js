import api from './index'

export function getHistory(sessionId = 'default') {
  return api.get('/chat/history', { params: { session_id: sessionId } })
}

export function sendMessage(message, sessionId = 'default') {
  return api.post('/chat/send', { message, session_id: sessionId })
}

/**
 * Stream a chat message via SSE (Server-Sent Events) using fetch + ReadableStream.
 *
 * @param {string} message
 * @param {string} sessionId
 * @param {(event: object) => void} onEvent - callback for each parsed SSE event
 * @returns {() => void} abort function to cancel the stream
 */
export function streamMessage(message, sessionId = 'default', onEvent) {
  const controller = new AbortController()

  const headers = { 'Content-Type': 'application/json' }
  // Dynamic base URL — supports both Vite proxy (dev) and production
  const base = import.meta.env.DEV ? '' : `${import.meta.env.VITE_API_BASE || ''}`
  const url = `${base}/api/v1/chat/stream`

  fetch(url, {
    method: 'POST',
    headers,
    body: JSON.stringify({ message, session_id: sessionId }),
    signal: controller.signal,
  })
    .then(async (response) => {
      if (!response.ok) {
        const text = await response.text().catch(() => '')
        onEvent({ kind: 'error', content: `HTTP ${response.status}: ${text}` })
        return
      }
      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              onEvent(JSON.parse(line.slice(6)))
            } catch {
              // skip malformed JSON lines
            }
          }
        }
      }
    })
    .catch((err) => {
      if (err.name !== 'AbortError') {
        onEvent({ kind: 'error', content: err.message })
      }
    })

  return () => controller.abort()
}
