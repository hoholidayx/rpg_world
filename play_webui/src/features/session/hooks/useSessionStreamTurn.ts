import { Dispatch, SetStateAction, useCallback, useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { stopSessionStream } from '@/lib/api/chat'
import { formatStreamErrorText } from '@/lib/stream/formatStreamError'
import { consumeChatStream } from '@/lib/stream/sse'
import { fromTurnUsage, type ContextUsageSnapshot } from '@/types/contextUsage'
import { TURN_CANCEL_STATUS } from '@/types/command'
import { PLAY_STREAM_EVENT_TYPE, type PlayStreamEvent } from '@/types/stream'
import type { SessionRoomLogger } from '../sessionRoomLogger'
import {
  isSlashCommandInput,
  MAIN_CONTEXT_WINDOW_THRESHOLD_EXCEEDED_ERROR_CODE,
} from '../contextWindowGate'
import {
  commandSpeaker,
  errorSpeaker,
  stoppedStreamText,
  thinkingSpeaker,
  toolSpeaker,
  outcomeSpeaker,
  parseNarrativeOutcomeToolResult,
} from '../sessionTimelineMessages'
import {
  HISTORY_REFRESH_MODE,
  SESSION_MESSAGE_STATUS,
  SESSION_TIMELINE_ROLE,
  type RefreshSessionDataOptions,
  type SessionInputMode,
  type NarrativeStyleId,
  type SessionStreamSource,
  type SessionTimelineMessage,
} from '../sessionRoomTypes'

type ActiveStream = {
  controller: AbortController
  requestId: string
  sessionId: string
  source: SessionStreamSource
  assistantMessageId: string
  turnId: number
}

type StreamRefreshRecovery = {
  sessionId: string
  options: RefreshSessionDataOptions
}

export type StreamLocalTurnOptions = {
  text: string
  turnId: number
  timelineAnchorTurnId: number
  userMessage: SessionTimelineMessage
  assistantMessage: SessionTimelineMessage
  source: SessionStreamSource
  mode: SessionInputMode
  narrativeStyleId: NarrativeStyleId
  pendingToast?: string
  successToast: string
  failureToast: string
  clearComposer?: boolean
}

export function useSessionStreamTurn({
  sessionId,
  contextPreviewUsage,
  setLastTurnUsage,
  setLocalTurnUsageByTurn,
  setComposerText,
  setLocalMessages,
  setForceScrollKey,
  refreshSessionData,
  refreshContextPreview,
  showToast,
  logger,
  onExit,
  onActiveSession,
  onCommittedNarrativeStyle,
  onTurnCommitted,
}: {
  sessionId: string
  contextPreviewUsage: ContextUsageSnapshot | null
  setLastTurnUsage: Dispatch<SetStateAction<ContextUsageSnapshot | null>>
  setLocalTurnUsageByTurn: Dispatch<SetStateAction<Record<number, ContextUsageSnapshot>>>
  setComposerText: Dispatch<SetStateAction<string>>
  setLocalMessages: Dispatch<SetStateAction<SessionTimelineMessage[]>>
  setForceScrollKey: Dispatch<SetStateAction<number>>
  refreshSessionData: (options?: RefreshSessionDataOptions) => Promise<boolean>
  refreshContextPreview: () => Promise<{
    available: boolean
    usage: ContextUsageSnapshot | null
  }>
  showToast: (message: string) => void
  logger: SessionRoomLogger
  onExit: () => void
  onActiveSession: (sessionId: string) => void
  onCommittedNarrativeStyle: (styleId: NarrativeStyleId) => void
  onTurnCommitted: (turnId: number) => void
}) {
  const queryClient = useQueryClient()
  const [sending, setSending] = useState(false)
  const [stoppingRequestId, setStoppingRequestId] = useState<string | null>(null)
  const [refreshRecovery, setRefreshRecovery] = useState<StreamRefreshRecovery | null>(null)
  const [refreshRetrying, setRefreshRetrying] = useState(false)
  const activeStreamRef = useRef<ActiveStream | null>(null)
  const sendingRequestIdRef = useRef<string | null>(null)
  const refreshRetryTokenRef = useRef<symbol | null>(null)
  const sessionIdRef = useRef(sessionId)
  const mountedRef = useRef(true)
  const stoppingRequestIdRef = useRef<string | null>(null)
  const stopSettledRequestIdsRef = useRef<Set<string>>(new Set())
  const nextTimelineGroupOrderRef = useRef(0)
  sessionIdRef.current = sessionId

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
    }
  }, [])

  useEffect(() => {
    sendingRequestIdRef.current = null
    refreshRetryTokenRef.current = null
    setSending(false)
    setRefreshRecovery(null)
    setRefreshRetrying(false)
    setStoppingRequestId(null)
    stoppingRequestIdRef.current = null
    stopSettledRequestIdsRef.current.clear()
  }, [sessionId])

  useEffect(() => {
    const effectSessionId = sessionId
    return () => {
      const active = activeStreamRef.current
      if (!active || active.sessionId !== effectSessionId) return
      logger.info('stream cleanup stop requested', {
        requestId: active.requestId,
        source: active.source,
        turnId: active.turnId,
      })
      queryClient.removeQueries({
        queryKey: ['play-session-dream-evidence-history', active.sessionId],
        exact: true,
      })
      activeStreamRef.current = null
      active.controller.abort()
      void stopSessionStream(active.sessionId, active.requestId).catch((error) => {
        logger.warn('stream cleanup stop failed', {
          requestId: active.requestId,
          sessionId: active.sessionId,
          source: active.source,
          turnId: active.turnId,
          error,
        })
      })
    }
  }, [logger, queryClient, sessionId])

  const markStreamStopped = useCallback((assistantMessageId: string, turnId: number) => {
    setLocalMessages((current) =>
      current.filter((message) => !(
        message.turnId === turnId && message.role === SESSION_TIMELINE_ROLE.OUTCOME
      )).map((message) =>
        message.id === assistantMessageId
          ? {
              ...message,
              status: SESSION_MESSAGE_STATUS.DONE,
              content: message.content || stoppedStreamText,
              canCopy: Boolean((message.content || stoppedStreamText).trim()),
            }
          : message.turnId === turnId && message.role === SESSION_TIMELINE_ROLE.USER
            ? {
                ...message,
                canRetry: true,
                canEdit: true,
              }
          : message,
      ),
    )
  }, [setLocalMessages])

  const appendLocalStreamError = useCallback((
    assistantMessageId: string,
    turnId: number,
    errorText: string,
    requestId: string,
    timelineAnchorTurnId: number,
    timelineGroupOrder: number,
  ) => {
    setLocalMessages((current) => [
      ...current.filter((message) => !(
        message.turnId === turnId && message.role === SESSION_TIMELINE_ROLE.OUTCOME
      )).map((message) =>
        message.id === assistantMessageId ? { ...message, status: SESSION_MESSAGE_STATUS.ERROR } : message,
      ),
      {
        id: `local-error-${turnId}-${crypto.randomUUID()}`,
        turnId,
        timelineGroupId: `stream:${requestId}`,
        timelineAnchorTurnId,
        timelineGroupOrder,
        seqInTurn: 5,
        role: SESSION_TIMELINE_ROLE.ERROR,
        content: errorText,
        metadata: { streamRequestId: requestId },
        createdAt: new Date().toISOString(),
        speaker: errorSpeaker(),
        status: SESSION_MESSAGE_STATUS.ERROR,
        canCopy: Boolean(errorText.trim()),
        canRetry: false,
        canEdit: false,
        canDelete: false,
      },
    ])
  }, [setLocalMessages])

  const appendStreamEvent = useCallback((
    event: PlayStreamEvent,
    assistantMessageId: string,
    turnId: number,
    requestId: string,
    timelineAnchorTurnId: number,
    timelineGroupOrder: number,
    usageFallback: ContextUsageSnapshot | null,
    isCommand: boolean,
  ) => {
    if (event.type === PLAY_STREAM_EVENT_TYPE.TURN_STARTED) return

    if (event.type === PLAY_STREAM_EVENT_TYPE.THINKING_DELTA) {
      setLocalMessages((current) => {
        const existingThinking = current.find((message) =>
          message.turnId === turnId
          && message.role === SESSION_TIMELINE_ROLE.THINKING
          && message.metadata?.streamKind === 'thinking',
        )
        if (existingThinking) {
          return current.map((message) =>
            message.id === existingThinking.id
              ? {
                  ...message,
                  content: `${message.content}${event.payload.text}`,
                  status: SESSION_MESSAGE_STATUS.STREAMING,
                  canCopy: Boolean(`${message.content}${event.payload.text}`.trim()),
                }
              : message,
          )
        }

        return [
          ...current,
          {
            id: `local-thinking-${turnId}-${crypto.randomUUID()}`,
            turnId,
            timelineGroupId: `stream:${requestId}`,
            timelineAnchorTurnId,
            timelineGroupOrder,
            timelineItemOrder: event.eventId,
            seqInTurn: 3,
            role: SESSION_TIMELINE_ROLE.THINKING,
            content: event.payload.text,
            metadata: { streamKind: 'thinking', streamRequestId: requestId },
            createdAt: new Date().toISOString(),
            speaker: thinkingSpeaker(),
            status: SESSION_MESSAGE_STATUS.STREAMING,
            canCopy: Boolean(event.payload.text.trim()),
            canRetry: false,
            canEdit: false,
            canDelete: false,
          },
        ]
      })
      return
    }

    if (event.type === PLAY_STREAM_EVENT_TYPE.TEXT_DELTA) {
      setLocalMessages((current) =>
        current.map((message) =>
          message.id === assistantMessageId
            ? {
                ...message,
                content: `${message.content}${event.payload.text}`,
                status: SESSION_MESSAGE_STATUS.STREAMING,
                canCopy: Boolean(`${message.content}${event.payload.text}`.trim()),
              }
            : message,
        ),
      )
      return
    }

    if (event.type === PLAY_STREAM_EVENT_TYPE.TOOL_CALL || event.type === PLAY_STREAM_EVENT_TYPE.TOOL_RESULT) {
      if (event.payload.toolName === 'rp_story_outcome') {
        if (event.type === PLAY_STREAM_EVENT_TYPE.TOOL_CALL) return
        const outcome = parseNarrativeOutcomeToolResult(
          event.payload.toolResult ?? event.payload.resultPreview,
        )
        if (!outcome) {
          logger.warn('narrative outcome tool result could not be parsed', { turnId })
          return
        }
        setLocalMessages((current) => [
          ...current.filter((message) => !(
            message.turnId === turnId && message.role === SESSION_TIMELINE_ROLE.OUTCOME
          )),
          {
            id: `local-outcome-${turnId}`,
            turnId,
            timelineGroupId: `stream:${requestId}`,
            timelineAnchorTurnId,
            timelineGroupOrder,
            timelineItemOrder: event.eventId,
            seqInTurn: 2,
            role: SESSION_TIMELINE_ROLE.OUTCOME,
            content: outcome.reason,
            outcome,
            metadata: { toolName: 'rp_story_outcome', streamRequestId: requestId },
            createdAt: new Date().toISOString(),
            speaker: outcomeSpeaker(),
            status: SESSION_MESSAGE_STATUS.LOCAL,
            canCopy: false,
            canRetry: false,
            canEdit: false,
            canDelete: false,
          },
        ])
        return
      }
      const toolText = event.type === PLAY_STREAM_EVENT_TYPE.TOOL_RESULT
        ? event.payload.resultPreview ?? event.payload.toolResult ?? event.payload.toolName ?? '工具事件'
        : event.payload.toolArguments ?? event.payload.toolName ?? '工具事件'
      setLocalMessages((current) => [
        ...current,
        {
          id: `local-tool-${turnId}-${crypto.randomUUID()}`,
          turnId,
          timelineGroupId: `stream:${requestId}`,
          timelineAnchorTurnId,
          timelineGroupOrder,
          timelineItemOrder: event.eventId,
          seqInTurn: 4,
          role: SESSION_TIMELINE_ROLE.TOOL,
          content: toolText,
          metadata: { streamRequestId: requestId },
          createdAt: new Date().toISOString(),
          speaker: toolSpeaker(),
          status: SESSION_MESSAGE_STATUS.LOCAL,
          canCopy: Boolean(toolText.trim()),
          canRetry: false,
          canEdit: false,
          canDelete: false,
        },
      ])
      return
    }

    if (event.type === PLAY_STREAM_EVENT_TYPE.TURN_COMPLETED) {
      const usage = fromTurnUsage(event.payload.usage, usageFallback, {
        model: event.payload.model,
        finishReason: event.payload.finishReason,
        durationMs: event.payload.durationMs,
      })
      logger.info('stream turn completed', {
        turnId,
        status: 'done',
        model: event.payload.model,
        finishReason: event.payload.finishReason,
        durationMs: event.payload.durationMs,
        hasUsage: Boolean(usage),
      })
      if (usage) setLastTurnUsage(usage)
      else if (!isCommand) setLastTurnUsage(null)
      const usageTurnId = event.payload.committedTurnId ?? turnId
      if (usage) {
        setLocalTurnUsageByTurn((current) => ({ ...current, [usageTurnId]: usage }))
      } else {
        setLocalTurnUsageByTurn((current) => {
          const next = { ...current }
          delete next[usageTurnId]
          return next
        })
      }
      setLocalMessages((current) =>
        current.map((message) => {
          const completedMessage = message.id === assistantMessageId
            ? {
                ...message,
                status: SESSION_MESSAGE_STATUS.DONE,
                content: message.content || event.payload.text || '已完成。',
                usage,
                canCopy: Boolean((message.content || event.payload.text || '已完成。').trim()),
              }
            : message.metadata?.streamRequestId === requestId
                && message.role === SESSION_TIMELINE_ROLE.THINKING
              ? { ...message, status: SESSION_MESSAGE_STATUS.DONE }
              : message
          const committedTurnId = event.payload.committedTurnId
          if (
            committedTurnId
            && completedMessage.metadata?.streamRequestId === requestId
          ) {
            return {
              ...completedMessage,
              turnId: committedTurnId,
              timelineGroupId: `turn:${committedTurnId}`,
              timelineAnchorTurnId: committedTurnId,
              timelineGroupOrder: 0,
            }
          }
          return completedMessage
        }),
      )
      return
    }

    if (event.type === PLAY_STREAM_EVENT_TYPE.ERROR) {
      if (event.payload.errorCode === MAIN_CONTEXT_WINDOW_THRESHOLD_EXCEEDED_ERROR_CODE) return
      const errorText = formatStreamErrorText(event.payload)
      logger.warn('stream sse error event', {
        turnId,
        status: 'error',
        transportStatusCode: event.payload.statusCode,
        errorCode: event.payload.errorCode,
      })
      setLocalMessages((current) => [
        ...current.filter((message) => !(
          message.turnId === turnId && message.role === SESSION_TIMELINE_ROLE.OUTCOME
        )).map((message) =>
          message.id === assistantMessageId ? { ...message, status: SESSION_MESSAGE_STATUS.ERROR } : message,
        ),
        {
          id: `local-error-${turnId}-${crypto.randomUUID()}`,
          turnId,
          timelineGroupId: `stream:${requestId}`,
          timelineAnchorTurnId,
          timelineGroupOrder,
          timelineItemOrder: event.eventId,
          seqInTurn: 5,
          role: SESSION_TIMELINE_ROLE.ERROR,
          content: errorText,
          metadata: {
            streamRequestId: requestId,
            errorCode: event.payload.errorCode,
            errorMessage: event.payload.message,
          },
          createdAt: new Date().toISOString(),
          speaker: errorSpeaker(),
          status: SESSION_MESSAGE_STATUS.ERROR,
          canCopy: Boolean(errorText.trim()),
          canRetry: false,
          canEdit: false,
          canDelete: false,
        },
      ])
    }
  }, [logger, setLastTurnUsage, setLocalMessages, setLocalTurnUsageByTurn])

  const streamLocalTurn = useCallback(async ({
    text,
    turnId,
    timelineAnchorTurnId,
    userMessage,
    assistantMessage,
    source,
    mode,
    narrativeStyleId,
    pendingToast,
    successToast,
    failureToast,
    clearComposer = false,
  }: StreamLocalTurnOptions) => {
    if (stoppingRequestIdRef.current) {
      showToast('正在停止当前生成，请稍后再试')
      return
    }
    if (refreshRetryTokenRef.current) {
      logger.warn('stream start ignored while history recovery owns the session view', {
        source,
        turnId,
      })
      showToast('正在刷新历史，请稍后再试')
      return
    }
    if (activeStreamRef.current || sendingRequestIdRef.current) {
      logger.warn('stream start ignored because another request owns the session view', {
        activeRequestId: activeStreamRef.current?.requestId,
        source,
        turnId,
      })
      showToast('当前仍在生成，请稍后再试')
      return
    }

    const controller = new AbortController()
    const requestId = crypto.randomUUID()
    const requestSessionId = sessionId
    const timelineGroupOrder = ++nextTimelineGroupOrderRef.current
    const timelineGroup = {
      timelineGroupId: `stream:${requestId}`,
      timelineAnchorTurnId,
      timelineGroupOrder,
    }
    const turnUsageFallback = contextPreviewUsage
    const commandInput = isSlashCommandInput(text)
    const clearCommandInput = text.trim() === '/clear'
    const displayedUserMessage = commandInput
      ? {
          ...userMessage,
          ...timelineGroup,
          metadata: { ...userMessage.metadata, localCommand: true, streamRequestId: requestId },
          speaker: { ...userMessage.speaker, label: 'CMD' },
        }
      : {
          ...userMessage,
          ...timelineGroup,
          metadata: { ...userMessage.metadata, streamRequestId: requestId },
        }
    const displayedAssistantMessage = commandInput
      ? {
          ...assistantMessage,
          ...timelineGroup,
          metadata: { ...assistantMessage.metadata, localCommand: true, streamRequestId: requestId },
          speaker: commandSpeaker(),
        }
      : {
          ...assistantMessage,
          ...timelineGroup,
          metadata: { ...assistantMessage.metadata, streamRequestId: requestId },
        }
    stoppingRequestIdRef.current = null
    stopSettledRequestIdsRef.current.clear()
    setStoppingRequestId(null)
    activeStreamRef.current = {
      controller,
      requestId,
      sessionId: requestSessionId,
      source,
      assistantMessageId: assistantMessage.id,
      turnId,
    }
    sendingRequestIdRef.current = requestId
    const ownsRequest = () => (
      activeStreamRef.current?.requestId === requestId
      && activeStreamRef.current.sessionId === requestSessionId
      && sessionIdRef.current === requestSessionId
    )
    setLocalTurnUsageByTurn((current) => {
      const next = { ...current }
      delete next[turnId]
      return next
    })
    if (clearComposer) setComposerText('')
    setSending(true)
    setLocalMessages((current) => [
      ...current.filter((message) => message.turnId !== turnId),
      displayedUserMessage,
      displayedAssistantMessage,
    ])
    setForceScrollKey((current) => current + 1)
    logger.info('stream started', {
      requestId,
      source,
      turnId,
      mode,
      narrativeStyleId,
      textLength: text.length,
      hasText: Boolean(text.trim()),
    })
    if (pendingToast) showToast(pendingToast)

    let streamFailure: string | null = null
    let contextThresholdRejected = false
    let contextThresholdMessage = ''
    let activeSession: string | null = null
    let receivedCommittedTurn = false
    let preserveVisibleFallback = false
    try {
      await consumeChatStream(
        {
          sessionId,
          text,
          mode,
          narrativeStyleId,
          requestId,
        },
        {
          signal: controller.signal,
          onEvent: (event) => {
            if (!ownsRequest()) {
              logger.info('stale stream event ignored', {
                requestId,
                requestSessionId,
                currentSessionId: sessionIdRef.current,
                eventId: event.eventId,
                eventType: event.type,
              })
              return
            }
            if (
              event.eventId < 0
              || (
                receivedCommittedTurn
                && event.type === PLAY_STREAM_EVENT_TYPE.TEXT_DELTA
              )
            ) {
              preserveVisibleFallback = true
            }
            appendStreamEvent(
              event,
              assistantMessage.id,
              turnId,
              requestId,
              timelineAnchorTurnId,
              timelineGroupOrder,
              turnUsageFallback,
              commandInput,
            )
            if (
              event.type === PLAY_STREAM_EVENT_TYPE.TURN_COMPLETED
              && event.payload.committedTurnId
              && event.payload.committedTurnId > 0
            ) {
              receivedCommittedTurn = true
              onCommittedNarrativeStyle(narrativeStyleId)
              onTurnCommitted(event.payload.committedTurnId)
            }
            if (
              event.type === PLAY_STREAM_EVENT_TYPE.TURN_COMPLETED
              && event.payload.activeSession
            ) {
              activeSession = event.payload.activeSession
            }
            if (
              event.type === PLAY_STREAM_EVENT_TYPE.ERROR
              && event.payload.errorCode === MAIN_CONTEXT_WINDOW_THRESHOLD_EXCEEDED_ERROR_CODE
            ) {
              contextThresholdRejected = true
              contextThresholdMessage = event.payload.message
            }
            if (event.type === PLAY_STREAM_EVENT_TYPE.ERROR) streamFailure = formatStreamErrorText(event.payload) || failureToast
          },
        },
      )
      if (!ownsRequest()) return
      if (stoppingRequestIdRef.current === requestId || stopSettledRequestIdsRef.current.has(requestId)) return
      if (streamFailure) throw new Error(streamFailure)
      if (activeSession && activeSession !== sessionId) {
        logger.info('session locator changed', {
          requestId,
          sourceSessionId: sessionId,
          activeSession,
        })
        onActiveSession(activeSession)
        return
      }
      queryClient.removeQueries({
        queryKey: ['play-session-dream-evidence-history', sessionId],
        exact: true,
      })
      const refreshOptions: RefreshSessionDataOptions = {
        silent: true,
        clearLastTurnUsage: clearCommandInput,
        preserveDiagnostics: !clearCommandInput,
        preserveCommandMessages: commandInput && !clearCommandInput,
        preserveLocalMessages: !receivedCommittedTurn || preserveVisibleFallback,
        historyMode: clearCommandInput
          ? HISTORY_REFRESH_MODE.LATEST
          : HISTORY_REFRESH_MODE.ACTIVE,
        scrollToBottom: clearCommandInput,
      }
      const refreshed = await refreshSessionData(refreshOptions)
      if (!ownsRequest()) return
      setRefreshRecovery(refreshed
        ? null
        : {
            sessionId: requestSessionId,
            options: refreshOptions,
          })
      if (clearCommandInput) {
        queryClient.removeQueries({ queryKey: ['play-session-dream-proposal', sessionId] })
        queryClient.removeQueries({ queryKey: ['play-session-dream-proposals', sessionId] })
        queryClient.removeQueries({ queryKey: ['play-session-dream-memories', sessionId] })
      }
      logger.info('stream refresh after completion', {
        requestId,
        source,
        turnId,
        status: refreshed ? 'success' : 'error',
      })
      showToast(refreshed ? successToast : `${successToast}，但刷新失败，请手动刷新页面`)
    } catch (error) {
      if (!ownsRequest()) {
        logger.info('stale stream failure ignored', {
          requestId,
          requestSessionId,
          currentSessionId: sessionIdRef.current,
        })
      } else if (controller.signal.aborted) {
        // A local abort can also mean navigation or deletion. Only a confirmed
        // Stop API cancellation may render the player-visible stopped state.
      } else if (contextThresholdRejected) {
        setLocalMessages((current) => current.filter((message) => message.turnId !== turnId))
        if (clearComposer) setComposerText(text)
        await refreshContextPreview()
        const errorText = contextThresholdMessage || (error instanceof Error ? error.message : failureToast)
        logger.warn('stream rejected by context threshold', {
          requestId,
          source,
          turnId,
          status: 'rejected',
        })
        showToast(errorText)
      } else if (stoppingRequestIdRef.current === requestId || stopSettledRequestIdsRef.current.has(requestId)) {
        // Stop API is responsible for deciding whether this stream is actually stopped.
      } else {
        const errorText = error instanceof Error ? error.message : failureToast
        logger.warn('stream failed', {
          requestId,
          source,
          turnId,
          status: 'error',
          error,
        })
        if (!streamFailure) {
          appendLocalStreamError(
            assistantMessage.id,
            turnId,
            errorText,
            requestId,
            timelineAnchorTurnId,
            timelineGroupOrder,
          )
        }
        showToast(errorText)
      }
    } finally {
      if (activeStreamRef.current?.requestId === requestId) activeStreamRef.current = null
      if (sendingRequestIdRef.current === requestId) {
        sendingRequestIdRef.current = null
        setSending(false)
      }
      stopSettledRequestIdsRef.current.delete(requestId)
    }
  }, [
    appendLocalStreamError,
    appendStreamEvent,
    contextPreviewUsage,
    logger,
    onActiveSession,
    onCommittedNarrativeStyle,
    onTurnCommitted,
    queryClient,
    refreshContextPreview,
    refreshSessionData,
    sessionId,
    setLocalTurnUsageByTurn,
    setComposerText,
    setForceScrollKey,
    setLocalMessages,
    showToast,
  ])

  const stopActiveStream = useCallback(async ({ silent = false }: { silent?: boolean } = {}) => {
    const active = activeStreamRef.current
    if (!active) return false
    if (active.sessionId !== sessionIdRef.current) {
      logger.info('stale session stream stop ignored', {
        requestId: active.requestId,
        requestSessionId: active.sessionId,
        currentSessionId: sessionIdRef.current,
      })
      return false
    }

    if (stoppingRequestIdRef.current === active.requestId) {
      logger.info('stream stop duplicate ignored', {
        requestId: active.requestId,
        source: active.source,
        turnId: active.turnId,
      })
      return false
    }
    stoppingRequestIdRef.current = active.requestId
    setStoppingRequestId(active.requestId)
    logger.info('stream stop requested', {
      requestId: active.requestId,
      source: active.source,
      turnId: active.turnId,
    })

    try {
      const result = await stopSessionStream(active.sessionId, active.requestId)
      logger.info('stream stop result received', {
        requestId: active.requestId,
        source: active.source,
        turnId: active.turnId,
        status: result.status,
        resultRequestId: result.requestId,
      })
      if (result.status === TURN_CANCEL_STATUS.CANCELLED) {
        stopSettledRequestIdsRef.current.add(active.requestId)
        const currentActive = activeStreamRef.current
        const ownsCurrentView = (
          mountedRef.current
          && sessionIdRef.current === active.sessionId
          && (!currentActive || currentActive.requestId === active.requestId)
          && (
            !sendingRequestIdRef.current
            || sendingRequestIdRef.current === active.requestId
          )
        )
        if (ownsCurrentView) {
          markStreamStopped(active.assistantMessageId, active.turnId)
          if (!silent) showToast('已停止当前流式响应')
        }
        if (activeStreamRef.current?.requestId === active.requestId) activeStreamRef.current = null
        active.controller.abort()
        return true
      }
      if (result.status === TURN_CANCEL_STATUS.NOT_RUNNING) {
        stopSettledRequestIdsRef.current.add(active.requestId)
        queryClient.removeQueries({
          queryKey: ['play-session-dream-evidence-history', active.sessionId],
          exact: true,
        })
        const refreshOptions: RefreshSessionDataOptions = {
          silent: true,
          preserveLocalMessages: true,
        }
        const refreshed = await refreshSessionData(refreshOptions)
        if (!refreshed && sessionIdRef.current === active.sessionId) {
          setRefreshRecovery({
            sessionId: active.sessionId,
            options: refreshOptions,
          })
        }
        if (!silent && sessionIdRef.current === active.sessionId) {
          showToast(refreshed ? '生成已结束，已刷新状态' : '生成已结束，但历史刷新失败')
        }
        return false
      }
      if (!silent && sessionIdRef.current === active.sessionId) {
        showToast('当前生成状态已变化，未停止')
      }
      return false
    } catch (error) {
      const stillActive = activeStreamRef.current?.requestId === active.requestId
      logger.warn('stream stop failed', {
        requestId: active.requestId,
        source: active.source,
        turnId: active.turnId,
        status: 'error',
        stillActive,
        error,
      })
      if (stillActive) {
        if (!silent && sessionIdRef.current === active.sessionId) {
          showToast('停止失败，生成仍在继续')
        }
      } else {
        queryClient.removeQueries({
          queryKey: ['play-session-dream-evidence-history', active.sessionId],
          exact: true,
        })
        const refreshOptions: RefreshSessionDataOptions = {
          silent: true,
          preserveLocalMessages: true,
        }
        const refreshed = await refreshSessionData(refreshOptions)
        if (!refreshed && sessionIdRef.current === active.sessionId) {
          setRefreshRecovery({
            sessionId: active.sessionId,
            options: refreshOptions,
          })
        }
        if (!silent && sessionIdRef.current === active.sessionId) {
          showToast(refreshed ? '停止失败，已刷新状态' : '停止失败，历史刷新也失败')
        }
      }
      return false
    } finally {
      if (stoppingRequestIdRef.current === active.requestId) {
        stoppingRequestIdRef.current = null
        setStoppingRequestId((current) => (current === active.requestId ? null : current))
      }
    }
  }, [logger, markStreamStopped, queryClient, refreshSessionData, showToast])

  const handleExitSession = useCallback(() => {
    const active = activeStreamRef.current
    if (active?.sessionId === sessionIdRef.current) {
      logger.info('stream exit stop requested', {
        requestId: active.requestId,
        source: active.source,
        turnId: active.turnId,
      })
      activeStreamRef.current = null
      stoppingRequestIdRef.current = null
      setStoppingRequestId(null)
      queryClient.removeQueries({
        queryKey: ['play-session-dream-evidence-history', active.sessionId],
        exact: true,
      })
      active.controller.abort()
      void stopSessionStream(active.sessionId, active.requestId).catch((error) => {
        logger.warn('stream exit stop failed', {
          requestId: active.requestId,
          sessionId: active.sessionId,
          source: active.source,
          turnId: active.turnId,
          error,
        })
      })
    }
    onExit()
  }, [logger, onExit, queryClient])

  const prepareForSessionDeletion = useCallback(() => {
    const active = activeStreamRef.current
    if (!active || active.sessionId !== sessionIdRef.current) return
    logger.info('stream local view cancelled for session deletion', {
      requestId: active.requestId,
      source: active.source,
      turnId: active.turnId,
    })
    activeStreamRef.current = null
    stoppingRequestIdRef.current = null
    setStoppingRequestId(null)
    active.controller.abort()
  }, [logger])

  const retryCompletionRefresh = useCallback(async () => {
    if (
      !refreshRecovery
      || refreshRetryTokenRef.current
      || sendingRequestIdRef.current
      || activeStreamRef.current
      || refreshRecovery.sessionId !== sessionIdRef.current
    ) return false

    const recovery = refreshRecovery
    const retryToken = Symbol('stream-refresh-retry')
    refreshRetryTokenRef.current = retryToken
    setRefreshRetrying(true)
    try {
      const refreshed = await refreshSessionData(recovery.options)
      if (
        refreshRetryTokenRef.current !== retryToken
        || sessionIdRef.current !== recovery.sessionId
      ) return false
      if (refreshed) {
        setRefreshRecovery(null)
        showToast('历史已刷新')
        return true
      }
      showToast('历史刷新仍失败，请稍后重试')
      return false
    } finally {
      if (refreshRetryTokenRef.current === retryToken) {
        refreshRetryTokenRef.current = null
        if (sessionIdRef.current === recovery.sessionId) setRefreshRetrying(false)
      }
    }
  }, [refreshRecovery, refreshSessionData, showToast])

  return {
    sending,
    stopping: Boolean(stoppingRequestId),
    refreshRecoveryPending: Boolean(refreshRecovery?.sessionId === sessionId),
    refreshRetrying,
    streamLocalTurn,
    stopActiveStream,
    retryCompletionRefresh,
    handleExitSession,
    prepareForSessionDeletion,
  }
}
