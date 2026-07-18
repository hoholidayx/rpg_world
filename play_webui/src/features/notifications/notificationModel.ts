import type { PlayEvent, PlayEventTerminalStatus } from '@/features/events/playEvents'

export type NotificationCategory = 'dream' | 'session_derivation'

export type NotificationEntry = {
  id: string
  category: NotificationCategory
  status: PlayEventTerminalStatus
  title: string
  description: string
  detail: string | null
  occurredAt: string
  sessionId: string
}

export function toNotificationEntry(event: PlayEvent): NotificationEntry {
  if (event.eventType === 'dream.proposal.terminal') {
    const depthLabel = event.payload.depth === 'shallow' ? '浅睡' : '深睡'
    const scopeLabel = event.payload.scope === 'incremental' ? '增量归纳' : '全量归纳'

    return {
      id: event.eventId,
      category: 'dream',
      status: event.payload.status,
      title: dreamTitle(depthLabel, event.payload.status),
      description: `${scopeLabel} · 会话 ${event.sessionId}`,
      detail: errorDetail(event.payload.errorCode, event.payload.errorMessage),
      occurredAt: validTimestampOrFallback(event.payload.finishedAt, event.publishedAt),
      sessionId: event.sessionId,
    }
  }

  const targetDescription = event.payload.targetSessionId
    ? `源会话 ${event.payload.sourceSessionId} → 分支会话 ${event.payload.targetSessionId}`
    : `源会话 ${event.payload.sourceSessionId} · Turn ${event.payload.turnId}`
  const thresholdDetail = event.payload.contextThresholdExceeded
    ? '源会话上下文已达到复制阈值。'
    : null

  return {
    id: event.eventId,
    category: 'session_derivation',
    status: event.payload.status,
    title: derivationTitle(event.payload.status),
    description: targetDescription,
    detail: joinDetails(
      thresholdDetail,
      errorDetail(event.payload.errorCode, event.payload.errorMessage),
    ),
    occurredAt: validTimestampOrFallback(event.payload.finishedAt, event.publishedAt),
    sessionId: event.sessionId,
  }
}

export function formatNotificationTime(value: string) {
  const timestamp = Date.parse(value)
  if (Number.isNaN(timestamp)) return '时间未知'

  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(new Date(timestamp))
}

function dreamTitle(depthLabel: string, status: PlayEventTerminalStatus) {
  if (status === 'ready') return `${depthLabel}记忆提案已生成`
  if (status === 'failed') return `${depthLabel}记忆提案生成失败`
  return `${depthLabel}记忆提案生成已中断`
}

function derivationTitle(status: PlayEventTerminalStatus) {
  if (status === 'ready') return '会话分支已就绪'
  if (status === 'failed') return '会话分支创建失败'
  return '会话分支创建已中断'
}

function errorDetail(errorCode: string, errorMessage: string) {
  const code = errorCode.trim()
  const message = errorMessage.trim()
  if (message && code) return `${message}（${code}）`
  return message || code || null
}

function joinDetails(...details: Array<string | null>) {
  const values = details.filter((detail): detail is string => Boolean(detail))
  return values.length ? values.join(' ') : null
}

function validTimestampOrFallback(value: string, fallback: string) {
  return Number.isNaN(Date.parse(value)) ? fallback : value
}
