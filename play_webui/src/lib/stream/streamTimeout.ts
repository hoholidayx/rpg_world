// Keep this aligned with agent_service.agent_client.stream_timeout_ms and
// agent_service.llm_client.stream_timeout_ms. The browser owns the visible
// timeout so it can explicitly cancel the matching backend request.
export const PLAY_STREAM_TIMEOUT_MS = 300_000

// Leave a small transport-only grace period after the visible timeout. This
// lets the browser deliver its Stop request before the Next development proxy
// tears down the SSE connection on its own.
export const PLAY_STREAM_PROXY_TIMEOUT_MS = PLAY_STREAM_TIMEOUT_MS + 5_000
