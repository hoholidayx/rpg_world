import { ChevronDown, Copy, MoreHorizontal, Pencil, RotateCcw, Trash2 } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { HistoryPage } from '@/types/session'
import type { ContextUsageSnapshot } from '@/types/contextUsage'
import { cn } from '@/lib/utils/cn'
import { SessionAvatar } from './SessionAvatar'
import {
  ASSISTANT_TEXT_SEGMENT_KIND,
  parseAssistantTextSegments,
  type AssistantTextSegment,
} from './assistantTextSegments'
import { formatMessageTime } from './sessionRoomHelpers'
import {
  HISTORY_LOAD_DIRECTION,
  SESSION_MESSAGE_STATUS,
  SESSION_TIMELINE_ROLE,
  type HistoryLoadDirection,
  type SessionTimelineMessage,
} from './sessionRoomTypes'

const BOUNDARY_LOAD_SOURCE = {
  AUTO: 'auto',
  MANUAL: 'manual',
} as const

type BoundaryLoadSource = (typeof BOUNDARY_LOAD_SOURCE)[keyof typeof BOUNDARY_LOAD_SOURCE]

const USER_SCROLL_DIRECTION = {
  UP: 'up',
  DOWN: 'down',
} as const

type UserScrollDirection = (typeof USER_SCROLL_DIRECTION)[keyof typeof USER_SCROLL_DIRECTION]

const TIMELINE_SCROLL = {
  programmaticGuardMs: 600,
  boundaryCooldownMs: 350,
  overflowTolerancePx: 24,
  stickToBottomDistancePx: 160,
  userScrollDeltaThresholdPx: 2,
} as const

function formatUsageToken(value: number | null | undefined) {
  if (value === null || value === undefined) return '-'
  const rounded = Math.round(value)
  if (rounded >= 1_000_000) return `${formatCompactNumber(rounded / 1_000_000)}M`
  if (rounded >= 1_000) return `${formatCompactNumber(rounded / 1_000)}K`
  return rounded.toLocaleString()
}

function formatCompactNumber(value: number) {
  const fixed = value >= 10 ? value.toFixed(1) : value.toFixed(2)
  return fixed.replace(/\.0+$|(\.\d*[1-9])0+$/, '$1')
}

function usageSourceLabel(usage: ContextUsageSnapshot) {
  if (usage.source === 'provider_usage') return 'provider 返回'
  if (usage.source === 'fallback_estimate') return '兜底估算，不含子 Agent'
  if (usage.source === 'unavailable') return '未知'
  return '主上下文估算，不含子 Agent'
}

function usageLineTitle(usage: ContextUsageSnapshot) {
  if (usage.source === 'provider_usage') return '本轮实际总消耗（含子 Agent）'
  return '主上下文估算兜底'
}

function AssistantUsageLine({ usage }: { usage: ContextUsageSnapshot }) {
  return (
    <div className="mt-3 border-t border-slate-200/80 pt-2 text-[11px] font-bold leading-5 text-slate-400 dark:border-slate-700/80 dark:text-slate-500">
      {usageLineTitle(usage)}：{formatUsageToken(usage.totalTokens)} total / prompt {formatUsageToken(usage.promptTokens ?? usage.usedTokens)} / completion {formatUsageToken(usage.completionTokens)} / cache {formatUsageToken(usage.cachedTokens)} · {usageSourceLabel(usage)}
    </div>
  )
}

