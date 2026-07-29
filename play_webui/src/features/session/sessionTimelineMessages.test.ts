import { describe, expect, it } from 'vitest'
import { NARRATIVE_OUTCOME_CODE } from '@/types/narrativeOutcome'
import {
  HISTORY_MESSAGE_ROLE,
  type SessionPlayerCharacter,
  type Turn,
} from '@/types/session'
import {
  SESSION_MESSAGE_STATUS,
  SESSION_TIMELINE_ROLE,
} from './sessionRoomTypes'
import {
  canEditMessage,
  canRetryMessage,
  mapHistoryToMessages,
  parseNarrativeOutcomeToolResult,
  unreconciledLocalMessages,
} from './sessionTimelineMessages'

const player: SessionPlayerCharacter = {
  characterId: 11,
  storyId: 3,
  name: '言琴',
  avatarUrl: '/avatar.png',
  roleLabel: 'PLAYER',
  updatedAt: '2026-07-29T10:00:00Z',
}

const turn: Turn = {
  turnId: 8,
  messages: [
    {
      messageId: 101,
      turnId: 8,
      seqInTurn: 1,
      role: HISTORY_MESSAGE_ROLE.USER,
      content: '[scene]\n地点：旧站台\n[/scene]\n向雨幕里走去。',
      mode: 'ic',
      metadata: {},
      createdAt: '2026-07-29T10:00:00Z',
    },
    {
      messageId: 102,
      turnId: 8,
      seqInTurn: 2,
      role: HISTORY_MESSAGE_ROLE.ASSISTANT,
      content: '<rp-narration>列车灯从远处亮起。</rp-narration>',
      mode: 'ic',
      metadata: {},
      createdAt: '2026-07-29T10:00:01Z',
    },
  ],
  plotInjections: [
    {
      eventTitle: '末班列车',
      directive: '让末班列车进入站台。',
    },
  ],
  outcome: {
    outcomeCode: NARRATIVE_OUTCOME_CODE.SUCCESS,
    label: '成功',
    narrativeGuidance: '目标达成。',
    reason: '及时赶到了站台。',
    actor: '言琴',
  },
}

describe('mapHistoryToMessages', () => {
  it('maps persistent messages with stable identity and player presentation', () => {
    const messages = mapHistoryToMessages({ turns: [turn], playerCharacter: player })
    const user = messages.find((message) => message.role === SESSION_TIMELINE_ROLE.USER)
    const assistant = messages.find(
      (message) => message.role === SESSION_TIMELINE_ROLE.ASSISTANT,
    )

    expect(user).toMatchObject({
      id: 'history-101',
      messageId: 101,
      turnId: 8,
      seqInTurn: 1,
      timelineGroupId: 'turn:8',
      content: '向雨幕里走去。',
      mode: 'ic',
      speaker: {
        name: '言琴',
        label: 'IC',
        avatarUrl: '/avatar.png',
        tone: 'player',
      },
      canRetry: true,
      canEdit: true,
      canDelete: true,
    })
    expect(assistant).toMatchObject({
      id: 'history-102',
      messageId: 102,
      status: SESSION_MESSAGE_STATUS.DONE,
      canDerive: true,
      canDelete: true,
    })
    expect(user && canEditMessage(user)).toBe(true)
    expect(user && canRetryMessage(user)).toBe(true)
  })

  it('projects plot injections and outcomes without changing assistant content', () => {
    const messages = mapHistoryToMessages({ turns: [turn], playerCharacter: player })
    const assistant = messages.find(
      (message) => message.role === SESSION_TIMELINE_ROLE.ASSISTANT,
    )
    const plot = messages.find(
      (message) => message.role === SESSION_TIMELINE_ROLE.PLOT_INJECTION,
    )
    const outcome = messages.find(
      (message) => message.role === SESSION_TIMELINE_ROLE.OUTCOME,
    )

    expect(assistant?.content).toBe(
      '<rp-narration>列车灯从远处亮起。</rp-narration>',
    )
    expect(plot).toMatchObject({
      id: 'history-plot-injection-8',
      content: '让末班列车进入站台。',
      canCopy: false,
    })
    expect(outcome).toMatchObject({
      id: 'history-outcome-8',
      content: '及时赶到了站台。',
      canCopy: false,
    })
  })
})

describe('unreconciledLocalMessages', () => {
  it('hides a local assistant prefix only after persistent history contains it', () => {
    const historyMessages = mapHistoryToMessages({ turns: [turn], playerCharacter: player })
    const localAssistant = {
      ...historyMessages.find(
        (message) => message.role === SESSION_TIMELINE_ROLE.ASSISTANT,
      )!,
      id: 'local-assistant',
      messageId: undefined,
      content: '<rp-narration>列车灯',
      status: SESSION_MESSAGE_STATUS.STREAMING,
    }

    expect(unreconciledLocalMessages(historyMessages, [localAssistant])).toEqual([])
  })

  it('retains divergent raw fallback text that persistent history does not cover', () => {
    const historyMessages = mapHistoryToMessages({ turns: [turn], playerCharacter: player })
    const rawFallback = {
      ...historyMessages.find(
        (message) => message.role === SESSION_TIMELINE_ROLE.ASSISTANT,
      )!,
      id: 'local-assistant',
      messageId: undefined,
      content: 'data: 无法解析但玩家已经看到',
      status: SESSION_MESSAGE_STATUS.ERROR,
    }

    expect(unreconciledLocalMessages(historyMessages, [rawFallback])).toEqual([rawFallback])
  })
})

describe('parseNarrativeOutcomeToolResult', () => {
  it('accepts a complete narrative outcome result', () => {
    expect(parseNarrativeOutcomeToolResult(JSON.stringify({
      outcomeCode: NARRATIVE_OUTCOME_CODE.SUCCESS_WITH_COST,
      label: '代价成功',
      narrativeGuidance: '完整达成目标并承担代价。',
      reason: '门打开了，但警报同时响起。',
      actor: '言琴',
    }))).toEqual({
      outcomeCode: NARRATIVE_OUTCOME_CODE.SUCCESS_WITH_COST,
      label: '代价成功',
      narrativeGuidance: '完整达成目标并承担代价。',
      reason: '门打开了，但警报同时响起。',
      actor: '言琴',
    })
  })

  it.each([
    undefined,
    '',
    '{',
    JSON.stringify({ outcomeCode: 'unknown' }),
    JSON.stringify({
      outcomeCode: NARRATIVE_OUTCOME_CODE.SUCCESS,
      label: '成功',
      narrativeGuidance: '目标达成。',
    }),
  ])('rejects an incomplete result: %j', (raw) => {
    expect(parseNarrativeOutcomeToolResult(raw)).toBeNull()
  })
})
