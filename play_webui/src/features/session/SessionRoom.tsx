'use client'

import { CSSProperties, PointerEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { useQuery } from '@tanstack/react-query'
import { AlignJustify, LogOut, TableProperties } from 'lucide-react'
import { ConfirmDialog } from '@/components/common/Dialog'
import { listStoryCharacters } from '@/lib/api/characters'
import { getCurrentScene } from '@/lib/api/scene'
import { getSession, getSessionHistory } from '@/lib/api/sessions'
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

const quickActions = [
  '我仔细观察周围最异常的细节，并判断它是否会带来危险。',
  '我向在场角色追问刚才那句话里被刻意回避的部分。',
  '我放慢动作，先确认随身物品、线索和当前处境。',
  '我主动推进到下一处关键地点，留意途中是否有人跟踪。',
]

type DragState = {
  side: 'left' | 'right'
  startX: number
  startLeft: number
  startRight: number
}

type MobilePanel = 'left' | 'right' | null

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

function makeAssistantSpeaker(content: string, characters: CharacterCard[], playerCharacter: CharacterCard | null): SessionSpeaker {
  const candidates = characters.filter((character) => character.id !== playerCharacter?.id)
  const matched = candidates.find((character) => content.includes(character.name)) ?? candidates[0] ?? null
  if (matched) {
    return {
      name: matched.name,
      avatarUrl: getCharacterAvatarUrl(matched),
      fallback: firstLetter(matched.name),
      tone: 'assistant',
    }
  }
  return {
    name: 'Narrator',
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

function assistantPreview(turnId: number, characters: CharacterCard[], playerCharacter: CharacterCard | null): SessionTimelineMessage {
  const content = '雾气在前方慢慢散开，新的线索浮出水面。当前版本仅做前端预览；真正的重试、编辑与删除会在后续 turn API 支持后持久化。'
  return {
    id: `local-retry-${turnId}-${crypto.randomUUID()}`,
    turnId,
    role: 'assistant',
    content,
    createdAt: new Date().toISOString(),
    speaker: makeAssistantSpeaker(content, characters, playerCharacter),
    status: 'local',
  }
}

function streamPlaceholder(turnId: number, characters: CharacterCard[], playerCharacter: CharacterCard | null): SessionTimelineMessage {
  return {
    id: `local-stream-${turnId}-${crypto.randomUUID()}`,
    turnId,
    role: 'assistant',
    content: '',
    createdAt: new Date().toISOString(),
    speaker: makeAssistantSpeaker('', characters, playerCharacter),
    status: 'streaming',
  }
}

function mapHistoryToMessages({
  turns,
  characters,
  playerCharacter,
}: {
  turns: Awaited<ReturnType<typeof getSessionHistory>> | undefined
  characters: CharacterCard[]
  playerCharacter: CharacterCard | null
}): SessionTimelineMessage[] {
  const playerSpeaker = makePlayerSpeaker(playerCharacter)

  return (turns ?? []).flatMap((turn, index) => {
    const turnId = turn.turnId || index + 1
    const userMessage: SessionTimelineMessage = {
      id: `history-${turnId}-user`,
      turnId,
      role: 'user',
      content: turn.userMessage,
      createdAt: turn.createdAt,
      speaker: playerSpeaker,
    }

    if (!turn.assistantMessage) return [userMessage]

    const assistantMessage: SessionTimelineMessage = {
      id: `history-${turnId}-assistant`,
      turnId,
      role: 'assistant',
      content: turn.assistantMessage,
      createdAt: turn.createdAt,
      speaker: makeAssistantSpeaker(turn.assistantMessage, characters, playerCharacter),
      status: 'done',
    }

    return [userMessage, assistantMessage]
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
  const [hiddenMessageIds, setHiddenMessageIds] = useState<Set<string>>(() => new Set())
  const [hiddenFromTurn, setHiddenFromTurn] = useState<number | null>(null)
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
    () => mapHistoryToMessages({ turns: historyQuery.data, characters, playerCharacter }),
    [characters, historyQuery.data, playerCharacter],
  )

  const visibleMessages = useMemo(() => {
    const visibleBase = hiddenFromTurn === null
      ? baseMessages
      : baseMessages.filter((message) => message.turnId < hiddenFromTurn)
    return [...visibleBase, ...localMessages]
      .filter((message) => !hiddenMessageIds.has(message.id))
      .sort((first, second) => first.turnId - second.turnId)
  }, [baseMessages, hiddenFromTurn, hiddenMessageIds, localMessages])

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
    setHiddenMessageIds(new Set())
    setHiddenFromTurn(null)
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

  const hideFromTurn = useCallback((turnId: number) => {
    setHiddenFromTurn((current) => (current === null ? turnId : Math.min(current, turnId)))
    setLocalMessages((current) => current.filter((message) => message.turnId < turnId))
    setEditingMessageId(null)
    setEditDraft('')
  }, [])

  const requestConfirm = useCallback((request: ConfirmRequest) => {
    setConfirmRequest(request)
  }, [])

  const performRetry = useCallback((message: SessionTimelineMessage) => {
    hideFromTurn(message.turnId)
    setLocalMessages((current) => [...current, assistantPreview(message.turnId, characters, playerCharacter)])
    showToast(`已删除 turn #${message.turnId} 及之后内容，并触发重试预览`)
  }, [characters, hideFromTurn, playerCharacter, showToast])

  const handleRetry = useCallback((message: SessionTimelineMessage) => {
    if (message.turnId >= lastTurnId) {
      performRetry(message)
      return
    }
    requestConfirm({
      title: '确认重试',
      heading: '该操作会影响后续回合',
      body: `重试 turn #${message.turnId} 会删除该 turn 以及之后更新的所有 turn。当前版本只做前端预览，不会写入后端。`,
      confirmLabel: '确认重试',
      onConfirm: () => performRetry(message),
    })
  }, [lastTurnId, performRetry, requestConfirm])

  const handleCopy = useCallback((message: SessionTimelineMessage) => {
    navigator.clipboard?.writeText(message.content).then(
      () => showToast('已复制当前消息'),
      () => showToast('复制失败，请手动选择文本'),
    )
  }, [showToast])

  const handleStartEdit = useCallback((message: SessionTimelineMessage) => {
    setEditingMessageId(message.id)
    setEditDraft(message.content)
  }, [])

  const performSendEdited = useCallback((message: SessionTimelineMessage, text: string) => {
    hideFromTurn(message.turnId)
    const editedMessage: SessionTimelineMessage = {
      ...message,
      id: `local-edit-${message.turnId}-${crypto.randomUUID()}`,
      content: text,
      createdAt: new Date().toISOString(),
      status: 'local',
    }
    setLocalMessages((current) => {
      const next = [...current, editedMessage]
      if (message.role === 'user') {
        next.push(assistantPreview(message.turnId, characters, playerCharacter))
      }
      return next
    })
    showToast(`已发送编辑后的 turn #${message.turnId} 预览`)
  }, [characters, hideFromTurn, playerCharacter, showToast])

  const handleSendEdit = useCallback((message: SessionTimelineMessage) => {
    const text = editDraft.trim()
    if (!text) {
      showToast('编辑内容不能为空')
      return
    }
    if (message.turnId < lastTurnId) {
      requestConfirm({
        title: '确认发送编辑',
        heading: '该操作会影响后续回合',
        body: `发送编辑后的 turn #${message.turnId} 会删除该 turn 以及之后更新的所有 turn，并使用新的内容重新生成。当前版本只做前端预览。`,
        confirmLabel: '确认发送',
        onConfirm: () => performSendEdited(message, text),
      })
      return
    }
    performSendEdited(message, text)
  }, [editDraft, lastTurnId, performSendEdited, requestConfirm, showToast])

  const handleDelete = useCallback((message: SessionTimelineMessage) => {
    requestConfirm({
      title: '确认删除',
      heading: '删除当前消息',
      body: '删除会从当前时间线移除这条消息。当前版本只做前端预览，不会写入后端。',
      confirmLabel: '确认删除',
      onConfirm: () => {
        setHiddenMessageIds((current) => {
          const next = new Set(current)
          next.add(message.id)
          return next
        })
        showToast(`已删除 turn #${message.turnId} 中的当前消息`)
      },
    })
  }, [requestConfirm, showToast])

  const insertComposerText = useCallback((text: string) => {
    setComposerText((current) => {
      const prefix = current.trim() ? '\n' : ''
      return `${current}${prefix}${text}`
    })
  }, [])

  const appendStreamEvent = useCallback((event: CurrentAgentStreamEvent, assistantMessageId: string, turnId: number) => {
    if (event.kind === 'text') {
      setLocalMessages((current) =>
        current.map((message) =>
          message.id === assistantMessageId
            ? {
                ...message,
                content: `${message.content}${event.content ?? ''}`,
                status: 'streaming',
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
          role: 'thinking',
          content: event.content ?? '思考中...',
          createdAt: new Date().toISOString(),
          speaker: thinkingSpeaker(),
          status: 'local',
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
          role: 'tool',
          content: event.tool_result_preview ?? event.tool_name ?? '工具事件',
          createdAt: new Date().toISOString(),
          speaker: toolSpeaker(),
          status: 'local',
        },
      ])
      return
    }

    if (event.kind === 'done') {
      setLocalMessages((current) =>
        current.map((message) =>
          message.id === assistantMessageId
            ? { ...message, status: 'done', content: message.content || '已完成。' }
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
          role: 'error',
          content: event.content ?? '流式请求失败',
          createdAt: new Date().toISOString(),
          speaker: errorSpeaker(),
          status: 'error',
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
      role: 'user',
      content: text,
      createdAt: new Date().toISOString(),
      speaker: { ...playerSpeaker, label: inputMode.toUpperCase() },
      hiddenPrompt: style.prompt,
      status: style.prompt ? 'local' : undefined,
    }
    const assistantMessage = streamPlaceholder(turnId, characters, playerCharacter)
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
              ? { ...message, status: 'done', content: message.content || '已停止当前流式响应。' }
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
            role: 'error',
            content: error instanceof Error ? error.message : '未知流式错误',
            createdAt: new Date().toISOString(),
            speaker: errorSpeaker(),
            status: 'error',
          },
        ])
      }
    } finally {
      setSending(false)
      abortRef.current = null
    }
  }, [appendStreamEvent, characters, composerText, currentNarrativeStyle, inputMode, lastTurnId, playerCharacter, sessionId, showToast])

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
      className="min-h-screen bg-[#f7f8fc] text-slate-900 lg:grid lg:h-screen lg:min-h-0 lg:grid-cols-[var(--session-grid-columns)] lg:overflow-hidden"
    >
      {mobilePanel ? (
        <button
          type="button"
          aria-label="关闭侧栏"
          onClick={() => setMobilePanel(null)}
          className="fixed inset-0 z-30 bg-slate-950/20 backdrop-blur-[1px] lg:hidden"
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
        className="group hidden cursor-col-resize bg-slate-100 transition hover:bg-violet-50 disabled:cursor-default disabled:opacity-40 lg:flex lg:h-screen lg:items-stretch lg:justify-center"
      >
        <span className="my-auto h-16 w-1 rounded-full bg-slate-300 transition group-hover:bg-violet-400" />
      </button>

      <section className="flex min-h-screen min-w-0 flex-col lg:h-screen lg:min-h-0">
        <header className="flex min-h-[73px] flex-wrap items-center justify-between gap-3 border-b border-slate-200 bg-white px-4 py-3 sm:px-6">
          <div className="min-w-0">
            <h1 className="truncate text-lg font-black text-slate-950 sm:text-xl">{session?.title ?? '加载会话中'}</h1>
            <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs font-semibold text-slate-400">
              <span>
                story <code className="font-mono text-slate-600">#{session?.storyId ?? '-'}</code>
              </span>
              <span>
                session <code className="font-mono text-slate-600">{session?.id ?? sessionId}</code>
              </span>
              {session?.updatedAt ? <span>更新 {formatDateTime(session.updatedAt)}</span> : null}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setMobilePanel('left')}
              className="flex h-10 w-10 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-600 shadow-sm transition hover:border-violet-200 hover:bg-violet-50 hover:text-violet-700 lg:hidden"
              aria-label="打开场景栏"
            >
              <AlignJustify size={18} />
            </button>
            <button
              type="button"
              onClick={() => setMobilePanel('right')}
              className="flex h-10 w-10 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-600 shadow-sm transition hover:border-violet-200 hover:bg-violet-50 hover:text-violet-700 lg:hidden"
              aria-label="打开状态栏"
            >
              <TableProperties size={18} />
            </button>
            <button
              type="button"
              onClick={() => router.push('/sessions')}
              className="flex h-10 items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 text-sm font-black text-slate-700 shadow-sm transition hover:border-violet-200 hover:bg-violet-50 hover:text-violet-700"
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
          quickActions={quickActions}
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
          onInsertQuickAction={insertComposerText}
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
