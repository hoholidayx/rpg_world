import { useCallback, useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getSessionHistoryPage } from '@/lib/api/sessions'
import { sessionHistoryPaginationConfig } from '@/lib/config/appConfig'
import type { HistoryPage } from '@/types/session'
import type { SessionRoomLogger } from '../sessionRoomLogger'
import {
  HISTORY_LOAD_DIRECTION,
  HISTORY_REFRESH_MODE,
  type HistoryLoadDirection,
  type HistoryRefreshMode,
} from '../sessionRoomTypes'

const HISTORY_PAGE_QUERY_SCOPE = {
  LATEST: 'latest',
} as const

function pageKey(page: HistoryPage) {
  return `${page.startTurnId ?? 'empty'}:${page.endTurnId ?? 'empty'}:${page.latestTurnId}`
}

function pageWindowKey(page: HistoryPage) {
  return `${page.startTurnId ?? 'empty'}:${page.endTurnId ?? 'empty'}`
}

function sortPages(pages: HistoryPage[]) {
  return [...pages].sort((first, second) => {
    const firstStart = first.startTurnId ?? Number.MAX_SAFE_INTEGER
    const secondStart = second.startTurnId ?? Number.MAX_SAFE_INTEGER
    return firstStart - secondStart
  })
}

function uniquePages(pages: HistoryPage[]) {
  const byKey = new Map<string, HistoryPage>()
  for (const page of pages) byKey.set(pageKey(page), page)
  return sortPages([...byKey.values()])
}

function trimPagesAroundActive(pages: HistoryPage[], activeKey: string, maxCachedPages: number) {
  const normalized = uniquePages(pages)
  if (normalized.length <= maxCachedPages) return normalized

  const activeIndex = normalized.findIndex((page) => pageKey(page) === activeKey)
  if (activeIndex < 0) return normalized.slice(-maxCachedPages)

  const start = Math.min(
    Math.max(0, activeIndex - maxCachedPages + 1),
    Math.max(0, normalized.length - maxCachedPages),
  )
  return normalized.slice(start, start + maxCachedPages)
}

function cachedBefore(pages: HistoryPage[], activePage: HistoryPage) {
  if (activePage.startTurnId === null) return null
  return sortPages(pages)
    .filter((page) => page.endTurnId !== null && page.endTurnId < activePage.startTurnId!)
    .at(-1) ?? null
}

function cachedAfter(pages: HistoryPage[], activePage: HistoryPage) {
  if (activePage.endTurnId === null) return null
  return sortPages(pages)
    .find((page) => page.startTurnId !== null && page.startTurnId > activePage.endTurnId!) ?? null
}

function isLatestHistoryPage(page: HistoryPage | null) {
  if (!page) return false
  if (page.latestTurnId === 0) return true
  return !page.hasAfter && page.endTurnId === page.latestTurnId
}

function refreshRequestForPage(page: HistoryPage) {
  if (page.startTurnId !== null && page.startTurnId > 1) {
    return { afterTurnId: page.startTurnId - 1 }
  }
  if (page.endTurnId !== null) {
    return { beforeTurnId: page.endTurnId + 1 }
  }
  return null
}