function MiniButton({
  label,
  onClick,
  children,
  disabled = false,
}: {
  label: string
  onClick: () => void
  children: React.ReactNode
  disabled?: boolean
}) {
  return (
    <button
      type="button"
      onClick={disabled ? undefined : onClick}
      disabled={disabled}
      aria-label={label}
      title={label}
      className="flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-500 shadow-sm transition hover:border-violet-200 hover:bg-violet-50 hover:text-violet-700 disabled:cursor-not-allowed disabled:border-slate-100 disabled:bg-slate-50 disabled:text-slate-300 disabled:shadow-none disabled:hover:border-slate-100 disabled:hover:bg-slate-50 disabled:hover:text-slate-300 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:shadow-black/30 dark:hover:border-violet-500/60 dark:hover:bg-violet-500/10 dark:hover:text-violet-200 dark:disabled:border-slate-800 dark:disabled:bg-slate-900/60 dark:disabled:text-slate-600 dark:disabled:hover:border-slate-800 dark:disabled:hover:bg-slate-900/60 dark:disabled:hover:text-slate-600"
    >
      {children}
    </button>
  )
}

function MessageActions({
  message,
  moreOpen,
  onToggleMore,
  onCopy,
  onRetry,
  onEdit,
  onDelete,
}: {
  message: SessionTimelineMessage
  moreOpen: boolean
  onToggleMore: () => void
  onCopy: (message: SessionTimelineMessage) => void
  onRetry: (message: SessionTimelineMessage) => void
  onEdit: (message: SessionTimelineMessage) => void
  onDelete: (message: SessionTimelineMessage) => void
}) {
  const canCopy = message.canCopy ?? Boolean(message.content.trim())
  const canRetry = Boolean(message.canRetry)
  const canEdit = Boolean(message.canEdit)
  const canDelete = Boolean(message.canDelete)

  return (
    <div className="relative mt-2 flex items-center gap-1.5">
      <MiniButton label="复制" disabled={!canCopy} onClick={() => onCopy(message)}>
        <Copy size={14} />
      </MiniButton>
      {canRetry ? (
        <MiniButton label="重试" onClick={() => onRetry(message)}>
          <RotateCcw size={14} />
        </MiniButton>
      ) : null}
      {canEdit ? (
        <MiniButton label="编辑" onClick={() => onEdit(message)}>
          <Pencil size={14} />
        </MiniButton>
      ) : null}
      {canDelete ? (
        <MiniButton label="更多" onClick={onToggleMore}>
          <MoreHorizontal size={15} />
        </MiniButton>
      ) : null}
      {moreOpen && canDelete ? (
        <div className="absolute right-0 top-full z-20 mt-2 w-32 overflow-hidden rounded-lg border border-slate-200 bg-white p-1 shadow-xl shadow-slate-200/80 dark:border-slate-700 dark:bg-slate-950 dark:shadow-black/40">
          <button
            type="button"
            onClick={() => onDelete(message)}
            disabled={!canDelete}
            className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm font-bold text-rose-600 transition hover:bg-rose-50 dark:text-rose-300 dark:hover:bg-rose-500/10"
          >
            <Trash2 size={14} />
            删除
          </button>
        </div>
      ) : null}
    </div>
  )
}

