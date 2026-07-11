import { useCallback, useEffect, useMemo, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { listStoryCharacters } from '@/lib/api/characters'
import { getContextPreview } from '@/lib/api/contextPreview'
import { getCurrentScene } from '@/lib/api/scene'
import { getSession } from '@/lib/api/sessions'
import { listSessionStatusTables } from '@/lib/api/statusTables'
import { getSessionSummary, listSessionSummaries } from '@/lib/api/summaries'
import { sessionContextUsageConfig } from '@/lib/config/appConfig'
import { fromContextPreviewEstimate, type ContextUsageSnapshot } from '@/types/contextUsage'
import { PLAYER_CHARACTER_STATUS } from '@/types/session'
import { STATUS_KIND } from '@/types/statusTables'
import type { SessionRoomLogger } from '../sessionRoomLogger'
import { mapHistoryToMessages } from '../sessionTimelineMessages'
import {
  HISTORY_REFRESH_MODE,
  SESSION_HISTORY_MESSAGES,
  SESSION_TIMELINE_ROLE,
  type RefreshSessionDataOptions,
  type SessionRailDrawerState,
  type SessionTimelineMessage,
} from '../sessionRoomTypes'
import { useSessionHistoryWindow } from './useSessionHistoryWindow'

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
  const [localTurnUsageByTurn, setLocalTurnUsageByTurn] = useState<Record<number, ContextUsageSnapshot>>({})
  const [optimisticTruncateFromTurn, setOptimisticTruncateFromTurn] = useState<number | null>(null)
  const [lastTurnUsage, setLastTurnUsage] = useState<ContextUsageSnapshot | null>(null)
  const [forceScrollKey, setForceScrollKey] = useState(0)
  const [timelineResetKey, setTimelineResetKey] = useState(0)
  const [activeRailDrawer, setActiveRailDrawer] = useState<SessionRailDrawerState>(null)

  const sessionQuery = useQuery({
    queryKey: ['play-session', sessionId],
    queryFn: () => getSession(sessionId),
  })

  const session = sessionQuery.data
  const {
    historyQuery,
    activePage: historyPage,
    loadingBefore: historyLoadingBefore,
    loadingAfter: historyLoadingAfter,
    showJumpToLatest: showJumpToLatestHistory,
    jumpingToLatest: jumpingToLatestHistory,
    latestTurnId,
    loadPreviousPage: loadPreviousHistoryPage,
    loadNextPage: loadNextHistoryPage,
    refreshHistoryWindow,
    jumpToLatestPage,
  } = useSessionHistoryWindow({ sessionId, logger })

  const sceneQuery = useQuery({
    queryKey: ['play-session-scene', sessionId],
    queryFn: () => getCurrentScene(sessionId),
  })

  const sceneTablesQuery = useQuery({
    queryKey: ['play-session-status-tables', sessionId, STATUS_KIND.SCENE],
    queryFn: () => listSessionStatusTables(sessionId, STATUS_KIND.SCENE),
  })

  const normalStatusTablesQuery = useQuery({
    queryKey: ['play-session-status-tables', sessionId, STATUS_KIND.NORMAL],
    queryFn: () => listSessionStatusTables(sessionId, STATUS_KIND.NORMAL),
  })

  const summaryIndexQuery = useQuery({
    queryKey: ['play-session-summaries', sessionId],
    queryFn: () => listSessionSummaries(sessionId),
  })

  const selectedSummaryKey = activeRailDrawer?.kind === 'summary'
    ? activeRailDrawer.summaryKey
    : null
  const summaryDetailQuery = useQuery({
    queryKey: ['play-session-summary', sessionId, selectedSummaryKey],
    queryFn: () => getSessionSummary(sessionId, selectedSummaryKey ?? ''),
    enabled: selectedSummaryKey !== null,
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
    () => fromContextPreviewEstimate(
      contextPreviewQuery.data,
      sessionContextUsageConfig.inputBlockThresholdRatio,
    ),
    [contextPreviewQuery.data],
  )

  const refreshContextPreview = useCallback(async () => {
    try {
      const preview = await queryClient.fetchQuery({
        queryKey: ['play-session-context-preview', sessionId],
        queryFn: () => getContextPreview(sessionId),
        staleTime: 0,
      })
      return {
        available: true as const,
        usage: fromContextPreviewEstimate(
          preview,
          sessionContextUsageConfig.inputBlockThresholdRatio,
        ),
      }
    } catch (error) {
      logger.warn('context preview refresh failed', { status: 'error', error })
      return { available: false as const, usage: null }
    }
  }, [logger, queryClient, sessionId])

  const baseMessages = useMemo(
    () => mapHistoryToMessages({ turns: historyPage?.turns, playerCharacter })
      .map((message) => (
        message.role === SESSION_TIMELINE_ROLE.ASSISTANT && localTurnUsageByTurn[message.turnId]
          ? { ...message, usage: localTurnUsageByTurn[message.turnId] }
          : message
      )),
    [historyPage?.turns, localTurnUsageByTurn, playerCharacter],
  )

  const lastPersistedTurnId = latestTurnId

  const visibleMessages = useMemo(() => {
    const historyMessages = optimisticTruncateFromTurn === null
      ? baseMessages
      : baseMessages.filter((message) => message.turnId < optimisticTruncateFromTurn)

    return [...historyMessages, ...localMessages]
      .sort(compareTimelineMessages)
  }, [baseMessages, localMessages, optimisticTruncateFromTurn])

  const lastTurnId = useMemo(
    () => Math.max(lastPersistedTurnId, ...localMessages.map((message) => message.turnId)),
    [lastPersistedTurnId, localMessages],
  )

  useEffect(() => {
    setLocalMessages([])
    setLocalTurnUsageByTurn({})
    setOptimisticTruncateFromTurn(null)
    setLastTurnUsage(null)
    setActiveRailDrawer(null)
    setTimelineResetKey((current) => current + 1)
    logger.info('session data reset', { status: 'session_changed' })
  }, [logger, sessionId])

  const jumpToLatestHistoryBottom = useCallback(async ({
    silent = false,
  }: {
    silent?: boolean
  } = {}) => {
    const latestTurnIdFromJump = await jumpToLatestPage()
    if (latestTurnIdFromJump === null) {
      if (!silent) showToast(SESSION_HISTORY_MESSAGES.LATEST_LOAD_FAILED)
      return null
    }
    setForceScrollKey((current) => current + 1)
    return latestTurnIdFromJump
  }, [jumpToLatestPage, showToast])

  const refreshSessionData = useCallback(async ({
    silent = false,
    clearLastTurnUsage = true,
    preserveDiagnostics = false,
    preserveCommandMessages = false,
    historyMode = HISTORY_REFRESH_MODE.ACTIVE,
    scrollToBottom = false,
  }: RefreshSessionDataOptions = {}) => {
    try {
      const [, historyRefreshed] = await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['play-session', sessionId] }),
        refreshHistoryWindow({ mode: historyMode }),
        queryClient.invalidateQueries({ queryKey: ['play-session-scene', sessionId] }),
        queryClient.invalidateQueries({ queryKey: ['play-session-status-tables', sessionId] }),
        queryClient.invalidateQueries({ queryKey: ['play-session-summaries', sessionId] }),
        queryClient.invalidateQueries({ queryKey: ['play-session-summary', sessionId] }),
        queryClient.invalidateQueries({ queryKey: ['play-session-context-preview', sessionId] }),
      ])
      if (!historyRefreshed) throw new Error('history page refresh failed')
      setLocalMessages((current) => (
        current.filter((message) => (
          (
            preserveDiagnostics
            && (
              message.role === SESSION_TIMELINE_ROLE.THINKING
              || message.role === SESSION_TIMELINE_ROLE.TOOL
            )
          )
          || (preserveCommandMessages && message.metadata?.localCommand === true)
        ))
      ))
      if (!preserveDiagnostics) setLocalTurnUsageByTurn({})
      setOptimisticTruncateFromTurn(null)
      setTimelineResetKey((current) => current + 1)
      if (scrollToBottom) setForceScrollKey((current) => current + 1)
      if (clearLastTurnUsage) setLastTurnUsage(null)
      logger.info('session data refreshed', {
        status: 'success',
        clearLastTurnUsage,
        preserveDiagnostics,
        preserveCommandMessages,
        historyMode,
        scrollToBottom,
      })
      return true
    } catch (error) {
      logger.warn('session data refresh failed', { status: 'error', error })
      if (!silent) showToast('刷新失败，请手动刷新页面')
      return false
    }
  }, [logger, queryClient, refreshHistoryWindow, sessionId, showToast])

  return {
    sessionQuery,
    historyQuery,
    historyPage,
    historyLoadingBefore,
    historyLoadingAfter,
    showJumpToLatestHistory,
    jumpingToLatestHistory,
    loadPreviousHistoryPage,
    loadNextHistoryPage,
    jumpToLatestHistoryBottom,
    sceneQuery,
    sceneTablesQuery,
    normalStatusTablesQuery,
    summaryIndexQuery,
    summaryDetailQuery,
    activeRailDrawer,
    setActiveRailDrawer,
    charactersQuery,
    session,
    characters,
    playerCharacter,
    playerCharacterInvalid,
    contextPreviewQuery,
    contextPreviewUsage,
    refreshContextPreview,
    lastTurnUsage,
    setLastTurnUsage,
    setLocalTurnUsageByTurn,
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

function compareTimelineMessages(first: SessionTimelineMessage, second: SessionTimelineMessage) {
  return (
    first.turnId - second.turnId
    || timelineDisplayOrder(first) - timelineDisplayOrder(second)
    || (first.seqInTurn ?? 0) - (second.seqInTurn ?? 0)
  )
}

function timelineDisplayOrder(message: SessionTimelineMessage) {
  if (message.role === SESSION_TIMELINE_ROLE.USER) return 10
  if (message.role === SESSION_TIMELINE_ROLE.THINKING) return 20
  if (message.role === SESSION_TIMELINE_ROLE.TOOL) return 30
  if (message.role === SESSION_TIMELINE_ROLE.ASSISTANT) return 40
  if (message.role === SESSION_TIMELINE_ROLE.ERROR) return 90
  return 80
}
