import { Dispatch, SetStateAction, useCallback, useEffect, useRef, useState } from 'react'
import { stopSessionStream } from '@/lib/api/chat'
import { consumeChatStream } from '@/lib/stream/sse'
import { fromTurnUsage, type ContextUsageSnapshot } from '@/types/contextUsage'
import { TURN_CANCEL_STATUS } from '@/types/command'
import { PLAY_STREAM_EVENT_TYPE, type PlayStreamEvent } from '@/types/stream'
import type { SessionRoomLogger } from '../sessionRoomLogger'
import {
  errorSpeaker,
  stoppedStreamText,
  toolSpeaker,
} from '../sessionTimelineMessages'
import {
  SESSION_MESSAGE_STATUS,
  SESSION_TIMELINE_ROLE,
  type SessionInputMode,
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
  userMessage: SessionTimelineMessage
  assistantMessage: SessionTimelineMessage
  source: SessionStreamSource
  pendingToast?: string
  successToast: string
  failureToast: string
  clearComposer?: boolean
}

export function useSessionStreamTurn({
  sessionId,
  inputMode,
  contextPreviewUsage,
  setAccurateUsageOverride,
  setComposerText,
  setLocalMessages,
  setForceScrollKey,
  refreshSessionData,
  showToast,
  logger,
  onExit,
}: {
  sessionId: string
  inputMode: SessionInputMode
  contextPreviewUsage: ContextUsageSnapshot | null
  setAccurateUsageOverride: Dispatch<SetStateAction<ContextUsageSnapshot | null>>
  setComposerText: Dispatch<SetStateAction<string>>
  setLocalMessages: Dispatch<SetStateAction<SessionTimelineMessage[]>>
  setForceScrollKey: Dispatch<SetStateAction<number>>
  refreshSessionData: (options?: { silent?: boolean; clearAccurateUsage?: boolean }) => Promise<boolean>
  showToast: (message: string) => void
  logger: SessionRoomLogger
  onExit: () => void
}) {
  const [sending, setSending] = useState(false)
  const [stoppingRequestId, setStoppingRequestId] = useState<string | null>(null)
  const activeStreamRef = useRef<ActiveStream | null>(null)
  const stoppingRequestIdRef = useRef<string | null>(null)
  const stopSettledRequestIdsRef = useRef<Set<string>>(new Set())

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
      current.map((message) =>
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

  const appendLocalStreamError = useCallback((assistantMessageId: string, turnId: number, errorText: string) => {
    setLocalMessages((current) => [
      ...current.map((message) =>
        message.id === assistantMessageId ? { ...message, status: SESSION_MESSAGE_STATUS.ERROR } : message,
      ),
      {
        id: `local-error-${turnId}-${crypto.randomUUID()}`,
        turnId,
        seqInTurn: 5,
        role: SESSION_TIMELINE_ROLE.ERROR,
        content: errorText,
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

  const appendStreamEvent = useCallback((event: PlayStreamEvent, assistantMessageId: string, turnId: number) => {
    if (event.type === PLAY_STREAM_EVENT_TYPE.TURN_STARTED) return

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
      const usage = fromTurnUsage(event.payload.usage, contextPreviewUsage, {
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
      if (usage) setAccurateUsageOverride(usage)
      setLocalMessages((current) =>
        current.map((message) =>
          message.id === assistantMessageId
            ? {
                ...message,
                status: SESSION_MESSAGE_STATUS.DONE,
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
      logger.warn('stream sse error event', {
        turnId,
        status: 'error',
        statusCode: event.payload.statusCode,
      })
      setLocalMessages((current) => [
        ...current.map((message) =>
          message.id === assistantMessageId ? { ...message, status: SESSION_MESSAGE_STATUS.ERROR } : message,
        ),
        {
          id: `local-error-${turnId}-${crypto.randomUUID()}`,
          turnId,
          seqInTurn: 5,
          role: SESSION_TIMELINE_ROLE.ERROR,
          content: errorText,
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
  }, [contextPreviewUsage, logger, setAccurateUsageOverride, setLocalMessages])

  const streamLocalTurn = useCallback(async ({
    text,
    turnId,
    userMessage,
    assistantMessage,
    source,
    pendingToast,
    successToast,
    failureToast,
    clearComposer = false,
  }: StreamLocalTurnOptions) => {
    const controller = new AbortController()
    const requestId = crypto.randomUUID()
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
    setAccurateUsageOverride(null)
    if (clearComposer) setComposerText('')
    setSending(true)
    setLocalMessages((current) => [...current, userMessage, assistantMessage])
    setForceScrollKey((current) => current + 1)
    logger.info('stream started', {
      requestId,
      source,
      turnId,
      mode: inputMode,
      textLength: text.length,
      hasText: Boolean(text.trim()),
    })
    if (pendingToast) showToast(pendingToast)

    let streamFailure: string | null = null
    let completedTurn = false
    try {
      await consumeChatStream(
        {
          sessionId,
          text,
          mode: inputMode,
          requestId,
        },
        {
          signal: controller.signal,
          onEvent: (event) => {
            appendStreamEvent(event, assistantMessage.id, turnId)
            if (event.type === PLAY_STREAM_EVENT_TYPE.ERROR) streamFailure = event.payload.message || failureToast
          },
        },
      )
      if (stoppingRequestIdRef.current === requestId || stopSettledRequestIdsRef.current.has(requestId)) return
      if (streamFailure) throw new Error(streamFailure)
      completedTurn = true
      const refreshed = await refreshSessionData({ silent: true, clearAccurateUsage: false })
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
        if (!streamFailure) appendLocalStreamError(assistantMessage.id, turnId, errorText)
        showToast(errorText)
      }
    } finally {
      setSending(false)
      if (activeStreamRef.current?.requestId === requestId) activeStreamRef.current = null
      stopSettledRequestIdsRef.current.delete(requestId)
      if (!completedTurn) setAccurateUsageOverride(null)
    }
  }, [
    appendLocalStreamError,
    appendStreamEvent,
    inputMode,
    logger,
    markStreamStopped,
    refreshSessionData,
    sessionId,
    setAccurateUsageOverride,
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

  return {
    sending,
    stopping: Boolean(stoppingRequestId),
    streamLocalTurn,
    stopActiveStream,
    handleExitSession,
  }
}