export function useSessionHistoryWindow({
  sessionId,
  logger,
}: {
  sessionId: string
  logger: SessionRoomLogger
}) {
  const pageTurnLimit = sessionHistoryPaginationConfig.pageTurnLimit
  const maxCachedPages = sessionHistoryPaginationConfig.maxCachedPages
  const [pages, setPages] = useState<HistoryPage[]>([])
  const [activePageKey, setActivePageKey] = useState('')
  const [loadingDirection, setLoadingDirection] = useState<HistoryLoadDirection | null>(null)
  const [jumpingToLatest, setJumpingToLatest] = useState(false)

  const latestQuery = useQuery({
    queryKey: ['play-session-history-page', sessionId, HISTORY_PAGE_QUERY_SCOPE.LATEST, pageTurnLimit],
    queryFn: () => getSessionHistoryPage(sessionId, { limit: pageTurnLimit }),
    refetchOnReconnect: false,
    refetchOnWindowFocus: false,
  })
  const latestPage = latestQuery.data
  const refetchLatestPage = latestQuery.refetch

  const activePage = useMemo(
    () => pages.find((page) => pageKey(page) === activePageKey) ?? latestPage ?? null,
    [activePageKey, latestPage, pages],
  )
  const isLatestPage = isLatestHistoryPage(activePage)

  const rememberPage = useCallback((page: HistoryPage, currentPage: HistoryPage | null) => {
    const nextKey = pageKey(page)
    setPages((current) => {
      const candidates = currentPage ? [currentPage, ...current, page] : [...current, page]
      return trimPagesAroundActive(candidates, nextKey, maxCachedPages)
    })
    setActivePageKey(nextKey)
  }, [maxCachedPages])

  const applyLatestPage = useCallback((page: HistoryPage) => {
    const nextKey = pageKey(page)
    setPages([page])
    setActivePageKey(nextKey)
  }, [])

  const replaceActivePage = useCallback((page: HistoryPage, currentPage: HistoryPage | null) => {
    const nextKey = pageKey(page)
    const currentKey = currentPage ? pageKey(currentPage) : ''
    const nextWindowKey = pageWindowKey(page)
    setPages((current) => {
      const candidates = current.filter((item) => (
        pageKey(item) !== currentKey && pageWindowKey(item) !== nextWindowKey
      ))
      return trimPagesAroundActive([...candidates, page], nextKey, maxCachedPages)
    })
    setActivePageKey(nextKey)
  }, [maxCachedPages])

  useEffect(() => {
    setPages([])
    setActivePageKey('')
    setLoadingDirection(null)
    setJumpingToLatest(false)
  }, [pageTurnLimit, sessionId])

  useEffect(() => {
    if (!latestPage) return
    setPages((current) => (current.length ? current : [latestPage]))
    setActivePageKey((current) => current || pageKey(latestPage))
  }, [latestPage])

  const loadAdjacentPage = useCallback(async (direction: HistoryLoadDirection) => {
    if (!activePage || loadingDirection) return false
    if (direction === HISTORY_LOAD_DIRECTION.BEFORE && !activePage.hasBefore) return false
    if (direction === HISTORY_LOAD_DIRECTION.AFTER && !activePage.hasAfter) return false

    const cached = direction === HISTORY_LOAD_DIRECTION.BEFORE
      ? cachedBefore(pages, activePage)
      : cachedAfter(pages, activePage)
    if (cached) {
      setActivePageKey(pageKey(cached))
      return true
    }

    const boundaryTurnId = direction === HISTORY_LOAD_DIRECTION.BEFORE ? activePage.startTurnId : activePage.endTurnId
    if (boundaryTurnId === null) return false

    setLoadingDirection(direction)
    try {
      const page = await getSessionHistoryPage(sessionId, {
        limit: pageTurnLimit,
        beforeTurnId: direction === HISTORY_LOAD_DIRECTION.BEFORE ? boundaryTurnId : undefined,
        afterTurnId: direction === HISTORY_LOAD_DIRECTION.AFTER ? boundaryTurnId : undefined,
      })
      if (!page.turns.length) return false
      rememberPage(page, activePage)
      logger.info('history page loaded', {
        direction,
        startTurnId: page.startTurnId,
        endTurnId: page.endTurnId,
        latestTurnId: page.latestTurnId,
      })
      return true
    } catch (error) {
      logger.warn('history page load failed', { direction, error })
      return false
    } finally {
      setLoadingDirection(null)
    }
  }, [activePage, loadingDirection, logger, pageTurnLimit, pages, rememberPage, sessionId])

  const fetchLatestPage = useCallback(async ({ apply = true }: { apply?: boolean } = {}) => {
    try {
      const result = await refetchLatestPage()
      if (!result.data) return null
      if (apply) applyLatestPage(result.data)
      return result.data
    } catch (error) {
      logger.warn('history latest page reload failed', { error })
      return null
    }
  }, [applyLatestPage, logger, refetchLatestPage])

  const refreshHistoryWindow = useCallback(async ({ mode }: { mode: HistoryRefreshMode }) => {
    if (mode === HISTORY_REFRESH_MODE.LATEST) return Boolean(await fetchLatestPage())

    if (!activePage) return Boolean(await fetchLatestPage())

    const activeWasLatest = isLatestHistoryPage(activePage)
    const request = refreshRequestForPage(activePage)
    if (!request) return Boolean(await fetchLatestPage())

    try {
      const page = await getSessionHistoryPage(sessionId, {
        limit: pageTurnLimit,
        ...request,
      })
      if (!page.turns.length && page.latestTurnId > 0) {
        return Boolean(await fetchLatestPage())
      }
      if (activeWasLatest && !isLatestHistoryPage(page)) {
        return Boolean(await fetchLatestPage())
      }
      replaceActivePage(page, activePage)
      logger.info('history active page refreshed', {
        startTurnId: page.startTurnId,
        endTurnId: page.endTurnId,
        latestTurnId: page.latestTurnId,
      })
      return true
    } catch (error) {
      logger.warn('history active page refresh failed', { error })
      return false
    }
  }, [activePage, fetchLatestPage, logger, pageTurnLimit, replaceActivePage, sessionId])

  const latestTurnId = useMemo(() => {
    return Math.max(
      activePage?.latestTurnId ?? 0,
      latestPage?.latestTurnId ?? 0,
      ...pages.map((page) => page.latestTurnId),
    )
  }, [activePage?.latestTurnId, latestPage?.latestTurnId, pages])

  const jumpToLatestPage = useCallback(async () => {
    setJumpingToLatest(true)
    try {
      const fetchedLatestPage = await fetchLatestPage()
      return fetchedLatestPage?.latestTurnId ?? null
    } finally {
      setJumpingToLatest(false)
    }
  }, [fetchLatestPage])

  const loadPreviousPage = useCallback(() => loadAdjacentPage(HISTORY_LOAD_DIRECTION.BEFORE), [loadAdjacentPage])
  const loadNextPage = useCallback(() => loadAdjacentPage(HISTORY_LOAD_DIRECTION.AFTER), [loadAdjacentPage])

  return {
    historyQuery: latestQuery,
    activePage,
    pages,
    loadingBefore: loadingDirection === HISTORY_LOAD_DIRECTION.BEFORE,
    loadingAfter: loadingDirection === HISTORY_LOAD_DIRECTION.AFTER,
    isLatestPage,
    showJumpToLatest: Boolean(activePage && !isLatestPage),
    jumpingToLatest,
    pageTurnLimit,
    latestTurnId,
    loadPreviousPage,
    loadNextPage,
    refreshHistoryWindow,
    jumpToLatestPage,
  }
}
