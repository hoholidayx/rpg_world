'use client'

import { useCallback, useEffect, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { createSessionDerivation } from '@/lib/api/sessions'
import type { SessionRoomLogger } from '../sessionRoomLogger'
import type { SessionTimelineMessage } from '../sessionRoomTypes'

export function useSessionDerivation({
  sessionId,
  showToast,
  logger,
}: {
  sessionId: string
  showToast: (message: string) => void
  logger: SessionRoomLogger
}) {
  const [turnId, setTurnId] = useState<number | null>(null)
  const [title, setTitle] = useState('')
  const {
    mutate,
    reset,
    isPending,
    error: mutationError,
  } = useMutation({
    mutationFn: ({ selectedTurnId, requestedTitle }: {
      selectedTurnId: number
      requestedTitle: string
    }) => createSessionDerivation(sessionId, selectedTurnId, requestedTitle),
    onSuccess: (job) => {
      logger.info('session derivation submitted', {
        jobId: job.jobId,
        turnId: job.turnId,
        status: job.status,
      })
      setTurnId(null)
      setTitle('')
      showToast(`Turn #${job.turnId} 的分支任务已提交，完成后将在通知中心显示`)
    },
    onError: (error, variables) => {
      logger.warn('session derivation submission failed', {
        turnId: variables.selectedTurnId,
        error,
      })
    },
  })

  useEffect(() => {
    setTurnId(null)
    setTitle('')
  }, [sessionId])

  const open = useCallback((message: SessionTimelineMessage) => {
    if (
      !message.canDerive
      || !Number.isInteger(message.turnId)
      || message.turnId <= 0
    ) {
      showToast('当前消息不是可创建分支的已提交 Turn 边界')
      return
    }
    reset()
    setTitle('')
    setTurnId(message.turnId)
    logger.info('session derivation dialog opened', { turnId: message.turnId })
  }, [logger, reset, showToast])

  const close = useCallback(() => {
    if (isPending) return
    reset()
    setTurnId(null)
    setTitle('')
  }, [isPending, reset])

  const submit = useCallback(() => {
    if (turnId === null || isPending) return
    mutate({
      selectedTurnId: turnId,
      requestedTitle: title.trim(),
    })
  }, [isPending, mutate, title, turnId])

  return {
    open: turnId !== null,
    turnId,
    title,
    setTitle,
    pending: isPending,
    error: mutationError instanceof Error ? mutationError.message : null,
    openDialog: open,
    closeDialog: close,
    submit,
  }
}
