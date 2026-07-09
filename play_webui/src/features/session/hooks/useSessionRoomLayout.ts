import { CSSProperties, PointerEvent, useEffect, useMemo, useState } from 'react'
import { SESSION_FONT_SCALE_DEFAULT, useSessionUiStore } from '@/stores/sessionUiStore'
import type { SessionRoomLogger } from '../sessionRoomLogger'

const defaultSidebarSizes = {
  left: 300,
  right: 340,
}

const collapsedSidebarSize = 72

const sidebarLimits = {
  leftMin: 260,
  leftMax: 460,
  rightMin: 280,
  rightMax: 500,
}

type DragState = {
  side: 'left' | 'right'
  startX: number
  startLeft: number
  startRight: number
}

export type MobilePanel = 'left' | 'right' | null

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value))
}

export function useSessionRoomLayout({
  sessionId,
  logger,
}: {
  sessionId: string
  logger: SessionRoomLogger
}) {
  const [leftWidth, setLeftWidth] = useState(defaultSidebarSizes.left)
  const [rightWidth, setRightWidth] = useState(defaultSidebarSizes.right)
  const [leftCollapsed, setLeftCollapsed] = useState(false)
  const [rightCollapsed, setRightCollapsed] = useState(false)
  const [mobilePanel, setMobilePanel] = useState<MobilePanel>(null)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [dragState, setDragState] = useState<DragState | null>(null)
  const fontScale = useSessionUiStore((state) => state.fontScale)
  const showThinking = useSessionUiStore((state) => state.showThinking)
  const showTools = useSessionUiStore((state) => state.showTools)
  const setFontScale = useSessionUiStore((state) => state.setFontScale)
  const setShowThinking = useSessionUiStore((state) => state.setShowThinking)
  const setShowTools = useSessionUiStore((state) => state.setShowTools)
  const syncFontScale = useSessionUiStore((state) => state.syncFontScale)
  const syncDiagnosticsDisplay = useSessionUiStore((state) => state.syncDiagnosticsDisplay)

  useEffect(() => {
    syncFontScale()
    syncDiagnosticsDisplay()
  }, [syncDiagnosticsDisplay, syncFontScale])

  useEffect(() => {
    setMobilePanel(null)
    setSettingsOpen(false)
    logger.info('layout reset', { status: 'session_changed' })
  }, [logger, sessionId])

  useEffect(() => {
    if (!dragState) return

    const handlePointerMove = (event: globalThis.PointerEvent) => {
      if (dragState.side === 'left') {
        setLeftWidth(clamp(dragState.startLeft + event.clientX - dragState.startX, sidebarLimits.leftMin, sidebarLimits.leftMax))
        return
      }
      setRightWidth(clamp(dragState.startRight - (event.clientX - dragState.startX), sidebarLimits.rightMin, sidebarLimits.rightMax))
    }

    const stopDragging = () => {
      setDragState(null)
    }

    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
    window.addEventListener('pointermove', handlePointerMove)
    window.addEventListener('pointerup', stopDragging)
    window.addEventListener('pointercancel', stopDragging)

    return () => {
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
      window.removeEventListener('pointermove', handlePointerMove)
      window.removeEventListener('pointerup', stopDragging)
      window.removeEventListener('pointercancel', stopDragging)
    }
  }, [dragState])

  const gridStyle = useMemo(
    () =>
      ({
        '--session-grid-columns': `${leftCollapsed ? collapsedSidebarSize : leftWidth}px 8px minmax(0,1fr) 8px ${
          rightCollapsed ? collapsedSidebarSize : rightWidth
        }px`,
      }) as CSSProperties,
    [leftCollapsed, leftWidth, rightCollapsed, rightWidth],
  )

  const sessionExperienceStyle = useMemo(
    () =>
      ({
        '--session-message-font-size': `${14 * (fontScale / 100)}px`,
        '--session-message-line-height': `${28 * (fontScale / 100)}px`,
        '--session-segment-label-font-size': `${11 * (fontScale / 100)}px`,
        '--session-composer-font-size': `${16 * (fontScale / 100)}px`,
        '--session-composer-line-height': `${28 * (fontScale / 100)}px`,
      }) as CSSProperties,
    [fontScale],
  )

  const startDrag = (side: 'left' | 'right') => (event: PointerEvent<HTMLButtonElement>) => {
    event.preventDefault()
    setDragState({
      side,
      startX: event.clientX,
      startLeft: leftWidth,
      startRight: rightWidth,
    })
  }

  return {
    gridStyle,
    sessionExperienceStyle,
    leftCollapsed,
    rightCollapsed,
    mobilePanel,
    setMobilePanel,
    settingsOpen,
    setSettingsOpen,
    fontScale,
    showThinking,
    showTools,
    setFontScale,
    setShowThinking,
    setShowTools,
    resetFontScale: () => setFontScale(SESSION_FONT_SCALE_DEFAULT),
    toggleLeftCollapsed: () => setLeftCollapsed((current) => !current),
    toggleRightCollapsed: () => setRightCollapsed((current) => !current),
    startDrag,
  }
}
