import { useCallback, useEffect, useMemo, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { listStoryCharacters } from '@/lib/api/characters'
import { getContextPreview } from '@/lib/api/contextPreview'
import { getCurrentScene } from '@/lib/api/scene'
import { getSession, getSessionHistory } from '@/lib/api/sessions'
import { listSessionStatusTables } from '@/lib/api/statusTables'
import { fromContextPreviewEstimate, type ContextUsageSnapshot } from '@/types/contextUsage'
import { PLAYER_CHARACTER_STATUS } from '@/types/session'
import { STATUS_KIND } from '@/types/statusTables'
import type { SessionRoomLogger } from '../sessionRoomLogger'
import { mapHistoryToMessages } from '../sessionTimelineMessages'
import type { SessionTimelineMessage } from '../sessionRoomTypes'

export function useSessionRoomData({
  sessionId,
  showToast,
  logger,
}: {
  sessionId: string
  showToast: (message: string) => void
  logger: SessionRoomLogger
}) {
  const queryClient = useQueryClient()
  const [localMessages, setLocalMessages] = useState<SessionTimelineMessage[]>([])
  const [optimisticTruncateFromTurn, setOptimisticTruncateFromTurn] = useState<number | null>(null)
  const [accurateUsageOverride, setAccurateUsageOverride] = useState<ContextUsageSnapshot | null>(null)
  const [forceScrollKey, setForceScrollKey] = useState(0)
  const [timelineResetKey, setTimelineResetKey] = useState(0)

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

  const contextPreviewQuery = useQuery({
    queryKey: ['play-session-context-preview', sessionId],
    enabled: Boolean(session && !playerCharacterInvalid),
    queryFn: () => getContextPreview(sessionId),
  })

  const contextPreviewUsage = useMemo(
    () => fromContextPreviewEstimate(contextPreviewQuery.data),
    [contextPreviewQuery.data],
  )

  const baseMessages = useMemo(
    () => mapHistoryToMessages({ turns: historyQuery.data, playerCharacter }),
    [historyQuery.data, playerCharacter],
  )

  const lastPersistedTurnId = useMemo(
    () => Math.max(0, ...baseMessages.map((message) => message.turnId)),
    [baseMessages],
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

  useEffect(() => {
    setLocalMessages([])
    setOptimisticTruncateFromTurn(null)
    setAccurateUsageOverride(null)
    setTimelineResetKey((current) => current + 1)
    logger.info('session data reset', { status: 'session_changed' })
  }, [logger, sessionId])

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
      setTimelineResetKey((current) => current + 1)
      if (clearAccurateUsage) setAccurateUsageOverride(null)
      logger.info('session data refreshed', { status: 'success', clearAccurateUsage })
      return true
    } catch (error) {
      logger.warn('session data refresh failed', { status: 'error', error })
      if (!silent) showToast('刷新失败，请手动刷新页面')
      return false
    }
  }, [logger, queryClient, sessionId, showToast])

  return {
    sessionQuery,
    historyQuery,
    sceneQuery,
    statusTablesQuery,
    charactersQuery,
    session,
    characters,
    playerCharacter,
    playerCharacterInvalid,
    contextPreviewQuery,
    contextPreviewUsage,
    accurateUsageOverride,
    setAccurateUsageOverride,
    localMessages,
    setLocalMessages,
    optimisticTruncateFromTurn,
    setOptimisticTruncateFromTurn,
    visibleMessages,
    lastTurnId,
    lastPersistedTurnId,
    forceScrollKey,
    setForceScrollKey,
    timelineResetKey,
    refreshSessionData,
  }
}
