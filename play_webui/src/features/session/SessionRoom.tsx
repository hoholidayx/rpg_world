'use client'

import { CSSProperties, PointerEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { AlignJustify, LogOut, TableProperties } from 'lucide-react'
import { ConfirmDialog } from '@/components/common/Dialog'
import { ThemeSwitcher } from '@/components/theme/ThemeSwitcher'
import { listStoryCharacters } from '@/lib/api/characters'
import { getCurrentScene } from '@/lib/api/scene'
import {
  deleteSessionMessage,
  getSession,
  getSessionHistory,
  retrySessionTurn,
  updateSessionMessage,
} from '@/lib/api/sessions'
import { listSessionStatusTables } from '@/lib/api/statusTables'
import { consumeChatStream } from '@/lib/stream/sse'
import { cn } from '@/lib/utils/cn'
import type { CharacterCard } from '@/types/characters'
import type { CurrentAgentStreamEvent } from '@/types/stream'
import { SessionComposer } from './SessionComposer'
import { SessionLeftRail, SessionRightRail } from './SessionSideRails'
import { SessionSettingsMenu } from './SessionSettingsMenu'
import { SessionTimeline } from './SessionTimeline'
import {
  findCharacterByName,
  firstLetter,
  formatDateTime,
  getCharacterAvatarUrl,
  pickPlayerCharacter,
} from './sessionRoomHelpers'
import type {
  ConfirmRequest,
  NarrativeStyle,
  NarrativeStyleId,
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

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value))
}

function makePlayerSpeaker(character: CharacterCard | null): SessionSpeaker {
  return {
    name: character?.name ?? '你',
    label: 'IC',
    avatarUrl: getCharacterAvatarUrl(character),
    fallback: firstLetter(character?.name ?? '你'),
    tone: 'player',
  }
}

