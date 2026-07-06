'use client'

import { CSSProperties, PointerEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { AlignJustify, LogOut, TableProperties } from 'lucide-react'
import { ConfirmDialog } from '@/components/common/Dialog'
import { ThemeSwitcher } from '@/components/theme/ThemeSwitcher'
import { listStoryCharacters } from '@/lib/api/characters'
import { getContextPreview } from '@/lib/api/contextPreview'
import { getCurrentScene } from '@/lib/api/scene'
import {
  bindSessionPlayerCharacter,
  deleteSessionMessage,
  getSession,
  getSessionHistory,
  truncateSessionTurn,
} from '@/lib/api/sessions'
import { listSessionStatusTables } from '@/lib/api/statusTables'
import { consumeChatStream } from '@/lib/stream/sse'
import { cn } from '@/lib/utils/cn'
import { SESSION_FONT_SCALE_DEFAULT, useSessionUiStore } from '@/stores/sessionUiStore'
import type { CharacterCard } from '@/types/characters'
import { fromContextPreviewEstimate, fromTurnUsage, type ContextUsageSnapshot } from '@/types/contextUsage'
import { PLAY_STREAM_EVENT_TYPE, type PlayStreamEvent } from '@/types/stream'
import { STATUS_KIND } from '@/types/statusTables'
import { SessionComposer } from './SessionComposer'
import { SessionLeftRail, SessionRightRail } from './SessionSideRails'
import { SessionSettingsMenu } from './SessionSettingsMenu'
import { SessionTimeline } from './SessionTimeline'
import {
  characterSummary,
  firstLetter,
  formatDateTime,
  getCharacterAvatarUrl,
  stripLeadingSceneBlock,
} from './sessionRoomHelpers'
import { HISTORY_MESSAGE_ROLE, PLAYER_CHARACTER_STATUS, type SessionPlayerCharacter } from '@/types/session'
import {
  ConfirmRequest,
  NarrativeStyle,
  NarrativeStyleId,
  SESSION_TIMELINE_ROLE,
  SessionInputMode,
  SessionSpeaker,
  SessionTimelineMessage,
} from './sessionRoomTypes'

const defaultSidebarSizes = {
  left: 300,
  right: 340,
}

const collapsedSidebarSize = 72

const sidebarLimits = {
  leftMin: 260,
  leftMax: 460,
  rightMin: 280,
  rightMax: 500,
}

const narrativeStyles: NarrativeStyle[] = [
  { id: 'default', label: '默认', prompt: '' },
  { id: 'detailed', label: '细腻描写', prompt: '请用细腻描写推进这一幕。' },
  { id: 'fast', label: '快速推进', prompt: '请快速推进到下一个关键选择。' },
  { id: 'options', label: '多给选项', prompt: '请在回应末尾给出多个可选择的行动方向。' },
]

type DragState = {
  side: 'left' | 'right'
  startX: number
  startLeft: number
  startRight: number
}

type MobilePanel = 'left' | 'right' | null
type HistoryMessage = Awaited<ReturnType<typeof getSessionHistory>>[number]['messages'][number]
type UserTimelineMessage = SessionTimelineMessage & { role: typeof SESSION_TIMELINE_ROLE.USER }
type PersistedUserTimelineMessage = UserTimelineMessage & { messageId: number }

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value))
}

function makePlayerSpeaker(character: SessionPlayerCharacter | null): SessionSpeaker {
  return {
    name: character?.name ?? '你',
    label: 'IC',
    avatarUrl: character?.avatarUrl ?? '',
    fallback: firstLetter(character?.name ?? '你'),
    tone: 'player',
  }
}

function makeAssistantSpeaker(): SessionSpeaker {
  // Assistant output is currently one mixed narrative block. Character-level
  // avatars need a future structured segments layer instead of speaker metadata.
  return {
    name: '叙事者',
    avatarUrl: '',
    fallback: '叙',
    tone: 'assistant',
  }
}

function toolSpeaker(): SessionSpeaker {
  return {
    name: '工具结果',
    fallback: '⚒',
    tone: 'tool',
  }
}