function MessageBubble({
  message,
  editing,
  editDraft,
  onEditDraftChange,
  onEditCancel,
  onEditSend,
}: {
  message: SessionTimelineMessage
  editing: boolean
  editDraft: string
  onEditDraftChange: (value: string) => void
  onEditCancel: () => void
  onEditSend: () => void
}) {
  const isUser = message.role === SESSION_TIMELINE_ROLE.USER
  const isAssistant = message.role === SESSION_TIMELINE_ROLE.ASSISTANT
  const isThinking = message.role === SESSION_TIMELINE_ROLE.THINKING
  const toneClass = {
    user: 'border-violet-600 bg-violet-600 text-white shadow-lg shadow-violet-100 dark:shadow-violet-950/30',
    assistant: 'border-slate-200 bg-white text-slate-950 shadow-sm dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 dark:shadow-black/25',
    tool: 'border-sky-200 bg-sky-50 text-sky-800 dark:border-sky-500/30 dark:bg-sky-500/10 dark:text-sky-200',
    system: 'border-slate-200 bg-slate-50 text-slate-600 dark:border-slate-700 dark:bg-slate-800/80 dark:text-slate-300',
    thinking: 'border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-200',
    error: 'border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-200',
  }[message.role]

  if (editing) {
    return (
      <div className="rounded-lg border border-violet-200 bg-white px-3 py-3 shadow-sm dark:border-violet-500/40 dark:bg-slate-900 dark:shadow-black/25">
        <textarea
          value={editDraft}
          onChange={(event) => onEditDraftChange(event.target.value)}
          className="min-h-28 w-full resize-none rounded-lg border border-slate-200 bg-white px-3 py-3 text-[length:var(--session-message-font-size)] leading-[var(--session-message-line-height)] text-slate-900 outline-none transition focus:border-violet-300 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100 dark:focus:border-violet-500"
          autoFocus
        />
        <div className="mt-3 flex justify-end gap-2">
          <button
            type="button"
            onClick={onEditCancel}
            className="h-9 rounded-lg border border-slate-200 bg-white px-3 text-sm font-bold text-slate-600 transition hover:border-violet-200 hover:text-violet-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:border-violet-500/60 dark:hover:text-violet-200"
          >
            取消
          </button>
          <button
            type="button"
            onClick={onEditSend}
            className="h-9 rounded-lg bg-violet-600 px-4 text-sm font-bold text-white shadow-lg shadow-violet-100 transition hover:bg-violet-700 dark:shadow-violet-950/40"
          >
            发送
          </button>
        </div>
      </div>
    )
  }

  const content = message.content || (message.status === SESSION_MESSAGE_STATUS.STREAMING ? '正在生成回应...' : '')

  if (isThinking) {
    return (
      <details
        className={cn(
          'group rounded-lg border px-4 py-3 text-sm leading-6 break-words whitespace-normal',
          toneClass,
        )}
      >
        <summary className="flex cursor-pointer list-none items-center justify-between gap-3 font-black marker:hidden">
          <span>{message.status === SESSION_MESSAGE_STATUS.STREAMING ? '正在思考...' : '思考过程'}</span>
          <ChevronDown size={16} className="shrink-0 transition group-open:rotate-180" />
        </summary>
        <div className="mt-3 whitespace-pre-wrap border-t border-amber-200/70 pt-3 text-xs font-semibold leading-6 text-amber-900 dark:border-amber-500/20 dark:text-amber-100">
          {content || '暂无思考内容'}
        </div>
      </details>
    )
  }

  return (
    <div
      className={cn(
        'rounded-lg border px-5 py-4 text-[length:var(--session-message-font-size)] leading-[var(--session-message-line-height)] break-words whitespace-pre-wrap',
        toneClass,
        isUser ? 'ml-auto w-fit max-w-full text-left font-semibold' : '',
      )}
    >
      {isAssistant && message.content ? <AssistantTaggedText content={message.content} /> : content}
      {isAssistant && message.usage ? <AssistantUsageLine usage={message.usage} /> : null}
    </div>
  )
}

function AssistantTaggedText({ content }: { content: string }) {
  const result = parseAssistantTextSegments(content)
  if (!result.structured) return <>{content}</>

  return (
    <div className="space-y-3 whitespace-normal">
      {result.segments.map((segment, index) => (
        <AssistantSegment key={`${segment.kind}-${index}`} segment={segment} />
      ))}
    </div>
  )
}

function AssistantSegment({ segment }: { segment: AssistantTextSegment }) {
  if (segment.kind === ASSISTANT_TEXT_SEGMENT_KIND.NARRATION) {
    return (
      <section className="space-y-1.5">
        <div className="text-[length:var(--session-segment-label-font-size)] font-bold text-slate-400 dark:text-slate-500">叙事者</div>
        <div className="whitespace-pre-wrap text-slate-800 dark:text-slate-100">{segment.text}</div>
      </section>
    )
  }

  if (segment.kind === ASSISTANT_TEXT_SEGMENT_KIND.CHARACTER) {
    return (
      <section className="space-y-1.5 border-l-2 border-violet-300 pl-3 dark:border-violet-500/70">
        <div className="text-[length:var(--session-segment-label-font-size)] font-bold text-violet-600 dark:text-violet-300">{segment.speakerName}</div>
        <div className="whitespace-pre-wrap text-slate-950 dark:text-slate-50">{segment.text}</div>
      </section>
    )
  }

  return <span className="whitespace-pre-wrap">{segment.text}</span>
}

