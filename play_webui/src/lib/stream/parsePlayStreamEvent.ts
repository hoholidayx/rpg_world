import {
  PLAY_STREAM_EVENT_TYPE,
  PLAY_STREAM_EVENT_TYPES,
  PLAY_STREAM_SCHEMA_VERSION,
  type PlayStreamEvent,
  type PlayStreamEventType,
} from '@/types/stream'
import { DEFAULT_STREAM_ERROR_MESSAGE } from './formatStreamError'

const PLAY_EVENT_TYPES = new Set<PlayStreamEventType>(PLAY_STREAM_EVENT_TYPES)

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === 'object' && !Array.isArray(value))
}

function parseError(message: string, raw: string, cause?: unknown): Error {
  return new Error(`${message}；原始 data: ${raw}`, cause === undefined ? undefined : { cause })
}

function assertOptionalString(payload: Record<string, unknown>, key: string, type: PlayStreamEventType, raw: string) {
  const value = payload[key]
  if (value !== undefined && typeof value !== 'string') {
    throw parseError(`Play SSE ${type}.payload.${key} 必须是 string`, raw)
  }
}

function assertRequiredString(payload: Record<string, unknown>, key: string, type: PlayStreamEventType, raw: string) {
  if (typeof payload[key] !== 'string') {
    throw parseError(`Play SSE ${type}.payload.${key} 缺失或无效`, raw)
  }
}

function normalizeStatusCode(value: unknown): number | undefined {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value)
    if (Number.isFinite(parsed)) return parsed
  }
  return undefined
}

function normalizePayload(type: PlayStreamEventType, payload: Record<string, unknown>): Record<string, unknown> {
  if (type !== PLAY_STREAM_EVENT_TYPE.ERROR) return payload

  const normalized: Record<string, unknown> = { ...payload }
  normalized.message = String(payload.message ?? DEFAULT_STREAM_ERROR_MESSAGE)

  if (payload.errorCode !== undefined && payload.errorCode !== null && payload.errorCode !== '') {
    normalized.errorCode = String(payload.errorCode)
  } else {
    delete normalized.errorCode
  }

  const statusCode = normalizeStatusCode(payload.statusCode)
  if (statusCode !== undefined) {
    normalized.statusCode = statusCode
  } else {
    delete normalized.statusCode
  }
  return normalized
}

function validatePayload(type: PlayStreamEventType, payload: Record<string, unknown>, raw: string) {
  switch (type) {
    case PLAY_STREAM_EVENT_TYPE.TURN_STARTED:
      assertOptionalString(payload, 'mode', type, raw)
      return
    case PLAY_STREAM_EVENT_TYPE.THINKING_DELTA:
      assertRequiredString(payload, 'text', type, raw)
      return
    case PLAY_STREAM_EVENT_TYPE.TEXT_DELTA:
      assertRequiredString(payload, 'text', type, raw)
      return
    case PLAY_STREAM_EVENT_TYPE.TOOL_CALL:
      assertOptionalString(payload, 'toolName', type, raw)
      assertOptionalString(payload, 'toolArguments', type, raw)
      assertOptionalString(payload, 'toolCallId', type, raw)
      return
    case PLAY_STREAM_EVENT_TYPE.TOOL_RESULT:
      assertOptionalString(payload, 'toolName', type, raw)
      assertOptionalString(payload, 'toolResult', type, raw)
      assertOptionalString(payload, 'resultPreview', type, raw)
      return
    case PLAY_STREAM_EVENT_TYPE.TURN_COMPLETED:
      assertRequiredString(payload, 'text', type, raw)
      assertOptionalString(payload, 'model', type, raw)
      assertOptionalString(payload, 'finishReason', type, raw)
      if (payload.durationMs !== undefined && typeof payload.durationMs !== 'number') {
        throw parseError(`Play SSE ${type}.payload.durationMs 必须是 number`, raw)
      }
      if (payload.usage !== undefined && !isRecord(payload.usage)) {
        throw parseError(`Play SSE ${type}.payload.usage 必须是 object`, raw)
      }
      return
    case PLAY_STREAM_EVENT_TYPE.ERROR:
      assertRequiredString(payload, 'message', type, raw)
      assertOptionalString(payload, 'errorCode', type, raw)
      return
  }
}

export function parsePlayStreamEvent(raw: string): PlayStreamEvent | null {
  const trimmed = raw.trim()
  if (!trimmed || trimmed === '[DONE]') return null

  let parsed: unknown
  try {
    parsed = JSON.parse(trimmed)
  } catch (error) {
    throw parseError('无法解析 Play SSE 事件', raw, error)
  }

  if (!isRecord(parsed)) throw parseError('Play SSE 事件必须是 JSON object', raw)
  if (parsed.schemaVersion !== PLAY_STREAM_SCHEMA_VERSION) {
    throw parseError('Play SSE 协议版本不匹配', raw)
  }
  if (typeof parsed.eventId !== 'number') throw parseError('Play SSE eventId 缺失或无效', raw)
  if (typeof parsed.sessionId !== 'string') throw parseError('Play SSE sessionId 缺失或无效', raw)
  if (typeof parsed.turnId !== 'string') throw parseError('Play SSE turnId 缺失或无效', raw)
  if (typeof parsed.type !== 'string' || !PLAY_EVENT_TYPES.has(parsed.type as PlayStreamEventType)) {
    throw parseError('Play SSE type 缺失或无效', raw)
  }
  if (!isRecord(parsed.payload)) throw parseError('Play SSE payload 缺失或无效', raw)
  const type = parsed.type as PlayStreamEventType
  const payload = normalizePayload(type, parsed.payload)
  validatePayload(type, payload, raw)

  return { ...parsed, type, payload } as PlayStreamEvent
}
