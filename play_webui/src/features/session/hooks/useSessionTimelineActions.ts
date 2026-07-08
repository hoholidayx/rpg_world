import { useCallback, useEffect, useState } from 'react'
import { deleteSessionMessage, truncateSessionTurn, type getSession } from '@/lib/api/sessions'
import type { SessionPlayerCharacter } from '@/types/session'
import type { SessionRoomLogger } from '../sessionRoomLogger'
import {
  canEditMessage,
  canRetryMessage,
  makePlayerSpeaker,
  streamPlaceholder,
} from '../sessionTimelineMessages'
import {
  SESSION_MESSAGE_STATUS,
  SESSION_STREAM_SOURCE,
  SESSION_TIMELINE_ROLE,
  type ConfirmRequest,
  type NarrativeStyle,
  type SessionInputMode,
  type SessionStreamSource,
  type SessionTimelineMessage,
} from '../sessionRoomTypes'
import type { StreamLocalTurnOptions } from './useSessionStreamTurn'

type SessionPayload = Awaited<ReturnType<typeof getSession>>

export function useSessionTimelineActions({
  sessionId,
  session,
  playerCharacter,
  playerCharacterInvalid,
  inputMode,
  currentNarrativeStyle,
  composerText,
  timelineResetKey,
  lastTurnId,
  lastPersistedTurnId,
  sending,
  stopping,
  streamLocalTurn,
  setOptimisticTruncateFromTurn,
  refreshSessionData,
  requestConfirm,
  requireRoleSelection,
  showToast,
  logger,
}: {
  sessionId: string
  session: SessionPayload | undefined
  playerCharacter: SessionPlayerCharacter | null
  playerCharacterInvalid: boolean
  inputMode: SessionInputMode
  currentNarrativeStyle: NarrativeStyle
  composerText: string
  timelineResetKey: number
  lastTurnId: number
  lastPersistedTurnId: number
  sending: boolean
  stopping: boolean
  streamLocalTurn: (options: StreamLocalTurnOptions) => Promise<void>
  setOptimisticTruncateFromTurn: (turnId: number | null) => void
  refreshSessionData: (options?: { silent?: boolean; clearAccurateUsage?: boolean }) => Promise<boolean>
  requestConfirm: (request: ConfirmRequest) => void
  requireRoleSelection: () => void
  showToast: (message: string) => void
  logger: SessionRoomLogger
}) {
  const [editingMessageId, setEditingMessageId] = useState<string | null>(null)
  const [editDraft, setEditDraft] = useState('')

  useEffect(() => {
    setEditingMessageId(null)
    setEditDraft('')
  }, [sessionId, timelineResetKey])

  const ensureCanStartTurn = useCallback(() => {
    if (!session) {
      showToast('会话加载中，请稍后再试')
      return false
    }
    if (playerCharacterInvalid) {
      requireRoleSelection()
      return false
    }
    if (sending) {
      showToast('当前仍在生成，请稍后再试')
      return false
    }
    if (stopping) {
      showToast('正在停止当前生成，请稍后再试')
      return false
    }
    return true
  }, [playerCharacterInvalid, requireRoleSelection, sending, session, showToast, stopping])

  const streamTurnFromText = useCallback(async ({
    message,
    text,
    source,
    pendingToast,
    successToast,
    failureToast,
    clearComposer = false,
  }: {
    message?: SessionTimelineMessage
    text: string
    source: SessionStreamSource
    pendingToast?: string
    successToast: string
    failureToast: string
    clearComposer?: boolean
  }) => {
    if (!ensureCanStartTurn()) return

    const trimmedText = text.trim()
    if (!trimmedText) {
      showToast(source === SESSION_STREAM_SOURCE.SEND ? '请输入内容后再发送' : '发送内容不能为空')
      return
    }

    const replacingLastTurn = Boolean(message?.messageId) && message?.turnId === lastPersistedTurnId
    const turnId = replacingLastTurn && message ? message.turnId : lastTurnId + 1
    const playerSpeaker = makePlayerSpeaker(playerCharacter)
    const userMessage: SessionTimelineMessage = {
      id: `local-${source}-user-${turnId}-${crypto.randomUUID()}`,
      turnId,
      seqInTurn: 1,
      role: SESSION_TIMELINE_ROLE.USER,
      content: trimmedText,
      createdAt: new Date().toISOString(),
      speaker: { ...playerSpeaker, label: inputMode.toUpperCase() },
      hiddenPrompt: currentNarrativeStyle.prompt,
      status: currentNarrativeStyle.prompt ? SESSION_MESSAGE_STATUS.LOCAL : undefined,
      canCopy: true,
      canRetry: false,
      canEdit: false,
      canDelete: false,
    }
    const assistantMessage = streamPlaceholder(turnId)

    logger.info('timeline stream action started', {
      source,
      turnId,
      messageId: message?.messageId,
      replacingLastTurn,
      mode: inputMode,
      textLength: trimmedText.length,
      hasText: Boolean(trimmedText),
    })

    setEditingMessageId(null)
    setEditDraft('')
    if (replacingLastTurn && message) {
      try {
        await truncateSessionTurn(sessionId, message.turnId)
        setOptimisticTruncateFromTurn(message.turnId)
        logger.info('timeline truncate before regeneration completed', {
          source,
          turnId: message.turnId,
          messageId: message.messageId,
          status: 'success',
        })
      } catch (error) {
        logger.warn('timeline truncate before regeneration failed', {
          source,
          turnId: message.turnId,
          messageId: message.messageId,
          status: 'error',
          error,
        })
        showToast(error instanceof Error ? error.message : failureToast)
        return
      }
    }

    await streamLocalTurn({
      text: trimmedText,
      turnId,
      userMessage,
      assistantMessage,
      source,
      pendingToast,
      successToast,
      failureToast,
      clearComposer,
    })
  }, [
    currentNarrativeStyle,
    ensureCanStartTurn,
    inputMode,
    lastPersistedTurnId,
    lastTurnId,
    logger,
    playerCharacter,
    sessionId,
    setOptimisticTruncateFromTurn,
    showToast,
    streamLocalTurn,
  ])

  const handleSend = useCallback(async () => {
    await streamTurnFromText({
      text: composerText,
      source: SESSION_STREAM_SOURCE.SEND,
      successToast: '发送完成',
      failureToast: '未知流式错误',
      clearComposer: true,
    })
  }, [composerText, streamTurnFromText])

  const performRetry = useCallback(async (message: SessionTimelineMessage) => {
    if (!canRetryMessage(message)) {
      showToast('当前回合不可重试')
      return
    }
    await streamTurnFromText({
      message,
      text: message.content,
      source: SESSION_STREAM_SOURCE.RETRY,
      pendingToast: `正在重试 turn #${message.turnId}`,
      successToast: `已重试 turn #${message.turnId}`,
      failureToast: '重试失败',
    })
  }, [showToast, streamTurnFromText])

  const handleRetry = useCallback((message: SessionTimelineMessage) => {
    if (!canRetryMessage(message)) {
      showToast('当前回合不可重试')
      return
    }
    void performRetry(message)
  }, [performRetry, showToast])

  const handleCopy = useCallback((message: SessionTimelineMessage) => {
    if (!message.content.trim()) {
      showToast('当前消息没有可复制内容')
      return
    }
    navigator.clipboard?.writeText(message.content).then(
      () => showToast('已复制当前消息'),
      () => {
        logger.warn('timeline copy failed', {
          turnId: message.turnId,
          messageId: message.messageId,
          textLength: message.content.length,
        })
        showToast('复制失败，请手动选择文本')
      },
    )
  }, [logger, showToast])

  const handleStartEdit = useCallback((message: SessionTimelineMessage) => {
    if (!canEditMessage(message)) {
      showToast('当前消息不可编辑')
      return
    }
    setEditingMessageId(message.id)
    setEditDraft(message.content)
    logger.info('timeline edit started', {
      turnId: message.turnId,
      messageId: message.messageId,
      textLength: message.content.length,
    })
  }, [logger, showToast])

  const performSendEdited = useCallback(async (message: SessionTimelineMessage, text: string) => {
    if (!canEditMessage(message)) {
      showToast('当前消息不可编辑')
      return
    }
    await streamTurnFromText({
      message,
      text,
      source: SESSION_STREAM_SOURCE.EDIT,
      pendingToast: '正在发送编辑',
      successToast: '已发送编辑',
      failureToast: '编辑失败',
    })
  }, [showToast, streamTurnFromText])

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
    void performSendEdited(message, text)
  }, [editDraft, performSendEdited, showToast])

  const performDelete = useCallback(async (message: SessionTimelineMessage) => {
    if (!message.canDelete || !message.messageId) {
      showToast('当前消息不可删除')
      return
    }
    showToast('正在删除消息')
    logger.info('timeline delete started', {
      turnId: message.turnId,
      messageId: message.messageId,
    })
    try {
      await deleteSessionMessage(sessionId, message.messageId)
      const refreshed = await refreshSessionData({ silent: true })
      logger.info('timeline delete completed', {
        turnId: message.turnId,
        messageId: message.messageId,
        status: refreshed ? 'success' : 'refresh_failed',
      })
      showToast(refreshed ? '已删除消息' : '删除已提交，但刷新失败，请手动刷新页面')
    } catch (error) {
      logger.warn('timeline delete failed', {
        turnId: message.turnId,
        messageId: message.messageId,
        status: 'error',
        error,
      })
      showToast(error instanceof Error ? error.message : '删除失败')
    }
  }, [logger, refreshSessionData, sessionId, showToast])

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

  const cancelEdit = useCallback(() => {
    setEditingMessageId(null)
    setEditDraft('')
    showToast('已取消编辑')
  }, [showToast])

  return {
    editingMessageId,
    editDraft,
    setEditDraft,
    handleSend,
    handleRetry,
    handleCopy,
    handleStartEdit,
    handleSendEdit,
    handleDelete,
    cancelEdit,
  }
}
