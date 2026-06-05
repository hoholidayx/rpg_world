import api from './index'

/**
 * Read the saved OpenAI API key from localStorage.
 * Returns empty string if not set.
 */
function getApiKey() {
  return localStorage.getItem('rpg_openai_api_key') || ''
}

export function getHistory(sessionId = 'default') {
  const headers = {}
  const key = getApiKey()
  if (key) headers['X-OpenAI-Api-Key'] = key
  return api.get('/chat/history', {
    params: { session_id: sessionId },
    headers,
  })
}

export function sendMessage(message, sessionId = 'default') {
  const headers = {}
  const key = getApiKey()
  if (key) headers['X-OpenAI-Api-Key'] = key
  return api.post('/chat/send', { message, session_id: sessionId }, { headers })
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
  const key = getApiKey()
  if (key) headers['X-OpenAI-Api-Key'] = key

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