function TimelineMessage({
  message,
  isEditing,
  editDraft,
  moreOpen,
  onToggleMore,
  onCopy,
  onRetry,
  onEdit,
  onDelete,
  onEditDraftChange,
  onEditCancel,
  onEditSend,
}: {
  message: SessionTimelineMessage
  isEditing: boolean
  editDraft: string
  moreOpen: boolean
  onToggleMore: () => void
  onCopy: (message: SessionTimelineMessage) => void
  onRetry: (message: SessionTimelineMessage) => void
  onEdit: (message: SessionTimelineMessage) => void
  onDelete: (message: SessionTimelineMessage) => void
  onEditDraftChange: (value: string) => void
  onEditCancel: () => void
  onEditSend: () => void
}) {
  const isUser = message.role === SESSION_TIMELINE_ROLE.USER

  return (
    <article
      className={cn(
        'grid items-start gap-3',
        isUser
          ? 'ml-auto max-w-[620px] grid-cols-[minmax(0,1fr)_44px]'
          : 'max-w-[780px] grid-cols-[44px_minmax(0,1fr)]',
      )}
      data-turn-index={message.turnId}
    >
      {!isUser ? <SessionAvatar speaker={message.speaker} /> : null}
      <div className={cn('min-w-0', isUser ? 'text-right' : '')}>
        <div className={cn('mb-2 flex flex-wrap items-center gap-2 text-xs font-semibold text-slate-400 dark:text-slate-400', isUser ? 'justify-end' : '')}>
          <span>{formatMessageTime(message.createdAt)}</span>
          <strong className="text-slate-600 dark:text-slate-300">
            {message.speaker.name}
            {message.speaker.label ? `（${message.speaker.label}）` : ''}
          </strong>
          {message.status ? (
            <span
              className={cn(
                'rounded-full px-2 py-0.5 text-[11px] font-black',
                message.status === SESSION_MESSAGE_STATUS.STREAMING ? 'bg-amber-50 text-amber-700 dark:bg-amber-500/15 dark:text-amber-200' : '',
                message.status === SESSION_MESSAGE_STATUS.DONE ? 'bg-teal-50 text-teal-700 dark:bg-teal-500/15 dark:text-teal-200' : '',
                message.status === SESSION_MESSAGE_STATUS.LOCAL ? 'bg-violet-50 text-violet-700 dark:bg-violet-500/15 dark:text-violet-200' : '',
                message.status === SESSION_MESSAGE_STATUS.ERROR ? 'bg-rose-50 text-rose-700 dark:bg-rose-500/15 dark:text-rose-200' : '',
              )}
            >
              {message.status}
            </span>
          ) : null}
        </div>
        <MessageBubble
          message={message}
          editing={isEditing}
          editDraft={editDraft}
          onEditDraftChange={onEditDraftChange}
          onEditCancel={onEditCancel}
          onEditSend={onEditSend}
        />
        {!isEditing ? (
          <div className={cn('flex', isUser ? 'justify-end' : 'justify-start')}>
            <MessageActions
              message={message}
              moreOpen={moreOpen}
              onToggleMore={onToggleMore}
              onCopy={onCopy}
              onRetry={onRetry}
              onEdit={onEdit}
              onDelete={onDelete}
            />
          </div>
        ) : null}
      </div>
      {isUser ? <SessionAvatar speaker={message.speaker} /> : null}
    </article>
  )
}

