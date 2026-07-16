import { Dispatch, SetStateAction, useCallback, useEffect, useRef, useState } from 'react'
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
  source: SessionStreamSource
  assistantMessageId: string
  turnId: number
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
  onCommittedNarrativeStyle: (styleId: NarrativeStyleId) => void
  onTurnCommitted: (turnId: number) => void
}) {
  const [sending, setSending] = useState(false)
  const [stoppingRequestId, setStoppingRequestId] = useState<string | null>(null)
  const activeStreamRef = useRef<ActiveStream | null>(null)
  const stoppingRequestIdRef = useRef<string | null>(null)
  const stopSettledRequestIdsRef = useRef<Set<string>>(new Set())
  const nextTimelineGroupOrderRef = useRef(0)

  useEffect(() => {
    setStoppingRequestId(null)
    stoppingRequestIdRef.current = null
    stopSettledRequestIdsRef.current.clear()
  }, [sessionId])

  useEffect(() => {
    return () => {
      const active = activeStreamRef.current
      if (!active) return
      logger.info('stream cleanup stop requested', {
        requestId: active.requestId,
        source: active.source,
        turnId: active.turnId,
      })
      active.controller.abort()
      activeStreamRef.current = null
      void stopSessionStream(sessionId, active.requestId).catch((error) => {
        logger.warn('stream cleanup stop failed', {
          requestId: active.requestId,
          source: active.source,
          turnId: active.turnId,
          error,
        })
      })
    }
  }, [logger, sessionId])

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
    const controller = new AbortController()
    const requestId = crypto.randomUUID()
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
      source,
      assistantMessageId: assistantMessage.id,
      turnId,
    }
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
              onCommittedNarrativeStyle(narrativeStyleId)
              onTurnCommitted(event.payload.committedTurnId)
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
      if (stoppingRequestIdRef.current === requestId || stopSettledRequestIdsRef.current.has(requestId)) return
      if (streamFailure) throw new Error(streamFailure)
      const refreshed = await refreshSessionData({
        silent: true,
        clearLastTurnUsage: clearCommandInput,
        preserveDiagnostics: !clearCommandInput,
        preserveCommandMessages: commandInput && !clearCommandInput,
        historyMode: clearCommandInput
          ? HISTORY_REFRESH_MODE.LATEST
          : HISTORY_REFRESH_MODE.ACTIVE,
        scrollToBottom: clearCommandInput,
      })
      logger.info('stream refresh after completion', {
        requestId,
        source,
        turnId,
        status: refreshed ? 'success' : 'error',
      })
      showToast(refreshed ? successToast : `${successToast}，但刷新失败，请手动刷新页面`)
    } catch (error) {
      if (controller.signal.aborted) {
        markStreamStopped(assistantMessage.id, turnId)
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
      setSending(false)
      if (activeStreamRef.current?.requestId === requestId) activeStreamRef.current = null
      stopSettledRequestIdsRef.current.delete(requestId)
    }
  }, [
    appendLocalStreamError,
    appendStreamEvent,
    contextPreviewUsage,
    logger,
    markStreamStopped,
    onCommittedNarrativeStyle,
    onTurnCommitted,
    refreshContextPreview,
    refreshSessionData,
    sessionId,
    setLastTurnUsage,
    setLocalTurnUsageByTurn,
    setComposerText,
    setForceScrollKey,
    setLocalMessages,
    showToast,
  ])

  const stopActiveStream = useCallback(async ({ silent = false }: { silent?: boolean } = {}) => {
    const active = activeStreamRef.current
    if (!active) return false

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
      const result = await stopSessionStream(sessionId, active.requestId)
      logger.info('stream stop result received', {
        requestId: active.requestId,
        source: active.source,
        turnId: active.turnId,
        status: result.status,
        resultRequestId: result.requestId,
      })
      if (result.status === TURN_CANCEL_STATUS.CANCELLED) {
        stopSettledRequestIdsRef.current.add(active.requestId)
        if (activeStreamRef.current?.requestId === active.requestId) activeStreamRef.current = null
        active.controller.abort()
        markStreamStopped(active.assistantMessageId, active.turnId)
        if (!silent) showToast('已停止当前流式响应')
        return true
      }
      if (result.status === TURN_CANCEL_STATUS.NOT_RUNNING) {
        stopSettledRequestIdsRef.current.add(active.requestId)
        await refreshSessionData({ silent: true })
        if (!silent) showToast('生成已结束，已刷新状态')
        return false
      }
      if (!silent) showToast('当前生成状态已变化，未停止')
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
        if (!silent) showToast('停止失败，生成仍在继续')
      } else {
        await refreshSessionData({ silent: true })
        if (!silent) showToast('停止失败，已刷新状态')
      }
      return false
    } finally {
      if (stoppingRequestIdRef.current === active.requestId) {
        stoppingRequestIdRef.current = null
        setStoppingRequestId((current) => (current === active.requestId ? null : current))
      }
    }
  }, [logger, markStreamStopped, refreshSessionData, sessionId, showToast])

  const handleExitSession = useCallback(() => {
    const active = activeStreamRef.current
    if (active) {
      logger.info('stream exit stop requested', {
        requestId: active.requestId,
        source: active.source,
        turnId: active.turnId,
      })
      activeStreamRef.current = null
      stoppingRequestIdRef.current = null
      setStoppingRequestId(null)
      active.controller.abort()
      void stopSessionStream(sessionId, active.requestId).catch((error) => {
        logger.warn('stream exit stop failed', {
          requestId: active.requestId,
          source: active.source,
          turnId: active.turnId,
          error,
        })
      })
    }
    onExit()
  }, [logger, onExit, sessionId])

  const prepareForSessionDeletion = useCallback(() => {
    const active = activeStreamRef.current
    if (!active) return
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

  return {
    sending,
    stopping: Boolean(stoppingRequestId),
    streamLocalTurn,
    stopActiveStream,
    handleExitSession,
    prepareForSessionDeletion,
  }
}