function errorSpeaker(): SessionSpeaker {
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

function streamPlaceholder(turnId: number): SessionTimelineMessage {
  return {
    id: `local-stream-${turnId}-${crypto.randomUUID()}`,
    turnId,
    seqInTurn: 2,
    role: SESSION_TIMELINE_ROLE.ASSISTANT,
    content: '',
    createdAt: new Date().toISOString(),
    speaker: makeAssistantSpeaker(),
    status: 'streaming',
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

function mapHistoryToMessages({
  turns,
  playerCharacter,
}: {
  turns: Awaited<ReturnType<typeof getSessionHistory>> | undefined
  playerCharacter: SessionPlayerCharacter | null
}): SessionTimelineMessage[] {
  return (turns ?? []).flatMap((turn, turnIndex) => {
    return turn.messages.map((message, messageIndex) => {
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
        status: message.role === HISTORY_MESSAGE_ROLE.ASSISTANT ? 'done' : undefined,
        canCopy: Boolean(content.trim()),
        canRetry: persistent && role === HISTORY_MESSAGE_ROLE.USER,
        canEdit: persistent && role === HISTORY_MESSAGE_ROLE.USER,
        canDelete: persistent && turnActionRole,
      }
    })
  })
}

function canEditMessage(message: SessionTimelineMessage): message is PersistedUserTimelineMessage {
  return Boolean(message.canEdit && message.messageId && message.role === SESSION_TIMELINE_ROLE.USER)
}

function canRetryMessage(message: SessionTimelineMessage): message is PersistedUserTimelineMessage {
  return Boolean(message.canRetry && message.messageId && message.role === SESSION_TIMELINE_ROLE.USER)
}

function Toast({ message }: { message: string }) {
  return (
    <div
      role="status"
      aria-live="polite"
      className={cn(
        'pointer-events-none fixed bottom-6 left-1/2 z-50 -translate-x-1/2 rounded-full bg-slate-950 px-4 py-2 text-sm font-bold text-white shadow-2xl transition',
        message ? 'translate-y-0 opacity-100' : 'translate-y-3 opacity-0',
      )}
    >
      {message}
    </div>
  )
}

function PlayerCharacterDialog({
  open,
  required,
  characters,
  loading,
  currentPlayer,
  selectedCharacterId,
  pending,
  error,
  onSelect,
  onSubmit,
  onClose,
}: {
  open: boolean
  required: boolean
  characters: CharacterCard[]
  loading: boolean
  currentPlayer: SessionPlayerCharacter | null
  selectedCharacterId: number | null
  pending: boolean
  error: string | null
  onSelect: (characterId: number) => void
  onSubmit: () => void
  onClose: () => void
}) {
  if (!open) return null

  const currentCharacterId = currentPlayer?.characterId ?? null
  const canSubmit = Boolean(selectedCharacterId) && (required || selectedCharacterId !== currentCharacterId) && !pending

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/45 px-4 py-8 backdrop-blur-sm">
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="player-character-title"
        className="flex max-h-[calc(100vh-4rem)] w-full max-w-3xl flex-col overflow-hidden rounded-lg border border-slate-200 bg-white shadow-2xl shadow-slate-950/20 dark:border-slate-700 dark:bg-slate-950 dark:shadow-black/50"
      >
        <header className="flex items-start justify-between gap-4 border-b border-slate-200 bg-slate-50 px-6 py-5 dark:border-slate-800 dark:bg-slate-900">
          <div>
            <h2 id="player-character-title" className="text-xl font-black text-slate-950 dark:text-slate-100">
              {required ? '选择你要扮演的角色' : '切换扮演角色'}
            </h2>
            <p className="mt-1 text-sm font-semibold leading-6 text-slate-500 dark:text-slate-300">
              角色选择会影响后续 user 消息的头像、名称和后续 prompt 语义，不重写已有历史。
            </p>
          </div>
          {!required ? (
            <button
              type="button"
              onClick={onClose}
              className="flex h-9 w-9 items-center justify-center rounded-lg text-slate-500 transition hover:bg-slate-100 hover:text-slate-900 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-slate-50"
              aria-label="关闭"
            >
              ×
            </button>
          ) : null}
        </header>

        <div className="overflow-y-auto px-6 py-5">
          {error ? (
            <p className="mb-4 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm font-bold text-rose-700 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-200">
              {error}
            </p>
          ) : null}

          {loading ? (
            <section className="rounded-lg border border-dashed border-slate-300 bg-slate-50 px-5 py-12 text-center dark:border-slate-700 dark:bg-slate-900">
              <h3 className="text-lg font-black text-slate-950 dark:text-slate-100">正在加载可扮演角色</h3>
              <p className="mt-2 text-sm font-semibold leading-6 text-slate-500 dark:text-slate-300">
                角色列表加载完成后即可选择。绑定完成前本会话不能发送消息。
              </p>
            </section>
          ) : characters.length ? (
            <div className="grid gap-3 md:grid-cols-3">
              {characters.map((character) => {
                const avatarUrl = getCharacterAvatarUrl(character)
                const selected = selectedCharacterId === character.id
                const current = currentCharacterId === character.id
                return (
                  <button
                    key={character.id}
                    type="button"
                    onClick={() => onSelect(character.id)}
                    className={cn(
                      'grid min-h-44 gap-3 rounded-lg border p-4 text-left transition',
                      selected
                        ? 'border-violet-400 bg-violet-50 shadow-[inset_0_0_0_1px_rgba(139,92,246,0.18)] dark:border-violet-500/60 dark:bg-violet-500/15'
                        : 'border-slate-200 bg-white hover:border-violet-200 hover:bg-violet-50/40 dark:border-slate-700 dark:bg-slate-900 dark:hover:border-violet-500/50 dark:hover:bg-violet-500/10',
                    )}
                  >
                    <span className="flex items-center justify-between gap-3">
                      {avatarUrl ? (
                        <img src={avatarUrl} alt="" className="h-11 w-11 rounded-full object-cover" />
                      ) : (
                        <span className="flex h-11 w-11 items-center justify-center rounded-full bg-teal-50 text-base font-black text-teal-700 dark:bg-teal-500/15 dark:text-teal-200">
                          {firstLetter(character.name)}
                        </span>
                      )}
                      <span className={cn('h-5 w-5 rounded-full border-2', selected ? 'border-[6px] border-violet-600' : 'border-slate-300 dark:border-slate-600')} />
                    </span>
                    <span className="min-w-0">
                      <strong className="block truncate text-base font-black text-slate-950 dark:text-slate-100">{character.name}</strong>
                      <span className="mt-1 line-clamp-3 block text-sm font-semibold leading-6 text-slate-500 dark:text-slate-300">
                        {characterSummary(character)}
                      </span>
                    </span>
                    <span className={cn('w-fit rounded-full px-2.5 py-1 text-xs font-black', current ? 'bg-teal-100 text-teal-700 dark:bg-teal-500/15 dark:text-teal-200' : 'bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-300')}>
                      {current ? '当前绑定' : '可选择'}
                    </span>
                  </button>
                )
              })}
            </div>
          ) : (
            <section className="rounded-lg border border-dashed border-slate-300 bg-slate-50 px-5 py-12 text-center dark:border-slate-700 dark:bg-slate-900">
              <h3 className="text-lg font-black text-slate-950 dark:text-slate-100">当前故事还没有可扮演角色</h3>
              <p className="mt-2 text-sm font-semibold leading-6 text-slate-500 dark:text-slate-300">
                请先到角色库创建角色，并将角色挂载到当前故事。绑定完成前本会话不能发送消息。
              </p>
            </section>
          )}
        </div>

        <footer className="flex items-center justify-between gap-3 border-t border-slate-200 bg-slate-50 px-6 py-4 dark:border-slate-800 dark:bg-slate-900">
          <p className="text-xs font-semibold text-slate-400 dark:text-slate-300">
            {required ? '必须选择角色后才能开始。' : '切换只影响后续消息。'}
          </p>
          <div className="flex items-center gap-2">
            {!required ? (
              <button
                type="button"
                onClick={onClose}
                className="h-10 rounded-lg border border-slate-200 bg-white px-4 text-sm font-black text-slate-700 transition hover:border-violet-200 hover:text-violet-700 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-300 dark:hover:border-violet-500/60 dark:hover:text-violet-200"
              >
                取消
              </button>
            ) : null}
            <button
              type="button"
              onClick={onSubmit}
              disabled={!canSubmit}
              className="h-10 rounded-lg bg-violet-600 px-4 text-sm font-black text-white shadow-lg shadow-violet-100 transition hover:bg-violet-700 disabled:cursor-not-allowed disabled:bg-slate-300 disabled:shadow-none dark:shadow-violet-950/40 dark:disabled:bg-slate-700"
            >
              {pending ? '绑定中...' : required ? '确认角色' : '切换角色'}
            </button>
          </div>
        </footer>
      </section>
    </div>
  )
}

export function SessionRoom({ sessionId }: { sessionId: string }) {
  const router = useRouter()
  const queryClient = useQueryClient()
  const [leftWidth, setLeftWidth] = useState(defaultSidebarSizes.left)
  const [rightWidth, setRightWidth] = useState(defaultSidebarSizes.right)
  const [leftCollapsed, setLeftCollapsed] = useState(false)
  const [rightCollapsed, setRightCollapsed] = useState(false)
  const [mobilePanel, setMobilePanel] = useState<MobilePanel>(null)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [dragState, setDragState] = useState<DragState | null>(null)
  const [inputMode, setInputMode] = useState<SessionInputMode>('ic')
  const [narrativeStyleId, setNarrativeStyleId] = useState<NarrativeStyleId>('default')
  const [composerText, setComposerText] = useState('')
  const [localMessages, setLocalMessages] = useState<SessionTimelineMessage[]>([])
  const [optimisticTruncateFromTurn, setOptimisticTruncateFromTurn] = useState<number | null>(null)
  const [editingMessageId, setEditingMessageId] = useState<string | null>(null)
  const [editDraft, setEditDraft] = useState('')
  const [confirmRequest, setConfirmRequest] = useState<ConfirmRequest | null>(null)
  const [roleDialogOpen, setRoleDialogOpen] = useState(false)
  const [roleDialogRequired, setRoleDialogRequired] = useState(false)
  const [selectedRoleCharacterId, setSelectedRoleCharacterId] = useState<number | null>(null)
  const [roleBindError, setRoleBindError] = useState<string | null>(null)
  const [bindingRole, setBindingRole] = useState(false)
  const [toastMessage, setToastMessage] = useState('')
  const [sending, setSending] = useState(false)
  const [accurateUsageOverride, setAccurateUsageOverride] = useState<ContextUsageSnapshot | null>(null)
  const [forceScrollKey, setForceScrollKey] = useState(0)
  const toastTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const fontScale = useSessionUiStore((state) => state.fontScale)
  const setFontScale = useSessionUiStore((state) => state.setFontScale)
  const syncFontScale = useSessionUiStore((state) => state.syncFontScale)

  const sessionQuery = useQuery({
    queryKey: ['play-session', sessionId],
    queryFn: () => getSession(sessionId),
  })

  const session = sessionQuery.data

  const historyQuery = useQuery({
    queryKey: ['play-session-history', sessionId],
    queryFn: () => getSessionHistory(sessionId),
  })

  const sceneQuery = useQuery({
    queryKey: ['play-session-scene', sessionId],
    queryFn: () => getCurrentScene(sessionId),
  })

  const statusTablesQuery = useQuery({
    queryKey: ['play-session-status-tables', sessionId, STATUS_KIND.NORMAL],
    queryFn: () => listSessionStatusTables(sessionId, STATUS_KIND.NORMAL),
  })

  const charactersQuery = useQuery({
    queryKey: ['play-story-characters', session?.workspace, session?.storyId],
    enabled: Boolean(session?.workspace && session?.storyId),
    queryFn: () => listStoryCharacters(session?.workspace ?? '', session?.storyId ?? 0),
  })

  const characters = charactersQuery.data ?? []
  const playerCharacter = session?.playerCharacter ?? null
  const playerCharacterInvalid = session?.playerCharacterStatus === PLAYER_CHARACTER_STATUS.INVALID
  const roleSelectionBlocked = !session || playerCharacterInvalid || bindingRole

  const contextPreviewQuery = useQuery({
    queryKey: ['play-session-context-preview', sessionId],
    enabled: Boolean(session && !playerCharacterInvalid),
    queryFn: () => getContextPreview(sessionId),
  })

  const contextPreviewUsage = useMemo(
    () => fromContextPreviewEstimate(contextPreviewQuery.data),
    [contextPreviewQuery.data],
  )
  const contextUsage = roleSelectionBlocked ? null : accurateUsageOverride ?? contextPreviewUsage

  const baseMessages = useMemo(
    () => mapHistoryToMessages({ turns: historyQuery.data, playerCharacter }),
    [historyQuery.data, playerCharacter],
  )

  const visibleMessages = useMemo(() => {
    const historyMessages = optimisticTruncateFromTurn === null
      ? baseMessages
      : baseMessages.filter((message) => message.turnId < optimisticTruncateFromTurn)

    return [...historyMessages, ...localMessages]
      .sort((first, second) => first.turnId - second.turnId || (first.seqInTurn ?? 0) - (second.seqInTurn ?? 0))
  }, [baseMessages, localMessages, optimisticTruncateFromTurn])

  const lastTurnId = useMemo(
    () => Math.max(0, ...visibleMessages.map((message) => message.turnId)),
    [visibleMessages],
  )

  const currentNarrativeStyle = narrativeStyles.find((style) => style.id === narrativeStyleId) ?? narrativeStyles[0]

  const showToast = useCallback((message: string) => {
    setToastMessage(message)
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current)
    toastTimerRef.current = setTimeout(() => setToastMessage(''), 2200)
  }, [])

  const handleComposerTextChange = useCallback((value: string) => {
    setComposerText(value)
    setAccurateUsageOverride(null)
  }, [])

  useEffect(() => {
    syncFontScale()
  }, [syncFontScale])

  useEffect(() => {
    setLocalMessages([])
    setOptimisticTruncateFromTurn(null)
    setEditingMessageId(null)
    setEditDraft('')
    setComposerText('')
    setMobilePanel(null)
    setSettingsOpen(false)
    setRoleDialogOpen(false)
    setRoleDialogRequired(false)
    setSelectedRoleCharacterId(null)
    setRoleBindError(null)
    setAccurateUsageOverride(null)
  }, [sessionId])

  useEffect(() => {
    if (!session) return
    if (session.playerCharacterStatus === PLAYER_CHARACTER_STATUS.INVALID) {
      setRoleDialogRequired(true)
      setRoleDialogOpen(true)
      setSelectedRoleCharacterId((current) => current ?? characters[0]?.id ?? null)
      return
    }
    if (roleDialogRequired) {
      setRoleDialogRequired(false)
      setRoleDialogOpen(false)
      setRoleBindError(null)
    }
  }, [characters, roleDialogRequired, session])

  useEffect(() => {
    return () => {
      if (toastTimerRef.current) clearTimeout(toastTimerRef.current)
      abortRef.current?.abort()
    }
  }, [])

  useEffect(() => {
    if (!dragState) return

    const handlePointerMove = (event: globalThis.PointerEvent) => {
      if (dragState.side === 'left') {
        setLeftWidth(clamp(dragState.startLeft + event.clientX - dragState.startX, sidebarLimits.leftMin, sidebarLimits.leftMax))
        return
      }
      setRightWidth(clamp(dragState.startRight - (event.clientX - dragState.startX), sidebarLimits.rightMin, sidebarLimits.rightMax))
    }

    const stopDragging = () => {
      setDragState(null)
    }

    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
    window.addEventListener('pointermove', handlePointerMove)
    window.addEventListener('pointerup', stopDragging)
    window.addEventListener('pointercancel', stopDragging)

    return () => {
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
      window.removeEventListener('pointermove', handlePointerMove)
      window.removeEventListener('pointerup', stopDragging)
      window.removeEventListener('pointercancel', stopDragging)
    }
  }, [dragState])

  const gridStyle = useMemo(
    () =>
      ({
        '--session-grid-columns': `${leftCollapsed ? collapsedSidebarSize : leftWidth}px 8px minmax(0,1fr) 8px ${
          rightCollapsed ? collapsedSidebarSize : rightWidth
        }px`,
      }) as CSSProperties,
    [leftCollapsed, leftWidth, rightCollapsed, rightWidth],
  )

  const sessionExperienceStyle = useMemo(
    () =>
      ({
        '--session-message-font-size': `${14 * (fontScale / 100)}px`,
        '--session-message-line-height': `${28 * (fontScale / 100)}px`,
        '--session-segment-label-font-size': `${11 * (fontScale / 100)}px`,
        '--session-composer-font-size': `${16 * (fontScale / 100)}px`,
        '--session-composer-line-height': `${28 * (fontScale / 100)}px`,
      }) as CSSProperties,
    [fontScale],
  )

  const startDrag = (side: 'left' | 'right') => (event: PointerEvent<HTMLButtonElement>) => {
    event.preventDefault()
    setDragState({
      side,
      startX: event.clientX,
      startLeft: leftWidth,
      startRight: rightWidth,
    })
  }

  const refreshSessionData = useCallback(async ({
    silent = false,
    clearAccurateUsage = true,
  }: {
    silent?: boolean
    clearAccurateUsage?: boolean
  } = {}) => {
    try {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['play-session', sessionId] }),
        queryClient.invalidateQueries({ queryKey: ['play-session-history', sessionId] }),
        queryClient.invalidateQueries({ queryKey: ['play-session-scene', sessionId] }),
        queryClient.invalidateQueries({ queryKey: ['play-session-status-tables', sessionId] }),
        queryClient.invalidateQueries({ queryKey: ['play-session-context-preview', sessionId] }),
      ])
      setLocalMessages([])
      setOptimisticTruncateFromTurn(null)
      setEditingMessageId(null)
      setEditDraft('')
      if (clearAccurateUsage) setAccurateUsageOverride(null)
      return true
    } catch {
      if (!silent) showToast('刷新失败，请手动刷新页面')
      return false
    }
  }, [queryClient, sessionId, showToast])

  const requestConfirm = useCallback((request: ConfirmRequest) => {
    setConfirmRequest(request)
  }, [])

  const openRoleDialog = useCallback(() => {
    setSettingsOpen(false)
    setRoleDialogRequired(false)
    setRoleDialogOpen(true)
    setRoleBindError(null)
    setSelectedRoleCharacterId(playerCharacter?.characterId ?? characters[0]?.id ?? null)
  }, [characters, playerCharacter])

  const closeRoleDialog = useCallback(() => {
    if (roleDialogRequired) return
    setRoleDialogOpen(false)
    setRoleBindError(null)
    setSelectedRoleCharacterId(null)
  }, [roleDialogRequired])

  const bindPlayerRole = useCallback(async (characterId: number) => {
    setBindingRole(true)
    setRoleBindError(null)
    try {
      const updated = await bindSessionPlayerCharacter(sessionId, characterId)
      await refreshSessionData({ silent: true })
      setRoleDialogOpen(false)
      setRoleDialogRequired(false)
      setSelectedRoleCharacterId(null)
      showToast(`已切换为 ${updated.playerCharacter?.name ?? '所选角色'}`)
    } catch (error) {
      const message = error instanceof Error ? error.message : '角色绑定失败'
      setRoleBindError(message)
      showToast(message)
    } finally {
      setBindingRole(false)
    }
  }, [refreshSessionData, sessionId, showToast])

  const submitRoleDialog = useCallback(() => {
    const characterId = selectedRoleCharacterId
    if (!characterId) {
      setRoleBindError('请选择一个角色')
      return
    }
    if (!roleDialogRequired && playerCharacter?.characterId === characterId) {
      showToast('已经是当前扮演角色')
      return
    }
    if (!roleDialogRequired && playerCharacter) {
      const next = characters.find((character) => character.id === characterId)
      requestConfirm({
        title: '确认切换角色',
        heading: '切换玩家扮演角色',
        body: `将当前扮演角色从 ${playerCharacter.name} 切换为 ${next?.name ?? '所选角色'}。历史消息保持原样，只影响后续 user 身份。`,
        confirmLabel: '确认切换',
        onConfirm: () => {
          void bindPlayerRole(characterId)
        },
      })
      return
    }
    void bindPlayerRole(characterId)
  }, [bindPlayerRole, characters, playerCharacter, requestConfirm, roleDialogRequired, selectedRoleCharacterId, showToast])

  const showRegenerationPreview = useCallback((message: UserTimelineMessage, text: string) => {
    const turnId = message.turnId
    const previewUserMessage: SessionTimelineMessage = {
      id: `local-regenerate-user-${turnId}-${crypto.randomUUID()}`,
      turnId,
      seqInTurn: 1,
      role: SESSION_TIMELINE_ROLE.USER,
      content: text,
      createdAt: new Date().toISOString(),
      speaker: message.speaker,
      status: 'local',
      canCopy: true,
      canRetry: false,
      canEdit: false,
      canDelete: false,
    }
    const assistantMessage = streamPlaceholder(turnId)

    setOptimisticTruncateFromTurn(turnId)
    setLocalMessages((current) => [
      ...current.filter((item) => item.turnId < turnId),
      previewUserMessage,
      assistantMessage,
    ])
    setForceScrollKey((current) => current + 1)
    setEditingMessageId(null)
    setEditDraft('')
    return assistantMessage
  }, [])

  const restoreRegenerationPreview = useCallback(() => {
    setOptimisticTruncateFromTurn(null)
    setLocalMessages([])
  }, [])

  const clearRegenerationPreviewAfterTruncate = useCallback((turnId: number) => {
    setOptimisticTruncateFromTurn(turnId)
    setLocalMessages([])
    setEditingMessageId(null)
    setEditDraft('')
  }, [])

  const appendStreamEvent = useCallback((event: PlayStreamEvent, assistantMessageId: string, turnId: number) => {
    if (event.type === PLAY_STREAM_EVENT_TYPE.TURN_STARTED) return

    if (event.type === PLAY_STREAM_EVENT_TYPE.TEXT_DELTA) {
      setLocalMessages((current) =>
        current.map((message) =>
          message.id === assistantMessageId
            ? {
                ...message,
                content: `${message.content}${event.payload.text}`,
                status: 'streaming',
                canCopy: Boolean(`${message.content}${event.payload.text}`.trim()),
              }
            : message,
        ),
      )
      return
    }

    if (event.type === PLAY_STREAM_EVENT_TYPE.TOOL_CALL || event.type === PLAY_STREAM_EVENT_TYPE.TOOL_RESULT) {
      const toolText = event.type === PLAY_STREAM_EVENT_TYPE.TOOL_RESULT
        ? event.payload.resultPreview ?? event.payload.toolResult ?? event.payload.toolName ?? '工具事件'
        : event.payload.toolArguments ?? event.payload.toolName ?? '工具事件'
      setLocalMessages((current) => [
        ...current,
        {
          id: `local-tool-${turnId}-${crypto.randomUUID()}`,
          turnId,
          seqInTurn: 4,
          role: SESSION_TIMELINE_ROLE.TOOL,
          content: toolText,
          createdAt: new Date().toISOString(),
          speaker: toolSpeaker(),
          status: 'local',
          canCopy: Boolean(toolText.trim()),
          canRetry: false,
          canEdit: false,
          canDelete: false,
        },
      ])
      return
    }

    if (event.type === PLAY_STREAM_EVENT_TYPE.TURN_COMPLETED) {
      const usage = fromTurnUsage(event.payload.usage, contextPreviewUsage, {
        model: event.payload.model,
        finishReason: event.payload.finishReason,
        durationMs: event.payload.durationMs,
      })
      if (usage) setAccurateUsageOverride(usage)
      setLocalMessages((current) =>
        current.map((message) =>
          message.id === assistantMessageId
            ? {
                ...message,
                status: 'done',
                content: message.content || event.payload.text || '已完成。',
                canCopy: Boolean((message.content || event.payload.text || '已完成。').trim()),
              }
            : message,
        ),
      )
      return
    }

    if (event.type === PLAY_STREAM_EVENT_TYPE.ERROR) {
      const errorText = event.payload.message || '流式请求失败'
      setLocalMessages((current) => [
        ...current.map((message) =>
          message.id === assistantMessageId ? { ...message, status: 'error' as const } : message,
        ),
        {
          id: `local-error-${turnId}-${crypto.randomUUID()}`,
          turnId,
          seqInTurn: 5,
          role: SESSION_TIMELINE_ROLE.ERROR,
          content: errorText,
          createdAt: new Date().toISOString(),
          speaker: errorSpeaker(),
          status: 'error',
          canCopy: Boolean(errorText.trim()),
          canRetry: false,
          canEdit: false,
          canDelete: false,
        },
      ])
    }
  }, [contextPreviewUsage])

  const performRegeneration = useCallback(async ({
    message,
    text,
    pendingToast,
    successToast,
    failureToast,
  }: {
    message: PersistedUserTimelineMessage
    text: string
    pendingToast: string
    successToast: string
    failureToast: string
  }) => {
    if (sending) {
      showToast('当前仍在生成，请稍后再试')
      return
    }

    const assistantMessage = showRegenerationPreview(message, text)
    const controller = new AbortController()
    let truncated = false
    let streamFailure: string | null = null
    abortRef.current = controller
    setAccurateUsageOverride(null)
    setSending(true)
    showToast(pendingToast)

    try {
      await truncateSessionTurn(sessionId, message.turnId)
      truncated = true
      await consumeChatStream(
        {
          sessionId,
          text,
          mode: inputMode,
        },
        {
          signal: controller.signal,
          onEvent: (event) => {
            appendStreamEvent(event, assistantMessage.id, message.turnId)
            if (event.type === PLAY_STREAM_EVENT_TYPE.ERROR) streamFailure = event.payload.message || failureToast
          },
        },
      )
      if (streamFailure) throw new Error(streamFailure)
      const refreshed = await refreshSessionData({ silent: true, clearAccurateUsage: false })
      showToast(refreshed ? successToast : `${successToast}，但刷新失败，请手动刷新页面`)
    } catch (error) {
      if (!truncated) {
        restoreRegenerationPreview()
      } else {
        clearRegenerationPreviewAfterTruncate(message.turnId)
        await refreshSessionData({ silent: true })
      }
      showToast(error instanceof Error ? error.message : failureToast)
    } finally {
      setSending(false)
      abortRef.current = null
    }
  }, [
    appendStreamEvent,
    clearRegenerationPreviewAfterTruncate,
    inputMode,
    refreshSessionData,
    restoreRegenerationPreview,
    sending,
    sessionId,
    showRegenerationPreview,
    showToast,
  ])

  const performRetry = useCallback(async (message: SessionTimelineMessage) => {
    if (!canRetryMessage(message)) {
      showToast('当前回合不可重试')
      return
    }
    await performRegeneration({
      message,
      text: message.content,
      pendingToast: `正在重试 turn #${message.turnId}`,
      successToast: `已重试 turn #${message.turnId}`,
      failureToast: '重试失败',
    })
  }, [performRegeneration, showToast])

  const handleRetry = useCallback((message: SessionTimelineMessage) => {
    if (!canRetryMessage(message)) {
      showToast('当前回合不可重试')
      return
    }
    if (message.turnId >= lastTurnId) {
      void performRetry(message)
      return
    }
    requestConfirm({
      title: '确认重试',
      heading: '该操作会影响后续回合',
      body: `重试 turn #${message.turnId} 会删除该 turn 以及之后更新的所有 turn，并重新生成回应。`,
      confirmLabel: '确认重试',
      onConfirm: () => {
        void performRetry(message)
      },
    })
  }, [lastTurnId, performRetry, requestConfirm, showToast])

  const handleCopy = useCallback((message: SessionTimelineMessage) => {
    if (!message.content.trim()) {
      showToast('当前消息没有可复制内容')
      return
    }
    navigator.clipboard?.writeText(message.content).then(
      () => showToast('已复制当前消息'),
      () => showToast('复制失败，请手动选择文本'),
    )
  }, [showToast])

  const handleStartEdit = useCallback((message: SessionTimelineMessage) => {
    if (!canEditMessage(message)) {
      showToast('当前消息不可编辑')
      return
    }
    setEditingMessageId(message.id)
    setEditDraft(message.content)
  }, [showToast])

  const performSendEdited = useCallback(async (message: SessionTimelineMessage, text: string) => {
    if (!canEditMessage(message)) {
      showToast('当前消息不可编辑')
      return
    }
    await performRegeneration({
      message,
      text,
      pendingToast: '正在发送编辑',
      successToast: '已发送编辑',
      failureToast: '编辑失败',
    })
  }, [performRegeneration, showToast])

  const handleSendEdit = useCallback((message: SessionTimelineMessage) => {
    if (!canEditMessage(message)) {
      showToast('当前消息不可编辑')
      return
    }
    const text = editDraft.trim()
    if (!text) {
      showToast('编辑内容不能为空')
      return
    }
    if (message.turnId < lastTurnId) {
      requestConfirm({
        title: '确认发送编辑',
        heading: '该操作会影响后续回合',
        body: `发送编辑后的 turn #${message.turnId} 会删除该 turn 以及之后更新的所有 turn，并从这条用户消息重新生成回应。`,
        confirmLabel: '确认发送',
        onConfirm: () => {
          void performSendEdited(message, text)
        },
      })
      return
    }
    void performSendEdited(message, text)
  }, [editDraft, lastTurnId, performSendEdited, requestConfirm, showToast])

  const performDelete = useCallback(async (message: SessionTimelineMessage) => {
    if (!message.canDelete || !message.messageId) {
      showToast('当前消息不可删除')
      return
    }
    showToast('正在删除消息')
    try {
      await deleteSessionMessage(sessionId, message.messageId)
      const refreshed = await refreshSessionData({ silent: true })
      showToast(refreshed ? '已删除消息' : '删除已提交，但刷新失败，请手动刷新页面')
    } catch (error) {
      showToast(error instanceof Error ? error.message : '删除失败')
    }
  }, [refreshSessionData, sessionId, showToast])

  const handleDelete = useCallback((message: SessionTimelineMessage) => {
    if (!message.canDelete) {
      showToast('当前消息不可删除')
      return
    }
    requestConfirm({
      title: '确认删除',
      heading: '删除当前消息',
      body: '删除会从当前会话历史中移除这条消息。',
      confirmLabel: '确认删除',
      onConfirm: () => {
        void performDelete(message)
      },
    })
  }, [performDelete, requestConfirm, showToast])

  const handleSend = useCallback(async () => {
    if (!session) {
      showToast('会话加载中，请稍后再试')
      return
    }
    if (playerCharacterInvalid) {
      setRoleDialogRequired(true)
      setRoleDialogOpen(true)
      showToast('请先选择你要扮演的角色')
      return
    }
    const text = composerText.trim()
    if (!text) {
      showToast('请输入内容后再发送')
      return
    }

    const turnId = lastTurnId + 1
    const style = currentNarrativeStyle
    const playerSpeaker = makePlayerSpeaker(playerCharacter)
    const userMessage: SessionTimelineMessage = {
      id: `local-user-${turnId}-${crypto.randomUUID()}`,
      turnId,
      seqInTurn: 1,
      role: SESSION_TIMELINE_ROLE.USER,
      content: text,
      createdAt: new Date().toISOString(),
      speaker: { ...playerSpeaker, label: inputMode.toUpperCase() },
      hiddenPrompt: style.prompt,
      status: style.prompt ? 'local' : undefined,
      canCopy: true,
      canRetry: false,
      canEdit: false,
      canDelete: false,
    }
    const assistantMessage = streamPlaceholder(turnId)
    const controller = new AbortController()
    abortRef.current = controller
    setAccurateUsageOverride(null)
    setComposerText('')
    setSending(true)
    setLocalMessages((current) => [...current, userMessage, assistantMessage])
    setForceScrollKey((current) => current + 1)

    let streamFailure: string | null = null
    let completedTurn = false
    try {
      // 叙事风格目前只保存在本地 message metadata；待后端支持独立 prompt 字段后再随 payload 发送。
      await consumeChatStream(
        {
          sessionId,
          text,
          mode: inputMode,
        },
        {
          signal: controller.signal,
          onEvent: (event) => {
            appendStreamEvent(event, assistantMessage.id, turnId)
            if (event.type === PLAY_STREAM_EVENT_TYPE.ERROR) streamFailure = event.payload.message || '未知流式错误'
          },
        },
      )
      if (streamFailure) throw new Error(streamFailure)
      completedTurn = true
    } catch (error) {
      if (controller.signal.aborted) {
        setLocalMessages((current) =>
          current.map((message) =>
            message.id === assistantMessage.id
              ? {
                  ...message,
                  status: 'done',
                  content: message.content || '已停止当前流式响应。',
                  canCopy: Boolean((message.content || '已停止当前流式响应。').trim()),
                }
              : message,
          ),
        )
      } else {
        const errorText = error instanceof Error ? error.message : '未知流式错误'
        if (!streamFailure) {
          setLocalMessages((current) => [
            ...current.map((message) =>
              message.id === assistantMessage.id ? { ...message, status: 'error' as const } : message,
            ),
            {
              id: `local-error-${turnId}-${crypto.randomUUID()}`,
              turnId,
              seqInTurn: 5,
              role: SESSION_TIMELINE_ROLE.ERROR,
              content: errorText,
              createdAt: new Date().toISOString(),
              speaker: errorSpeaker(),
              status: 'error',
              canCopy: Boolean(errorText.trim()),
              canRetry: false,
              canEdit: false,
              canDelete: false,
            },
          ])
        }
        showToast(errorText)
      }
    } finally {
      setSending(false)
      abortRef.current = null
      const refreshed = await refreshSessionData({ silent: true, clearAccurateUsage: !completedTurn })
      if (!refreshed) showToast('发送完成，但刷新失败，请手动刷新页面')
    }
  }, [appendStreamEvent, composerText, currentNarrativeStyle, inputMode, lastTurnId, playerCharacter, playerCharacterInvalid, refreshSessionData, session, sessionId, showToast])

  const handleStop = useCallback(() => {
    abortRef.current?.abort()
    showToast('已停止当前流式响应')
  }, [showToast])

  const handleConfirm = () => {
    const action = confirmRequest?.onConfirm
    setConfirmRequest(null)
    action?.()
  }

  return (
    <main
      style={gridStyle}
      data-workspace={session?.workspace ?? ''}
      data-story-id={session?.storyId ?? ''}
      data-session-id={sessionId}
      className="min-h-screen bg-[#f7f8fc] text-slate-900 dark:bg-[#0b1020] dark:text-slate-100 lg:grid lg:h-screen lg:min-h-0 lg:grid-cols-[var(--session-grid-columns)] lg:overflow-hidden"
    >
      {mobilePanel ? (
        <button
          type="button"
          aria-label="关闭侧栏"
          onClick={() => setMobilePanel(null)}
          className="fixed inset-0 z-30 bg-slate-950/20 backdrop-blur-[1px] dark:bg-slate-950/60 lg:hidden"
        />
      ) : null}

      <SessionLeftRail
        scene={sceneQuery.data}
        sceneLoading={sceneQuery.isLoading}
        characters={characters}
        charactersLoading={charactersQuery.isLoading}
        collapsed={leftCollapsed}
        mobileOpen={mobilePanel === 'left'}
        onCloseMobile={() => setMobilePanel(null)}
        onToggleCollapsed={() => setLeftCollapsed((current) => !current)}
      />
      <button
        type="button"
        aria-label="调整左侧栏宽度"
        onPointerDown={startDrag('left')}
        disabled={leftCollapsed}
        className="group hidden cursor-col-resize bg-slate-100 transition hover:bg-violet-50 disabled:cursor-default disabled:opacity-40 dark:bg-slate-800 dark:hover:bg-violet-500/10 lg:flex lg:h-screen lg:items-stretch lg:justify-center"
      >
        <span className="my-auto h-16 w-1 rounded-full bg-slate-300 transition group-hover:bg-violet-400 dark:bg-slate-600 dark:group-hover:bg-violet-400" />
      </button>

      <section
        style={sessionExperienceStyle}
        className="flex min-h-screen min-w-0 flex-col lg:h-screen lg:min-h-0"
      >
        <header className="flex min-h-[73px] flex-wrap items-center justify-between gap-3 border-b border-slate-200 bg-white px-4 py-3 dark:border-slate-800 dark:bg-slate-950/90 sm:px-6">
          <div className="min-w-0">
            <h1 className="truncate text-lg font-black text-slate-950 dark:text-slate-100 sm:text-xl">{session?.title ?? '加载会话中'}</h1>
            <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs font-semibold text-slate-400 dark:text-slate-400">
              <span>
                story <code className="font-mono text-slate-600 dark:text-slate-300">#{session?.storyId ?? '-'}</code>
              </span>
              <span>
                session <code className="font-mono text-slate-600 dark:text-slate-300">{session?.id ?? sessionId}</code>
              </span>
              {session?.updatedAt ? <span>更新 {formatDateTime(session.updatedAt)}</span> : null}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setMobilePanel('left')}
              className="flex h-10 w-10 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-600 shadow-sm transition hover:border-violet-200 hover:bg-violet-50 hover:text-violet-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:border-violet-500/60 dark:hover:bg-violet-500/10 dark:hover:text-violet-200 lg:hidden"
              aria-label="打开场景栏"
            >
              <AlignJustify size={18} />
            </button>
            <button
              type="button"
              onClick={() => setMobilePanel('right')}
              className="flex h-10 w-10 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-600 shadow-sm transition hover:border-violet-200 hover:bg-violet-50 hover:text-violet-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:border-violet-500/60 dark:hover:bg-violet-500/10 dark:hover:text-violet-200 lg:hidden"
              aria-label="打开状态栏"
            >
              <TableProperties size={18} />
            </button>
            <ThemeSwitcher menuAlign="right" menuSide="bottom" triggerSize="compact" />
            <button
              type="button"
              onClick={() => router.push('/sessions')}
              className="flex h-10 items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 text-sm font-black text-slate-700 shadow-sm transition hover:border-violet-200 hover:bg-violet-50 hover:text-violet-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:border-violet-500/60 dark:hover:bg-violet-500/10 dark:hover:text-violet-200"
            >
              <LogOut size={16} />
              退出
            </button>
            <SessionSettingsMenu
              open={settingsOpen}
              leftCollapsed={leftCollapsed}
              rightCollapsed={rightCollapsed}
              fontScale={fontScale}
              playerCharacter={playerCharacter}
              onToggleOpen={() => setSettingsOpen((current) => !current)}
              onToggleSide={(side) => {
                if (side === 'left') setLeftCollapsed((current) => !current)
                else setRightCollapsed((current) => !current)
              }}
              onFontScaleChange={setFontScale}
              onResetFontScale={() => setFontScale(SESSION_FONT_SCALE_DEFAULT)}
              onOpenRoleDialog={openRoleDialog}
            />
          </div>
        </header>

        <SessionTimeline
          sessionId={sessionId}
          messages={visibleMessages}
          forceScrollKey={forceScrollKey}
          editingMessageId={editingMessageId}
          editDraft={editDraft}
          onEditDraftChange={setEditDraft}
          onCopy={handleCopy}
          onRetry={handleRetry}
          onEdit={handleStartEdit}
          onDelete={handleDelete}
          onEditCancel={() => {
            setEditingMessageId(null)
            setEditDraft('')
            showToast('已取消编辑')
          }}
          onEditSend={handleSendEdit}
        />

        <SessionComposer
          sessionId={sessionId}
          text={composerText}
          mode={inputMode}
          narrativeStyleId={narrativeStyleId}
          narrativeStyles={narrativeStyles}
          sending={sending}
          disabled={roleSelectionBlocked}
          contextUsage={contextUsage}
          contextUsageLoading={contextPreviewQuery.isLoading || contextPreviewQuery.isFetching}
          onTextChange={handleComposerTextChange}
          onModeChange={setInputMode}
          onNarrativeStyleChange={setNarrativeStyleId}
          onSend={handleSend}
          onStop={handleStop}
        />
      </section>

      <button
        type="button"
        aria-label="调整右侧栏宽度"
        onPointerDown={startDrag('right')}
        disabled={rightCollapsed}
        className="group hidden cursor-col-resize bg-slate-100 transition hover:bg-violet-50 disabled:cursor-default disabled:opacity-40 lg:flex lg:h-screen lg:items-stretch lg:justify-center"
      >
        <span className="my-auto h-16 w-1 rounded-full bg-slate-300 transition group-hover:bg-violet-400" />
      </button>
      <SessionRightRail
        tables={statusTablesQuery.data ?? []}
        loading={statusTablesQuery.isLoading}
        collapsed={rightCollapsed}
        mobileOpen={mobilePanel === 'right'}
        onCloseMobile={() => setMobilePanel(null)}
        onToggleCollapsed={() => setRightCollapsed((current) => !current)}
      />

      {confirmRequest ? (
        <ConfirmDialog
          title={confirmRequest.title}
          heading={confirmRequest.heading}
          body={confirmRequest.body}
          confirmLabel={confirmRequest.confirmLabel}
          pending={false}
          onClose={() => setConfirmRequest(null)}
          onConfirm={handleConfirm}
        />
      ) : null}
      <PlayerCharacterDialog
        open={roleDialogOpen}
        required={roleDialogRequired}
        characters={characters}
        loading={charactersQuery.isLoading}
        currentPlayer={playerCharacter}
        selectedCharacterId={selectedRoleCharacterId}
        pending={bindingRole}
        error={roleBindError}
        onSelect={setSelectedRoleCharacterId}
        onSubmit={submitRoleDialog}
        onClose={closeRoleDialog}
      />
      <Toast message={toastMessage} />
    </main>
  )
}