export function SessionTimeline({
  sessionId,
  messages,
  showThinking,
  showTools,
  historyPage,
  loadingBefore,
  loadingAfter,
  showJumpToLatest,
  jumpingToLatest,
  onTopBoundaryVisible,
  onBottomBoundaryVisible,
  onJumpToLatest,
  forceScrollKey,
  editingMessageId,
  editDraft,
  onEditDraftChange,
  onCopy,
  onRetry,
  onEdit,
  onDelete,
  onEditCancel,
  onEditSend,
}: {
  sessionId: string
  messages: SessionTimelineMessage[]
  showThinking: boolean
  showTools: boolean
  historyPage: HistoryPage | null
  loadingBefore: boolean
  loadingAfter: boolean
  showJumpToLatest: boolean
  jumpingToLatest: boolean
  onTopBoundaryVisible: () => void | Promise<unknown>
  onBottomBoundaryVisible: () => void | Promise<unknown>
  onJumpToLatest: () => void | Promise<unknown>
  forceScrollKey: number
  editingMessageId: string | null
  editDraft: string
  onEditDraftChange: (value: string) => void
  onCopy: (message: SessionTimelineMessage) => void
  onRetry: (message: SessionTimelineMessage) => void
  onEdit: (message: SessionTimelineMessage) => void
  onDelete: (message: SessionTimelineMessage) => void
  onEditCancel: () => void
  onEditSend: (message: SessionTimelineMessage) => void
}) {
  const [openMoreId, setOpenMoreId] = useState<string | null>(null)
  const scrollContainerRef = useRef<HTMLDivElement | null>(null)
  const topBoundaryRef = useRef<HTMLDivElement | null>(null)
  const bottomBoundaryRef = useRef<HTMLDivElement | null>(null)
  const bottomAnchorRef = useRef<HTMLDivElement | null>(null)
  const shouldStickToBottomRef = useRef(true)
  const initialScrollDoneRef = useRef(false)
  const previousPageRef = useRef<HistoryPage | null>(null)
  const boundaryInFlightRef = useRef<HistoryLoadDirection | null>(null)
  const boundaryCooldownRef = useRef(false)
  const boundaryCooldownTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const programmaticScrollRef = useRef(false)
  const programmaticScrollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const lastScrollTopRef = useRef(0)
  const userScrollDirectionRef = useRef<UserScrollDirection | null>(null)
  const displayMessages = useMemo(
    () => messages.filter((message) => {
      if (!showThinking && message.role === SESSION_TIMELINE_ROLE.THINKING) return false
      if (!showTools && message.role === SESSION_TIMELINE_ROLE.TOOL) return false
      return true
    }),
    [messages, showThinking, showTools],
  )
  const lastMessageFingerprint = useMemo(() => {
    const lastMessage = displayMessages[displayMessages.length - 1]
    const usageStamp = lastMessage?.usage
      ? `${lastMessage.usage.source}:${lastMessage.usage.totalTokens ?? ''}:${lastMessage.usage.promptTokens ?? ''}`
      : ''
    return lastMessage ? `${lastMessage.id}:${lastMessage.content.length}:${lastMessage.status ?? ''}:${usageStamp}` : ''
  }, [displayMessages])
  const pageFingerprint = historyPage
    ? `${historyPage.startTurnId ?? 'empty'}:${historyPage.endTurnId ?? 'empty'}:${historyPage.latestTurnId}`
    : 'empty'

  const markProgrammaticScroll = useCallback(() => {
    programmaticScrollRef.current = true
    userScrollDirectionRef.current = null
    if (programmaticScrollTimerRef.current) clearTimeout(programmaticScrollTimerRef.current)
    programmaticScrollTimerRef.current = setTimeout(() => {
      programmaticScrollRef.current = false
      programmaticScrollTimerRef.current = null
      const container = scrollContainerRef.current
      if (container) lastScrollTopRef.current = container.scrollTop
    }, TIMELINE_SCROLL.programmaticGuardMs)
  }, [])

  const scrollToBottom = useCallback((behavior: ScrollBehavior) => {
    markProgrammaticScroll()
    requestAnimationFrame(() => {
      bottomAnchorRef.current?.scrollIntoView({ behavior, block: 'end' })
    })
  }, [markProgrammaticScroll])

  const scrollToTop = useCallback((behavior: ScrollBehavior) => {
    markProgrammaticScroll()
    requestAnimationFrame(() => {
      scrollContainerRef.current?.scrollTo({ top: 0, behavior })
    })
  }, [markProgrammaticScroll])

  const startBoundaryCooldown = useCallback(() => {
    boundaryCooldownRef.current = true
    if (boundaryCooldownTimerRef.current) clearTimeout(boundaryCooldownTimerRef.current)
    boundaryCooldownTimerRef.current = setTimeout(() => {
      boundaryCooldownRef.current = false
      boundaryCooldownTimerRef.current = null
    }, TIMELINE_SCROLL.boundaryCooldownMs)
  }, [])

  const hasScrollableOverflow = useCallback(() => {
    const container = scrollContainerRef.current
    if (!container) return false
    return container.scrollHeight > container.clientHeight + TIMELINE_SCROLL.overflowTolerancePx
  }, [])

  const triggerBoundaryLoad = useCallback((direction: HistoryLoadDirection, source: BoundaryLoadSource = BOUNDARY_LOAD_SOURCE.AUTO) => {
    if (boundaryCooldownRef.current || boundaryInFlightRef.current) return
    if (source === BOUNDARY_LOAD_SOURCE.AUTO) {
      if (!hasScrollableOverflow()) return
      if (
        direction === HISTORY_LOAD_DIRECTION.BEFORE
        && userScrollDirectionRef.current !== USER_SCROLL_DIRECTION.UP
      ) return
      if (
        direction === HISTORY_LOAD_DIRECTION.AFTER
        && userScrollDirectionRef.current !== USER_SCROLL_DIRECTION.DOWN
      ) return
    }
    const action = direction === HISTORY_LOAD_DIRECTION.BEFORE ? onTopBoundaryVisible : onBottomBoundaryVisible
    boundaryInFlightRef.current = direction
    Promise.resolve(action()).finally(() => {
      boundaryInFlightRef.current = null
      userScrollDirectionRef.current = null
      startBoundaryCooldown()
    })
  }, [hasScrollableOverflow, onBottomBoundaryVisible, onTopBoundaryVisible, startBoundaryCooldown])

  const updateStickToBottom = useCallback(() => {
    const container = scrollContainerRef.current
    if (!container) return
    const nextScrollTop = container.scrollTop
    const scrollDelta = nextScrollTop - lastScrollTopRef.current
    if (!programmaticScrollRef.current && Math.abs(scrollDelta) > TIMELINE_SCROLL.userScrollDeltaThresholdPx) {
      userScrollDirectionRef.current = scrollDelta < 0 ? USER_SCROLL_DIRECTION.UP : USER_SCROLL_DIRECTION.DOWN
    }
    lastScrollTopRef.current = nextScrollTop
    const distanceFromBottom = container.scrollHeight - container.scrollTop - container.clientHeight
    shouldStickToBottomRef.current = distanceFromBottom < TIMELINE_SCROLL.stickToBottomDistancePx
  }, [])

  useEffect(() => {
    initialScrollDoneRef.current = false
    shouldStickToBottomRef.current = true
    previousPageRef.current = null
    boundaryInFlightRef.current = null
    boundaryCooldownRef.current = false
    programmaticScrollRef.current = false
    lastScrollTopRef.current = 0
    userScrollDirectionRef.current = null
    if (boundaryCooldownTimerRef.current) {
      clearTimeout(boundaryCooldownTimerRef.current)
      boundaryCooldownTimerRef.current = null
    }
    if (programmaticScrollTimerRef.current) {
      clearTimeout(programmaticScrollTimerRef.current)
      programmaticScrollTimerRef.current = null
    }
  }, [sessionId])

  useEffect(() => {
    return () => {
      if (boundaryCooldownTimerRef.current) clearTimeout(boundaryCooldownTimerRef.current)
      if (programmaticScrollTimerRef.current) clearTimeout(programmaticScrollTimerRef.current)
    }
  }, [])

  useEffect(() => {
    if (!displayMessages.length) {
      initialScrollDoneRef.current = false
      shouldStickToBottomRef.current = true
      return
    }

    if (!initialScrollDoneRef.current) {
      scrollToBottom('auto')
      initialScrollDoneRef.current = true
      return
    }

    if (shouldStickToBottomRef.current) scrollToBottom('smooth')
  }, [displayMessages.length, lastMessageFingerprint, scrollToBottom])

  useEffect(() => {
    const previousPage = previousPageRef.current
    previousPageRef.current = historyPage
    if (!previousPage || !historyPage) return

    const movedBefore = (
      historyPage.endTurnId !== null
      && previousPage.startTurnId !== null
      && historyPage.endTurnId < previousPage.startTurnId
    )
    const movedAfter = (
      historyPage.startTurnId !== null
      && previousPage.endTurnId !== null
      && historyPage.startTurnId > previousPage.endTurnId
    )

    if (movedBefore) {
      startBoundaryCooldown()
      shouldStickToBottomRef.current = true
      scrollToBottom('auto')
      return
    }

    if (movedAfter) {
      startBoundaryCooldown()
      shouldStickToBottomRef.current = false
      scrollToTop('auto')
    }
  }, [historyPage, pageFingerprint, scrollToBottom, scrollToTop, startBoundaryCooldown])

  useEffect(() => {
    if (!forceScrollKey) return
    shouldStickToBottomRef.current = true
    scrollToBottom('smooth')
  }, [forceScrollKey, scrollToBottom])

  useEffect(() => {
    const container = scrollContainerRef.current
    if (!container) return
    if (!hasScrollableOverflow()) return

    const observer = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue
        if (entry.target === topBoundaryRef.current && historyPage?.hasBefore && !loadingBefore) {
          triggerBoundaryLoad(HISTORY_LOAD_DIRECTION.BEFORE, BOUNDARY_LOAD_SOURCE.AUTO)
        }
        if (entry.target === bottomBoundaryRef.current && historyPage?.hasAfter && !loadingAfter) {
          triggerBoundaryLoad(HISTORY_LOAD_DIRECTION.AFTER, BOUNDARY_LOAD_SOURCE.AUTO)
        }
      }
    }, { root: container, threshold: 0.1 })

    if (historyPage?.hasBefore && topBoundaryRef.current) observer.observe(topBoundaryRef.current)
    if (historyPage?.hasAfter && bottomBoundaryRef.current) observer.observe(bottomBoundaryRef.current)

    return () => observer.disconnect()
  }, [
    historyPage?.hasAfter,
    historyPage?.hasBefore,
    loadingAfter,
    loadingBefore,
    pageFingerprint,
    hasScrollableOverflow,
    triggerBoundaryLoad,
  ])

  return (
    <section className="relative min-h-0 flex-1 bg-[#f7f8fc] dark:bg-[#0b1020]">
      <div
        ref={scrollContainerRef}
        onScroll={updateStickToBottom}
        className="h-full overflow-y-auto px-4 py-7 sm:px-6"
      >
        <div className="mx-auto max-w-5xl">
          <div className="mb-7 flex items-center justify-center gap-4 text-xs font-bold uppercase text-slate-400 dark:text-slate-300">
            <span className="h-px w-24 bg-slate-200 dark:bg-slate-700 sm:w-44" />
            时间线 / Timeline
            <span className="h-px w-24 bg-slate-200 dark:bg-slate-700 sm:w-44" />
          </div>

          {historyPage?.hasBefore || loadingBefore ? (
            <div
              ref={topBoundaryRef}
              className="mb-5 flex min-h-8 items-center justify-center text-xs font-bold text-slate-400 dark:text-slate-400"
            >
              {loadingBefore ? (
                '加载更早记录...'
              ) : (
                <button
                  type="button"
                  onClick={() => triggerBoundaryLoad(HISTORY_LOAD_DIRECTION.BEFORE, BOUNDARY_LOAD_SOURCE.MANUAL)}
                  className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-black text-slate-500 shadow-sm transition hover:border-violet-200 hover:bg-violet-50 hover:text-violet-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:border-violet-500/60 dark:hover:bg-violet-500/10 dark:hover:text-violet-200"
                >
                  加载更早记录
                </button>
              )}
            </div>
          ) : null}

          {displayMessages.length ? (
            <div className="space-y-7">
              {displayMessages.map((message) => (
                <TimelineMessage
                  key={message.id}
                  message={message}
                  isEditing={editingMessageId === message.id}
                  editDraft={editDraft}
                  moreOpen={openMoreId === message.id}
                  onToggleMore={() => setOpenMoreId((current) => (current === message.id ? null : message.id))}
                  onCopy={onCopy}
                  onRetry={onRetry}
                  onEdit={onEdit}
                  onDelete={(item) => {
                    setOpenMoreId(null)
                    onDelete(item)
                  }}
                  onEditDraftChange={onEditDraftChange}
                  onEditCancel={onEditCancel}
                  onEditSend={() => onEditSend(message)}
                />
              ))}
            </div>
          ) : (
            <div className="rounded-lg border border-dashed border-slate-200 bg-white px-6 py-12 text-center dark:border-slate-700 dark:bg-slate-900/80">
              <h2 className="text-base font-black text-slate-950 dark:text-slate-100">暂无回合记录</h2>
              <p className="mt-2 text-sm font-semibold text-slate-400 dark:text-slate-300">发送第一条行动后，故事会从这里展开。</p>
            </div>
          )}

          {historyPage?.hasAfter || loadingAfter ? (
            <div
              ref={bottomBoundaryRef}
              className="mt-5 flex min-h-8 items-center justify-center text-xs font-bold text-slate-400 dark:text-slate-400"
            >
              {loadingAfter ? (
                '加载更新记录...'
              ) : (
                <button
                  type="button"
                  onClick={() => triggerBoundaryLoad(HISTORY_LOAD_DIRECTION.AFTER, BOUNDARY_LOAD_SOURCE.MANUAL)}
                  className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-black text-slate-500 shadow-sm transition hover:border-violet-200 hover:bg-violet-50 hover:text-violet-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:border-violet-500/60 dark:hover:bg-violet-500/10 dark:hover:text-violet-200"
                >
                  加载更新记录
                </button>
              )}
            </div>
          ) : null}
          <div ref={bottomAnchorRef} aria-hidden="true" className="h-px" />
        </div>
      </div>
      {showJumpToLatest ? (
        <div className="pointer-events-none absolute inset-x-0 bottom-5 z-20 flex justify-center px-4">
          <button
            type="button"
            aria-label="返回最新记录"
            title="返回最新记录"
            disabled={jumpingToLatest}
            onClick={() => {
              void onJumpToLatest()
            }}
            className="pointer-events-auto flex h-11 w-11 items-center justify-center rounded-full border border-violet-200 bg-white text-violet-700 shadow-xl shadow-slate-300/40 transition hover:border-violet-300 hover:bg-violet-50 disabled:cursor-wait disabled:opacity-70 dark:border-violet-500/50 dark:bg-slate-950 dark:text-violet-200 dark:shadow-black/40 dark:hover:border-violet-400 dark:hover:bg-violet-500/10"
          >
            <ChevronDown size={20} className={jumpingToLatest ? 'animate-pulse' : ''} />
          </button>
        </div>
      ) : null}
    </section>
  )
}
