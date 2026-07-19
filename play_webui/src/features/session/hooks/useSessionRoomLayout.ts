import { useEffect, useMemo, useState } from 'react'
import type { CSSProperties } from 'react'
import { SESSION_FONT_SCALE_DEFAULT, useSessionUiStore } from '@/stores/sessionUiStore'
import type { SessionRoomLogger } from '../sessionRoomLogger'

export function useSessionRoomLayout({
  sessionId,
  logger,
}: {
  sessionId: string
  logger: SessionRoomLogger
}) {
  const [settingsOpen, setSettingsOpen] = useState(false)
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
    setSettingsOpen(false)
    logger.info('session preferences reset', { status: 'session_changed' })
  }, [logger, sessionId])

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

  return {
    sessionExperienceStyle,
    settingsOpen,
    setSettingsOpen,
    fontScale,
    showThinking,
    showTools,
    setFontScale,
    setShowThinking,
    setShowTools,
    resetFontScale: () => setFontScale(SESSION_FONT_SCALE_DEFAULT),
  }
}
