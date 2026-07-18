export const PLAY_EVENT_SCHEMA_VERSION = 'play_event_v1' as const

export type PlayEventConnectionStatus = 'connecting' | 'open' | 'disconnected'
export type PlayEventTerminalStatus = 'ready' | 'failed' | 'interrupted'

export type DreamProposalTerminalPayload = {
  proposalId: string
  depth: 'shallow' | 'deep'
  scope: 'incremental' | 'full'
  status: PlayEventTerminalStatus
  errorCode: string
  errorMessage: string
  finishedAt: string
  updatedAt: string
}

export type SessionDerivationTerminalPayload = {
  jobId: string
  sourceSessionId: string
  targetSessionId: string | null
  turnId: number
  status: PlayEventTerminalStatus
  errorCode: string
  errorMessage: string
  contextThresholdExceeded: boolean
  finishedAt: string
  updatedAt: string
}

type PlayEventBase = {
  schemaVersion: typeof PLAY_EVENT_SCHEMA_VERSION
  eventId: string
  publishedAt: string
  sessionId: string
}

export type DreamProposalTerminalEvent = PlayEventBase & {
  eventType: 'dream.proposal.terminal'
  payload: DreamProposalTerminalPayload
}

export type SessionDerivationTerminalEvent = PlayEventBase & {
  eventType: 'session.derivation.terminal'
  payload: SessionDerivationTerminalPayload
}

export type PlayEvent =
  | DreamProposalTerminalEvent
  | SessionDerivationTerminalEvent

const ENVELOPE_KEYS = [
  'schemaVersion',
  'eventId',
  'eventType',
  'publishedAt',
  'sessionId',
  'payload',
] as const

const DREAM_KEYS = [
  'proposalId',
  'depth',
  'scope',
  'status',
  'errorCode',
  'errorMessage',
  'finishedAt',
  'updatedAt',
] as const

const DERIVATION_KEYS = [
  'jobId',
  'sourceSessionId',
  'targetSessionId',
  'turnId',
  'status',
  'errorCode',
  'errorMessage',
  'contextThresholdExceeded',
  'finishedAt',
  'updatedAt',
] as const

export function parsePlayEvent(raw: unknown): PlayEvent | null {
  if (!isRecord(raw) || !hasExactKeys(raw, ENVELOPE_KEYS)) return null
  if (raw.schemaVersion !== PLAY_EVENT_SCHEMA_VERSION) return null
  if (!isUuid(raw.eventId) || !isText(raw.publishedAt) || !isText(raw.sessionId)) return null

  if (raw.eventType === 'dream.proposal.terminal') {
    const payload = parseDreamPayload(raw.payload)
    if (payload === null) return null
    return {
      schemaVersion: PLAY_EVENT_SCHEMA_VERSION,
      eventId: raw.eventId,
      eventType: raw.eventType,
      publishedAt: raw.publishedAt,
      sessionId: raw.sessionId,
      payload,
    }
  }

  if (raw.eventType === 'session.derivation.terminal') {
    const payload = parseDerivationPayload(raw.payload)
    if (payload === null || payload.sourceSessionId !== raw.sessionId) return null
    return {
      schemaVersion: PLAY_EVENT_SCHEMA_VERSION,
      eventId: raw.eventId,
      eventType: raw.eventType,
      publishedAt: raw.publishedAt,
      sessionId: raw.sessionId,
      payload,
    }
  }

  return null
}

function parseDreamPayload(raw: unknown): DreamProposalTerminalPayload | null {
  if (!isRecord(raw) || !hasExactKeys(raw, DREAM_KEYS)) return null
  if (
    !isText(raw.proposalId)
    || (raw.depth !== 'shallow' && raw.depth !== 'deep')
    || (raw.scope !== 'incremental' && raw.scope !== 'full')
    || !isTerminalStatus(raw.status)
    || typeof raw.errorCode !== 'string'
    || typeof raw.errorMessage !== 'string'
    || !isText(raw.finishedAt)
    || !isText(raw.updatedAt)
  ) return null
  return raw as DreamProposalTerminalPayload
}

function parseDerivationPayload(raw: unknown): SessionDerivationTerminalPayload | null {
  if (!isRecord(raw) || !hasExactKeys(raw, DERIVATION_KEYS)) return null
  if (
    !isText(raw.jobId)
    || !isText(raw.sourceSessionId)
    || (raw.targetSessionId !== null && !isText(raw.targetSessionId))
    || !Number.isInteger(raw.turnId)
    || (raw.turnId as number) <= 0
    || !isTerminalStatus(raw.status)
    || typeof raw.errorCode !== 'string'
    || typeof raw.errorMessage !== 'string'
    || typeof raw.contextThresholdExceeded !== 'boolean'
    || !isText(raw.finishedAt)
    || !isText(raw.updatedAt)
  ) return null
  return raw as SessionDerivationTerminalPayload
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function hasExactKeys(
  value: Record<string, unknown>,
  expected: readonly string[],
) {
  const keys = Object.keys(value)
  return keys.length === expected.length && expected.every((key) => key in value)
}

function isText(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0
}

function isUuid(value: unknown): value is string {
  return typeof value === 'string'
    && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value)
}

function isTerminalStatus(value: unknown): value is PlayEventTerminalStatus {
  return value === 'ready' || value === 'failed' || value === 'interrupted'
}
