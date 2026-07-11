import { HISTORY_MESSAGE_ROLE, type SessionPlayerCharacter, type Turn } from '@/types/session'
import {
  NARRATIVE_OUTCOME_CODES,
  type NarrativeOutcome,
  type NarrativeOutcomeCode,
} from '@/types/narrativeOutcome'
import {
  firstLetter,
  stripLeadingSceneBlock,
} from './sessionRoomHelpers'
import {
  SESSION_MESSAGE_STATUS,
  SESSION_TIMELINE_ROLE,
  type SessionSpeaker,
  type SessionTimelineMessage,
} from './sessionRoomTypes'

export const stoppedStreamText = '已停止当前流式响应。'

type HistoryMessage = Turn['messages'][number]

export type UserTimelineMessage = SessionTimelineMessage & { role: typeof SESSION_TIMELINE_ROLE.USER }

export function makePlayerSpeaker(character: SessionPlayerCharacter | null): SessionSpeaker {
  return {
    name: character?.name ?? '你',
    label: 'IC',
    avatarUrl: character?.avatarUrl ?? '',
    fallback: firstLetter(character?.name ?? '你'),
    tone: 'player',
  }
}

export function makeAssistantSpeaker(): SessionSpeaker {
  // Assistant output is currently one mixed narrative block. Character-level
  // avatars need a future structured segments layer instead of speaker metadata.
  return {
    name: '叙事者',
    avatarUrl: '',
    fallback: '叙',
    tone: 'assistant',
  }
}

export function toolSpeaker(): SessionSpeaker {
  return {
    name: '工具结果',
    fallback: '⚒',
    tone: 'tool',
  }
}

export function outcomeSpeaker(): SessionSpeaker {
  return {
    name: '剧情裁定',
    fallback: '分',
    tone: 'outcome',
  }
}

export function commandSpeaker(): SessionSpeaker {
  return {
    name: '命令结果',
    fallback: '⌘',
    tone: 'system',
  }
}

export function thinkingSpeaker(): SessionSpeaker {
  return {
    name: '思考',
    fallback: '思',
    tone: 'thinking',
  }
}

export function errorSpeaker(): SessionSpeaker {
  return {
    name: '错误',
    fallback: '!',
    tone: 'error',
  }
}

function systemSpeaker(): SessionSpeaker {
  return {
    name: '系统',
    fallback: 'S',
    tone: 'system',
  }
}

export function streamPlaceholder(turnId: number): SessionTimelineMessage {
  return {
    id: `local-stream-${turnId}-${crypto.randomUUID()}`,
    turnId,
    seqInTurn: 2,
    role: SESSION_TIMELINE_ROLE.ASSISTANT,
    content: '',
    createdAt: new Date().toISOString(),
    speaker: makeAssistantSpeaker(),
    status: SESSION_MESSAGE_STATUS.STREAMING,
    canCopy: false,
    canRetry: false,
    canEdit: false,
    canDelete: false,
  }
}

function timelineRole(role: HistoryMessage['role']): SessionTimelineMessage['role'] {
  if (
    role === HISTORY_MESSAGE_ROLE.USER
    || role === HISTORY_MESSAGE_ROLE.ASSISTANT
    || role === HISTORY_MESSAGE_ROLE.TOOL
    || role === HISTORY_MESSAGE_ROLE.SYSTEM
  ) return role
  return SESSION_TIMELINE_ROLE.ASSISTANT
}

function makeHistorySpeaker(
  message: HistoryMessage,
  playerCharacter: SessionPlayerCharacter | null,
): SessionSpeaker {
  const role = timelineRole(message.role)

  if (role === HISTORY_MESSAGE_ROLE.USER) {
    return makePlayerSpeaker(playerCharacter)
  }

  if (role === HISTORY_MESSAGE_ROLE.ASSISTANT) {
    return makeAssistantSpeaker()
  }

  if (role === HISTORY_MESSAGE_ROLE.TOOL) return toolSpeaker()
  return systemSpeaker()
}

export function mapHistoryToMessages({
  turns,
  playerCharacter,
}: {
  turns: Turn[] | undefined
  playerCharacter: SessionPlayerCharacter | null
}): SessionTimelineMessage[] {
  return (turns ?? []).flatMap((turn, turnIndex) => {
    const messages = turn.messages.map((message, messageIndex) => {
      const role = timelineRole(message.role)
      const persistent = Boolean(message.messageId)
      const turnActionRole = role === HISTORY_MESSAGE_ROLE.USER || role === HISTORY_MESSAGE_ROLE.ASSISTANT
      const content = role === HISTORY_MESSAGE_ROLE.USER ? stripLeadingSceneBlock(message.content) : message.content

      return {
        id: message.messageId ? `history-${message.messageId}` : `history-${turn.turnId || turnIndex + 1}-${messageIndex}`,
        messageId: message.messageId || undefined,
        turnId: message.turnId || turn.turnId || turnIndex + 1,
        seqInTurn: message.seqInTurn || messageIndex + 1,
        role,
        content,
        metadata: message.metadata,
        createdAt: message.createdAt,
        speaker: makeHistorySpeaker(message, playerCharacter),
        status: message.role === HISTORY_MESSAGE_ROLE.ASSISTANT ? SESSION_MESSAGE_STATUS.DONE : undefined,
        canCopy: Boolean(content.trim()),
        canRetry: persistent && role === HISTORY_MESSAGE_ROLE.USER,
        canEdit: persistent && role === HISTORY_MESSAGE_ROLE.USER,
        canDelete: persistent && turnActionRole,
      }
    })
    if (!turn.outcome) return messages
    const outcomeCreatedAt = turn.messages.find(
      (message) => message.role === HISTORY_MESSAGE_ROLE.ASSISTANT,
    )?.createdAt ?? turn.messages[0]?.createdAt
    return [
      ...messages,
      {
        id: `history-outcome-${turn.turnId}`,
        turnId: turn.turnId,
        seqInTurn: 2,
        role: SESSION_TIMELINE_ROLE.OUTCOME,
        content: turn.outcome.reason,
        outcome: turn.outcome,
        createdAt: outcomeCreatedAt,
        speaker: outcomeSpeaker(),
        status: SESSION_MESSAGE_STATUS.DONE,
        canCopy: false,
        canRetry: false,
        canEdit: false,
        canDelete: false,
      },
    ]
  })
}

export function parseNarrativeOutcomeToolResult(raw: string | undefined): NarrativeOutcome | null {
  if (!raw) return null
  try {
    const payload = JSON.parse(raw) as Record<string, unknown>
    const outcomeCode = payload.outcomeCode
    if (
      typeof outcomeCode !== 'string'
      || !NARRATIVE_OUTCOME_CODES.includes(outcomeCode as NarrativeOutcomeCode)
      || typeof payload.label !== 'string'
      || typeof payload.narrativeGuidance !== 'string'
      || typeof payload.reason !== 'string'
    ) return null
    return {
      outcomeCode: outcomeCode as NarrativeOutcomeCode,
      label: payload.label,
      narrativeGuidance: payload.narrativeGuidance,
      reason: payload.reason,
      actor: typeof payload.actor === 'string' && payload.actor ? payload.actor : null,
    }
  } catch {
    return null
  }
}

export function canEditMessage(message: SessionTimelineMessage): message is UserTimelineMessage {
  return Boolean(message.canEdit && message.role === SESSION_TIMELINE_ROLE.USER)
}

export function canRetryMessage(message: SessionTimelineMessage): message is UserTimelineMessage {
  return Boolean(message.canRetry && message.role === SESSION_TIMELINE_ROLE.USER)
}