function makeAssistantSpeaker(): SessionSpeaker {
  // Assistant output is currently one mixed narrative block. Character-level
  // avatars need a future structured segments layer instead of speaker metadata.
  return {
    name: '旁白',
    avatarUrl: '',
    fallback: '旁',
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

function thinkingSpeaker(): SessionSpeaker {
  return {
    name: '思考中',
    fallback: '…',
    tone: 'thinking',
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
    role: 'assistant',
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
  if (role === 'user' || role === 'assistant' || role === 'tool' || role === 'system') return role
  return 'assistant'
}

function makeHistorySpeaker(
  message: HistoryMessage,
  playerCharacter: CharacterCard | null,
): SessionSpeaker {
  const role = timelineRole(message.role)

  if (role === 'user') {
    return makePlayerSpeaker(playerCharacter)
  }

  if (role === 'assistant') {
    return makeAssistantSpeaker()
  }

  if (role === 'tool') return toolSpeaker()
  return systemSpeaker()
}

function mapHistoryToMessages({
  turns,
  playerCharacter,
}: {
  turns: Awaited<ReturnType<typeof getSessionHistory>> | undefined
  playerCharacter: CharacterCard | null
}): SessionTimelineMessage[] {
  return (turns ?? []).flatMap((turn, turnIndex) => {
    const turnHasPersistentUser = turn.messages.some(
      (message) => Boolean(message.messageId) && timelineRole(message.role) === 'user',
    )

    return turn.messages.map((message, messageIndex) => {
      const role = timelineRole(message.role)
      const persistent = Boolean(message.messageId)
      const turnActionRole = role === 'user' || role === 'assistant'

      return {
        id: message.messageId ? `history-${message.messageId}` : `history-${turn.turnId || turnIndex + 1}-${messageIndex}`,
        messageId: message.messageId || undefined,
        turnId: message.turnId || turn.turnId || turnIndex + 1,
        seqInTurn: message.seqInTurn || messageIndex + 1,
        role,
        content: message.content,
        metadata: message.metadata,
        createdAt: message.createdAt,
        speaker: makeHistorySpeaker(message, playerCharacter),
        status: message.role === 'assistant' ? 'done' : undefined,
        canCopy: Boolean(message.content.trim()),
        canRetry: persistent && turnActionRole && turnHasPersistentUser,
        canEdit: persistent && turnActionRole,
        canDelete: persistent && turnActionRole,
      }
    })
  })
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
  const [editingMessageId, setEditingMessageId] = useState<string | null>(null)
  const [editDraft, setEditDraft] = useState('')
  const [confirmRequest, setConfirmRequest] = useState<ConfirmRequest | null>(null)
  const [toastMessage, setToastMessage] = useState('')
  const [sending, setSending] = useState(false)
  const toastTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const abortRef = useRef<AbortController | null>(null)

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
    queryKey: ['play-session-status-tables', sessionId, 'normal'],
    queryFn: () => listSessionStatusTables(sessionId, 'normal'),
  })

  const charactersQuery = useQuery({
    queryKey: ['play-story-characters', session?.workspace, session?.storyId],
    enabled: Boolean(session?.workspace && session?.storyId),
    queryFn: () => listStoryCharacters(session?.workspace ?? '', session?.storyId ?? 0),
  })

  const characters = charactersQuery.data ?? []
  const playerCharacter = useMemo(() => {
    const scenePlayer = sceneQuery.data?.presentCharacters
      ?.map((name) => findCharacterByName(characters, name))
      .find((character): character is CharacterCard => Boolean(character))
    return scenePlayer ?? pickPlayerCharacter(characters)
  }, [characters, sceneQuery.data?.presentCharacters])

  const baseMessages = useMemo(
    () => mapHistoryToMessages({ turns: historyQuery.data, playerCharacter }),
    [historyQuery.data, playerCharacter],
  )

  const visibleMessages = useMemo(() => {
    return [...baseMessages, ...localMessages]
      .sort((first, second) => first.turnId - second.turnId || (first.seqInTurn ?? 0) - (second.seqInTurn ?? 0))
  }, [baseMessages, localMessages])

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

  useEffect(() => {
    setLocalMessages([])
    setEditingMessageId(null)
    setEditDraft('')
    setComposerText('')
    setMobilePanel(null)
    setSettingsOpen(false)
  }, [sessionId])

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

  const startDrag = (side: 'left' | 'right') => (event: PointerEvent<HTMLButtonElement>) => {
    event.preventDefault()
    setDragState({
      side,
      startX: event.clientX,
      startLeft: leftWidth,
      startRight: rightWidth,
    })
  }

  const refreshSessionData = useCallback(async ({ silent = false }: { silent?: boolean } = {}) => {
    try {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['play-session-history', sessionId] }),
        queryClient.invalidateQueries({ queryKey: ['play-session-scene', sessionId] }),
        queryClient.invalidateQueries({ queryKey: ['play-session-status-tables', sessionId] }),
      ])
      setLocalMessages([])
      setEditingMessageId(null)
      setEditDraft('')
      return true
    } catch {
      if (!silent) showToast('刷新失败，请手动刷新页面')
      return false
    }
  }, [queryClient, sessionId, showToast])

  const requestConfirm = useCallback((request: ConfirmRequest) => {
    setConfirmRequest(request)
  }, [])

  const performRetry = useCallback(async (message: SessionTimelineMessage) => {
    if (!message.canRetry) {
      showToast('当前回合不可重试')
      return
    }
    showToast(`正在重试 turn #${message.turnId}`)
    try {
      await retrySessionTurn(sessionId, message.turnId)
      const refreshed = await refreshSessionData({ silent: true })
      showToast(refreshed ? `已重试 turn #${message.turnId}` : '重试完成，但刷新失败，请手动刷新页面')
    } catch (error) {
      showToast(error instanceof Error ? error.message : '重试失败')
    }
  }, [refreshSessionData, sessionId, showToast])

  const handleRetry = useCallback((message: SessionTimelineMessage) => {
    if (!message.canRetry) {
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
    if (!message.canEdit || !message.messageId) {
      showToast('当前消息不可编辑')
      return
    }
    setEditingMessageId(message.id)
    setEditDraft(message.content)
  }, [showToast])

  const performSendEdited = useCallback(async (message: SessionTimelineMessage, text: string) => {
    if (!message.canEdit || !message.messageId) {
      showToast('当前消息不可编辑')
      return
    }
    showToast('正在发送编辑')
    try {
      await updateSessionMessage(sessionId, message.messageId, text)
      const refreshed = await refreshSessionData({ silent: true })
      showToast(refreshed ? '已发送编辑' : '编辑已提交，但刷新失败，请手动刷新页面')
    } catch (error) {
      showToast(error instanceof Error ? error.message : '编辑失败')
    }
  }, [refreshSessionData, sessionId, showToast])

  const handleSendEdit = useCallback((message: SessionTimelineMessage) => {
    if (!message.canEdit || !message.messageId) {
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
        body: `发送编辑后的 turn #${message.turnId} 会影响后续回合；用户消息会从该 turn 重新生成，其他消息会写入修改后的内容。`,
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

  const appendStreamEvent = useCallback((event: CurrentAgentStreamEvent, assistantMessageId: string, turnId: number) => {
    if (event.kind === 'text') {
      setLocalMessages((current) =>
        current.map((message) =>
          message.id === assistantMessageId
            ? {
                ...message,
                content: `${message.content}${event.content ?? ''}`,
                status: 'streaming',
                canCopy: Boolean(`${message.content}${event.content ?? ''}`.trim()),
              }
            : message,
        ),
      )
      return
    }

    if (event.kind === 'thinking') {
      setLocalMessages((current) => [
        ...current,
        {
          id: `local-thinking-${turnId}-${crypto.randomUUID()}`,
          turnId,
          seqInTurn: 3,
          role: 'thinking',
          content: event.content ?? '思考中...',
          createdAt: new Date().toISOString(),
          speaker: thinkingSpeaker(),
          status: 'local',
          canCopy: Boolean((event.content ?? '思考中...').trim()),
          canRetry: false,
          canEdit: false,
          canDelete: false,
        },
      ])
      return
    }

    if (event.kind === 'tool_call' || event.kind === 'tool_result') {
      setLocalMessages((current) => [
        ...current,
        {
          id: `local-tool-${turnId}-${crypto.randomUUID()}`,
          turnId,
          seqInTurn: 4,
          role: 'tool',
          content: event.tool_result_preview ?? event.tool_name ?? '工具事件',
          createdAt: new Date().toISOString(),
          speaker: toolSpeaker(),
          status: 'local',
          canCopy: Boolean((event.tool_result_preview ?? event.tool_name ?? '工具事件').trim()),
          canRetry: false,
          canEdit: false,
          canDelete: false,
        },
      ])
      return
    }

    if (event.kind === 'done') {
      setLocalMessages((current) =>
        current.map((message) =>
          message.id === assistantMessageId
            ? { ...message, status: 'done', content: message.content || '已完成。', canCopy: Boolean((message.content || '已完成。').trim()) }
            : message,
        ),
      )
      return
    }

    if (event.kind === 'error') {
      setLocalMessages((current) => [
        ...current.map((message) =>
          message.id === assistantMessageId ? { ...message, status: 'error' as const } : message,
        ),
        {
          id: `local-error-${turnId}-${crypto.randomUUID()}`,
          turnId,
          seqInTurn: 5,
          role: 'error',
          content: event.content ?? '流式请求失败',
          createdAt: new Date().toISOString(),
          speaker: errorSpeaker(),
          status: 'error',
          canCopy: Boolean((event.content ?? '流式请求失败').trim()),
          canRetry: false,
          canEdit: false,
          canDelete: false,
        },
      ])
    }
  }, [])

  const handleSend = useCallback(async () => {
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
      role: 'user',
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
    setComposerText('')
    setSending(true)
    setLocalMessages((current) => [...current, userMessage, assistantMessage])

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
          onEvent: (event) => appendStreamEvent(event, assistantMessage.id, turnId),
        },
      )
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
        setLocalMessages((current) => [
          ...current.map((message) =>
            message.id === assistantMessage.id ? { ...message, status: 'error' as const } : message,
          ),
          {
            id: `local-error-${turnId}-${crypto.randomUUID()}`,
            turnId,
            seqInTurn: 5,
            role: 'error',
            content: error instanceof Error ? error.message : '未知流式错误',
            createdAt: new Date().toISOString(),
            speaker: errorSpeaker(),
            status: 'error',
            canCopy: Boolean((error instanceof Error ? error.message : '未知流式错误').trim()),
            canRetry: false,
            canEdit: false,
            canDelete: false,
          },
        ])
      }
    } finally {
      setSending(false)
      abortRef.current = null
      const refreshed = await refreshSessionData({ silent: true })
      if (!refreshed) showToast('发送完成，但刷新失败，请手动刷新页面')
    }
  }, [appendStreamEvent, composerText, currentNarrativeStyle, inputMode, lastTurnId, playerCharacter, refreshSessionData, sessionId, showToast])

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

      <section className="flex min-h-screen min-w-0 flex-col lg:h-screen lg:min-h-0">
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
              onToggleOpen={() => setSettingsOpen((current) => !current)}
              onToggleSide={(side) => {
                if (side === 'left') setLeftCollapsed((current) => !current)
                else setRightCollapsed((current) => !current)
              }}
            />
          </div>
        </header>

        <SessionTimeline
          messages={visibleMessages}
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
          onTextChange={setComposerText}
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
      <Toast message={toastMessage} />
    </main>
  )
}
