import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { StatusTable } from '@/types/statusTables'

const PINNED_STATUS_STORAGE_PREFIX = 'rpg-world-session-pinned-status-tables:'

function storageKey(sessionId: string) {
  return `${PINNED_STATUS_STORAGE_PREFIX}${sessionId}`
}

function parseStoredIds(value: string): number[] | null {
  try {
    const parsed: unknown = JSON.parse(value)
    if (!Array.isArray(parsed)) return null
    const ids = parsed.map(Number)
    if (ids.some((id) => !Number.isSafeInteger(id) || id <= 0)) return null
    return [...new Set(ids)]
  } catch {
    return null
  }
}

export function usePinnedStatusTables({
  sessionId,
  tables,
  ready,
}: {
  sessionId: string
  tables: StatusTable[]
  ready: boolean
}) {
  const [pinnedIds, setPinnedIds] = useState<number[]>([])
  const [initialized, setInitialized] = useState(false)
  const initializedSessionRef = useRef<string | null>(null)

  const persist = useCallback((ids: number[]) => {
    try {
      window.localStorage.setItem(storageKey(sessionId), JSON.stringify(ids))
    } catch {
      // Browser storage is optional; the current in-memory preference remains usable.
    }
  }, [sessionId])

  useEffect(() => {
    setPinnedIds([])
    setInitialized(false)
    initializedSessionRef.current = null
  }, [sessionId])

  useEffect(() => {
    if (!ready || initializedSessionRef.current === sessionId) return
    const currentIds = new Set(tables.map((table) => table.id))
    let nextIds = tables.map((table) => table.id)
    let shouldPersist = false
    try {
      const stored = window.localStorage.getItem(storageKey(sessionId))
      if (stored === null) {
        shouldPersist = true
      } else {
        const parsed = parseStoredIds(stored)
        if (parsed !== null) {
          nextIds = parsed.filter((id) => currentIds.has(id))
          shouldPersist = nextIds.length !== parsed.length
        }
      }
    } catch {
      // Fall back to the first-visit in-memory default when storage is unavailable.
    }
    initializedSessionRef.current = sessionId
    setPinnedIds(nextIds)
    setInitialized(true)
    if (shouldPersist) persist(nextIds)
  }, [persist, ready, sessionId, tables])

  useEffect(() => {
    if (!initialized || initializedSessionRef.current !== sessionId) return
    const currentIds = new Set(tables.map((table) => table.id))
    setPinnedIds((current) => {
      const next = current.filter((id) => currentIds.has(id))
      if (next.length !== current.length) persist(next)
      return next.length === current.length ? current : next
    })
  }, [initialized, persist, sessionId, tables])

  const togglePinned = useCallback((tableId: number) => {
    setPinnedIds((current) => {
      const next = current.includes(tableId)
        ? current.filter((id) => id !== tableId)
        : [...current, tableId]
      persist(next)
      return next
    })
  }, [persist])

  const pinnedIdSet = useMemo(() => new Set(pinnedIds), [pinnedIds])
  const pinnedTables = useMemo(
    () => tables.filter((table) => pinnedIdSet.has(table.id)),
    [pinnedIdSet, tables],
  )

  return {
    initialized,
    pinnedIds,
    pinnedIdSet,
    pinnedTables,
    togglePinned,
  }
}
