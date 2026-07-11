'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { AlignJustify, LogOut, TableProperties } from 'lucide-react'
import { ConfirmDialog } from '@/components/common/Dialog'
import { ThemeSwitcher } from '@/components/theme/ThemeSwitcher'
import { sessionContextUsageConfig } from '@/lib/config/appConfig'
import { cn } from '@/lib/utils/cn'
import type { CharacterCard } from '@/types/characters'
import type { SessionPlayerCharacter } from '@/types/session'
import { SessionComposer } from './SessionComposer'
import { SessionLeftRail, SessionRightRail } from './SessionSideRails'
import { SessionSettingsMenu } from './SessionSettingsMenu'
import { SessionNarrativeOutcomeDialog } from './SessionNarrativeOutcomeDialog'
import { SessionTimeline } from './SessionTimeline'
import { useSessionRoomData } from './hooks/useSessionRoomData'
import { useSessionRoomLayout } from './hooks/useSessionRoomLayout'
import { useSessionMainLLM } from './hooks/useSessionMainLLM'
import { useSessionRoleBinding } from './hooks/useSessionRoleBinding'
import { useSessionStreamTurn } from './hooks/useSessionStreamTurn'
import { useSessionTimelineActions } from './hooks/useSessionTimelineActions'
import { createSessionRoomLogger } from './sessionRoomLogger'
import { isContextInputBlocked } from './contextWindowGate'
import {
  characterSummary,
  firstLetter,
  formatDateTime,
  getCharacterAvatarUrl,
} from './sessionRoomHelpers'
import {
  type ConfirmRequest,
  type NarrativeStyle,
  type NarrativeStyleId,
  type SessionInputMode,
} from './sessionRoomTypes'

const narrativeStyles: NarrativeStyle[] = [
  { id: 'default', label: '默认', prompt: '' },
  { id: 'detailed', label: '细腻描写', prompt: '请用细腻描写推进这一幕。' },
  { id: 'fast', label: '快速推进', prompt: '请快速推进到下一个关键选择。' },
  { id: 'options', label: '多给选项', prompt: '请在回应末尾给出多个可选择的行动方向。' },
]

function Toast({ message }: { message: string }) {
  return (
    <div
      role="status"
      aria-live="polite"
      className={cn(
        'pointer-events-none fixed bottom-6 left-1/2 z-50 -translate-x-1/2 rounded-full bg-slate-950 px-4 py-2 text-sm font-bold text-white shadow-2xl transition',
        message ? 'translate-y-0 opacity-100' : 'translate-y-3 opacity-0',
      )}
    >
      {message}
    </div>
  )
}

function PlayerCharacterDialog({
  open,
  required,
  characters,
  loading,
  currentPlayer,
  selectedCharacterId,
  pending,
  error,
  onSelect,
  onSubmit,
  onClose,
}: {
  open: boolean
  required: boolean
  characters: CharacterCard[]
  loading: boolean
  currentPlayer: SessionPlayerCharacter | null
  selectedCharacterId: number | null
  pending: boolean
  error: string | null
  onSelect: (characterId: number) => void
  onSubmit: () => void
  onClose: () => void
}) {
  if (!open) return null

  const currentCharacterId = currentPlayer?.characterId ?? null
  const canSubmit = Boolean(selectedCharacterId) && (required || selectedCharacterId !== currentCharacterId) && !pending

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/45 px-4 py-8 backdrop-blur-sm">
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="player-character-title"
        className="flex max-h-[calc(100vh-4rem)] w-full max-w-3xl flex-col overflow-hidden rounded-lg border border-slate-200 bg-white shadow-2xl shadow-slate-950/20 dark:border-slate-700 dark:bg-slate-950 dark:shadow-black/50"
      >
        <header className="flex items-start justify-between gap-4 border-b border-slate-200 bg-slate-50 px-6 py-5 dark:border-slate-800 dark:bg-slate-900">
          <div>
            <h2 id="player-character-title" className="text-xl font-black text-slate-950 dark:text-slate-100">
              {required ? '选择你要扮演的角色' : '切换扮演角色'}
            </h2>
            <p className="mt-1 text-sm font-semibold leading-6 text-slate-500 dark:text-slate-300">
              角色选择会影响后续 user 消息的头像、名称和后续 prompt 语义，不重写已有历史。
            </p>
          </div>
          {!required ? (
            <button
              type="button"
              onClick={onClose}
              className="flex h-9 w-9 items-center justify-center rounded-lg text-slate-500 transition hover:bg-slate-100 hover:text-slate-900 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-slate-50"
              aria-label="关闭"
            >
              ×
            </button>
          ) : null}
        </header>

        <div className="overflow-y-auto px-6 py-5">
          {error ? (
            <p className="mb-4 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm font-bold text-rose-700 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-200">
              {error}
            </p>
          ) : null}

          {loading ? (
            <section className="rounded-lg border border-dashed border-slate-300 bg-slate-50 px-5 py-12 text-center dark:border-slate-700 dark:bg-slate-900">
              <h3 className="text-lg font-black text-slate-950 dark:text-slate-100">正在加载可扮演角色</h3>
              <p className="mt-2 text-sm font-semibold leading-6 text-slate-500 dark:text-slate-300">
                角色列表加载完成后即可选择。绑定完成前本会话不能发送消息。
              </p>
            </section>
          ) : characters.length ? (
            <div className="grid gap-3 md:grid-cols-3">
              {characters.map((character) => {
                const avatarUrl = getCharacterAvatarUrl(character)
                const selected = selectedCharacterId === character.id
                const current = currentCharacterId === character.id
                return (
                  <button
                    key={character.id}
                    type="button"
                    onClick={() => onSelect(character.id)}
                    className={cn(
                      'grid min-h-44 gap-3 rounded-lg border p-4 text-left transition',
                      selected
                        ? 'border-violet-400 bg-violet-50 shadow-[inset_0_0_0_1px_rgba(139,92,246,0.18)] dark:border-violet-500/60 dark:bg-violet-500/15'
                        : 'border-slate-200 bg-white hover:border-violet-200 hover:bg-violet-50/40 dark:border-slate-700 dark:bg-slate-900 dark:hover:border-violet-500/50 dark:hover:bg-violet-500/10',
                    )}
                  >
                    <span className="flex items-center justify-between gap-3">
                      {avatarUrl ? (
                        <img src={avatarUrl} alt="" className="h-11 w-11 rounded-full object-cover" />
                      ) : (
                        <span className="flex h-11 w-11 items-center justify-center rounded-full bg-teal-50 text-base font-black text-teal-700 dark:bg-teal-500/15 dark:text-teal-200">
                          {firstLetter(character.name)}
                        </span>
                      )}
                      <span className={cn('h-5 w-5 rounded-full border-2', selected ? 'border-[6px] border-violet-600' : 'border-slate-300 dark:border-slate-600')} />
                    </span>
                    <span className="min-w-0">
                      <strong className="block truncate text-base font-black text-slate-950 dark:text-slate-100">{character.name}</strong>
                      <span className="mt-1 line-clamp-3 block text-sm font-semibold leading-6 text-slate-500 dark:text-slate-300">
                        {characterSummary(character)}
                      </span>
                    </span>
                    <span className={cn('w-fit rounded-full px-2.5 py-1 text-xs font-black', current ? 'bg-teal-100 text-teal-700 dark:bg-teal-500/15 dark:text-teal-200' : 'bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-300')}>
                      {current ? '当前绑定' : '可选择'}
                    </span>
                  </button>
                )
              })}
            </div>
          ) : (
            <section className="rounded-lg border border-dashed border-slate-300 bg-slate-50 px-5 py-12 text-center dark:border-slate-700 dark:bg-slate-900">
              <h3 className="text-lg font-black text-slate-950 dark:text-slate-100">当前故事还没有可扮演角色</h3>
              <p className="mt-2 text-sm font-semibold leading-6 text-slate-500 dark:text-slate-300">
                请先到角色库创建角色，并将角色挂载到当前故事。绑定完成前本会话不能发送消息。
              </p>
            </section>
          )}
        </div>

        <footer className="flex items-center justify-between gap-3 border-t border-slate-200 bg-slate-50 px-6 py-4 dark:border-slate-800 dark:bg-slate-900">
          <p className="text-xs font-semibold text-slate-400 dark:text-slate-300">
            {required ? '必须选择角色后才能开始。' : '切换只影响后续消息。'}
          </p>
          <div className="flex items-center gap-2">
            {!required ? (
              <button
                type="button"
                onClick={onClose}
                className="h-10 rounded-lg border border-slate-200 bg-white px-4 text-sm font-black text-slate-700 transition hover:border-violet-200 hover:text-violet-700 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-300 dark:hover:border-violet-500/60 dark:hover:text-violet-200"
              >
                取消
              </button>
            ) : null}
            <button
              type="button"
              onClick={onSubmit}
              disabled={!canSubmit}
              className="h-10 rounded-lg bg-violet-600 px-4 text-sm font-black text-white shadow-lg shadow-violet-100 transition hover:bg-violet-700 disabled:cursor-not-allowed disabled:bg-slate-300 disabled:shadow-none dark:shadow-violet-950/40 dark:disabled:bg-slate-700"
            >
              {pending ? '绑定中...' : required ? '确认角色' : '切换角色'}
            </button>
          </div>
        </footer>
      </section>
    </div>
  )
}

export function SessionRoom({ sessionId }: { sessionId: string }) {
  const router = useRouter()
  const logger = useMemo(() => createSessionRoomLogger(sessionId), [sessionId])
  const [inputMode, setInputMode] = useState<SessionInputMode>('ic')
  const [narrativeStyleId, setNarrativeStyleId] = useState<NarrativeStyleId>('default')
  const [composerText, setComposerText] = useState('')
  const [confirmRequest, setConfirmRequest] = useState<ConfirmRequest | null>(null)
  const [toastMessage, setToastMessage] = useState('')
  const [narrativeOutcomeDialogOpen, setNarrativeOutcomeDialogOpen] = useState(false)
  const toastTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const showToast = useCallback((message: string) => {
    setToastMessage(message)
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current)
    toastTimerRef.current = setTimeout(() => setToastMessage(''), 2200)
  }, [])

  useEffect(() => {
    setComposerText('')
    logger.info('session room entered', { status: 'session_changed' })
  }, [logger, sessionId])

  useEffect(() => {
    return () => {
      if (toastTimerRef.current) clearTimeout(toastTimerRef.current)
    }
  }, [])

  const layout = useSessionRoomLayout({ sessionId, logger })
  const data = useSessionRoomData({ sessionId, showToast, logger })
  const requestConfirm = useCallback((request: ConfirmRequest) => {
    setConfirmRequest(request)
  }, [])
  const role = useSessionRoleBinding({
    sessionId,
    session: data.session,
    characters: data.characters,
    playerCharacter: data.playerCharacter,
    refreshSessionData: data.refreshSessionData,
    requestConfirm,
    showToast,
    logger,
    closeSettings: () => layout.setSettingsOpen(false),
  })

  const currentNarrativeStyle = narrativeStyles.find((style) => style.id === narrativeStyleId) ?? narrativeStyles[0]
  const roleSelectionBlocked = !data.session || data.playerCharacterInvalid || role.bindingRole
  const contextPreviewUsage = roleSelectionBlocked ? null : data.contextPreviewUsage
  const contextInputBlocked = !roleSelectionBlocked && isContextInputBlocked(
    contextPreviewUsage,
    sessionContextUsageConfig.inputBlockThresholdRatio,
  )

  const mainLLM = useSessionMainLLM({
    sessionId,
    enabled: Boolean(data.session),
    showToast,
    logger,
  })

  const handleComposerTextChange = useCallback((value: string) => {
    setComposerText(value)
  }, [])

  const stream = useSessionStreamTurn({
    sessionId,
    inputMode,
    contextPreviewUsage: data.contextPreviewUsage,
    setLastTurnUsage: data.setLastTurnUsage,
    setLocalTurnUsageByTurn: data.setLocalTurnUsageByTurn,
    setComposerText,
    setLocalMessages: data.setLocalMessages,
    setForceScrollKey: data.setForceScrollKey,
    refreshSessionData: data.refreshSessionData,
    refreshContextPreview: data.refreshContextPreview,
    showToast,
    logger,
    onExit: () => router.push('/sessions'),
  })

  const timelineActions = useSessionTimelineActions({
    sessionId,
    session: data.session,
    playerCharacter: data.playerCharacter,
    playerCharacterInvalid: data.playerCharacterInvalid,
    inputMode,
    currentNarrativeStyle,
    composerText,
    contextInputBlockThresholdRatio: sessionContextUsageConfig.inputBlockThresholdRatio,
    refreshContextPreview: data.refreshContextPreview,
    timelineResetKey: data.timelineResetKey,
    lastTurnId: data.lastTurnId,
    lastPersistedTurnId: data.lastPersistedTurnId,
    sending: stream.sending,
    stopping: stream.stopping,
    streamLocalTurn: stream.streamLocalTurn,
    setOptimisticTruncateFromTurn: data.setOptimisticTruncateFromTurn,
    jumpToLatestHistoryBottom: data.jumpToLatestHistoryBottom,
    refreshSessionData: data.refreshSessionData,
    requestConfirm,
    requireRoleSelection: role.requireRoleSelection,
    showToast,
    logger,
  })

  const handleConfirm = () => {
    const action = confirmRequest?.onConfirm
    setConfirmRequest(null)
    action?.()
  }

  return (
    <main
      style={layout.gridStyle}
      data-workspace={data.session?.workspace ?? ''}
      data-story-id={data.session?.storyId ?? ''}
      data-session-id={sessionId}
      className="min-h-screen bg-[#f7f8fc] text-slate-900 dark:bg-[#0b1020] dark:text-slate-100 lg:grid lg:h-screen lg:min-h-0 lg:grid-cols-[var(--session-grid-columns)] lg:overflow-hidden"
    >
      {layout.mobilePanel ? (
        <button
          type="button"
          aria-label="关闭侧栏"
          onClick={() => layout.setMobilePanel(null)}
          className="fixed inset-0 z-30 bg-slate-950/20 backdrop-blur-[1px] dark:bg-slate-950/60 lg:hidden"
        />
      ) : null}

      <SessionLeftRail
        sessionId={sessionId}
        sceneTables={data.sceneTablesQuery.data ?? []}
        sceneTablesLoading={data.sceneTablesQuery.isLoading}
        normalTables={data.normalStatusTablesQuery.data ?? []}
        normalTablesLoading={data.normalStatusTablesQuery.isLoading}
        normalTablesReady={data.normalStatusTablesQuery.isSuccess}
        characters={data.characters}
        charactersLoading={data.charactersQuery.isLoading}
        scene={data.sceneQuery.data}
        playerCharacter={data.playerCharacter}
        collapsed={layout.leftCollapsed}
        mobileOpen={layout.mobilePanel === 'left'}
        activeDrawer={data.activeRailDrawer}
        onCloseMobile={() => layout.setMobilePanel(null)}
        onToggleCollapsed={layout.toggleLeftCollapsed}
        onOpenDrawer={data.setActiveRailDrawer}
        onCloseDrawer={() => data.setActiveRailDrawer(null)}
      />
      <button
        type="button"
        aria-label="调整左侧栏宽度"
        onPointerDown={layout.startDrag('left')}
        disabled={layout.leftCollapsed}
        className="group hidden cursor-col-resize bg-slate-100 transition hover:bg-violet-50 disabled:cursor-default disabled:opacity-40 dark:bg-slate-800 dark:hover:bg-violet-500/10 lg:flex lg:h-screen lg:items-stretch lg:justify-center"
      >
        <span className="my-auto h-16 w-1 rounded-full bg-slate-300 transition group-hover:bg-violet-400 dark:bg-slate-600 dark:group-hover:bg-violet-400" />
      </button>

      <section
        style={layout.sessionExperienceStyle}
        className="flex min-h-screen min-w-0 flex-col lg:h-screen lg:min-h-0"
      >
        <header className="flex min-h-[73px] flex-wrap items-center justify-between gap-3 border-b border-slate-200 bg-white px-4 py-3 dark:border-slate-800 dark:bg-slate-950/90 sm:px-6">
          <div className="min-w-0">
            <h1 className="truncate text-lg font-black text-slate-950 dark:text-slate-100 sm:text-xl">{data.session?.title ?? '加载会话中'}</h1>
            <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs font-semibold text-slate-400 dark:text-slate-400">
              <span>
                story <code className="font-mono text-slate-600 dark:text-slate-300">#{data.session?.storyId ?? '-'}</code>
              </span>
              <span>
                session <code className="font-mono text-slate-600 dark:text-slate-300">{data.session?.id ?? sessionId}</code>
              </span>
              {data.session?.updatedAt ? <span>更新 {formatDateTime(data.session.updatedAt)}</span> : null}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => layout.setMobilePanel('left')}
              className="flex h-10 w-10 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-600 shadow-sm transition hover:border-violet-200 hover:bg-violet-50 hover:text-violet-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:border-violet-500/60 dark:hover:bg-violet-500/10 dark:hover:text-violet-200 lg:hidden"
              aria-label="打开场景与固定状态栏"
            >
              <AlignJustify size={18} />
            </button>
            <button
              type="button"
              onClick={() => layout.setMobilePanel('right')}
              className="flex h-10 w-10 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-600 shadow-sm transition hover:border-violet-200 hover:bg-violet-50 hover:text-violet-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:border-violet-500/60 dark:hover:bg-violet-500/10 dark:hover:text-violet-200 lg:hidden"
              aria-label="打开会话速览与故事归纳栏"
            >
              <TableProperties size={18} />
            </button>
            <ThemeSwitcher menuAlign="right" menuSide="bottom" triggerSize="compact" />
            <button
              type="button"
              onClick={stream.handleExitSession}
              className="flex h-10 items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 text-sm font-black text-slate-700 shadow-sm transition hover:border-violet-200 hover:bg-violet-50 hover:text-violet-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:border-violet-500/60 dark:hover:bg-violet-500/10 dark:hover:text-violet-200"
            >
              <LogOut size={16} />
              退出
            </button>
            <SessionSettingsMenu
              open={layout.settingsOpen}
              leftCollapsed={layout.leftCollapsed}
              rightCollapsed={layout.rightCollapsed}
              fontScale={layout.fontScale}
              showThinking={layout.showThinking}
              showTools={layout.showTools}
              playerCharacter={data.playerCharacter}
              onToggleOpen={() => layout.setSettingsOpen((current) => !current)}
              onToggleSide={(side) => {
                if (side === 'left') layout.toggleLeftCollapsed()
                else layout.toggleRightCollapsed()
              }}
              onFontScaleChange={layout.setFontScale}
              onResetFontScale={layout.resetFontScale}
              onShowThinkingChange={layout.setShowThinking}
              onShowToolsChange={layout.setShowTools}
              onOpenRoleDialog={role.openRoleDialog}
              onOpenNarrativeOutcomeDialog={() => {
                layout.setSettingsOpen(false)
                setNarrativeOutcomeDialogOpen(true)
              }}
            />
          </div>
        </header>

        <SessionTimeline
          sessionId={sessionId}
          messages={data.visibleMessages}
          showThinking={layout.showThinking}
          showTools={layout.showTools}
          historyPage={data.historyPage}
          loadingBefore={data.historyLoadingBefore}
          loadingAfter={data.historyLoadingAfter}
          showJumpToLatest={data.showJumpToLatestHistory}
          jumpingToLatest={data.jumpingToLatestHistory}
          onTopBoundaryVisible={data.loadPreviousHistoryPage}
          onBottomBoundaryVisible={data.loadNextHistoryPage}
          onJumpToLatest={data.jumpToLatestHistoryBottom}
          forceScrollKey={data.forceScrollKey}
          editingMessageId={timelineActions.editingMessageId}
          editDraft={timelineActions.editDraft}
          onEditDraftChange={timelineActions.setEditDraft}
          onCopy={timelineActions.handleCopy}
          onRetry={timelineActions.handleRetry}
          onEdit={timelineActions.handleStartEdit}
          onDelete={timelineActions.handleDelete}
          onEditCancel={timelineActions.cancelEdit}
          onEditSend={timelineActions.handleSendEdit}
        />

        <SessionComposer
          sessionId={sessionId}
          text={composerText}
          mode={inputMode}
          narrativeStyleId={narrativeStyleId}
          narrativeStyles={narrativeStyles}
          sending={stream.sending}
          disabled={roleSelectionBlocked}
          contextPreviewUsage={contextPreviewUsage}
          lastTurnUsage={data.lastTurnUsage}
          contextInputBlocked={contextInputBlocked}
          contextInputBlockThresholdRatio={sessionContextUsageConfig.inputBlockThresholdRatio}
          contextUsageLoading={data.contextPreviewQuery.isLoading || data.contextPreviewQuery.isFetching}
          mainLLMCatalog={mainLLM.catalog}
          mainLLMSelection={mainLLM.selection}
          mainLLMLoading={mainLLM.loading || mainLLM.fetching}
          mainLLMUpdating={mainLLM.updating}
          mainLLMError={mainLLM.error}
          stopping={stream.stopping}
          onTextChange={handleComposerTextChange}
          onModeChange={setInputMode}
          onNarrativeStyleChange={setNarrativeStyleId}
          onMainLLMChange={mainLLM.selectProvider}
          onSend={timelineActions.handleSend}
          onStop={() => {
            void stream.stopActiveStream()
          }}
        />
      </section>

      <button
        type="button"
        aria-label="调整右侧栏宽度"
        onPointerDown={layout.startDrag('right')}
        disabled={layout.rightCollapsed}
        className="group hidden cursor-col-resize bg-slate-100 transition hover:bg-violet-50 disabled:cursor-default disabled:opacity-40 lg:flex lg:h-screen lg:items-stretch lg:justify-center"
      >
        <span className="my-auto h-16 w-1 rounded-full bg-slate-300 transition group-hover:bg-violet-400" />
      </button>
      <SessionRightRail
        session={data.session}
        scene={data.sceneQuery.data}
        lastTurnId={data.lastTurnId}
        summaryIndex={data.summaryIndexQuery.data}
        summariesLoading={data.summaryIndexQuery.isLoading}
        summariesError={data.summaryIndexQuery.isError}
        summaryDetail={data.summaryDetailQuery.data}
        summaryDetailLoading={data.summaryDetailQuery.isLoading || data.summaryDetailQuery.isFetching}
        summaryDetailError={data.summaryDetailQuery.isError}
        collapsed={layout.rightCollapsed}
        mobileOpen={layout.mobilePanel === 'right'}
        activeDrawer={data.activeRailDrawer}
        onCloseMobile={() => layout.setMobilePanel(null)}
        onToggleCollapsed={layout.toggleRightCollapsed}
        onOpenDrawer={data.setActiveRailDrawer}
        onCloseDrawer={() => data.setActiveRailDrawer(null)}
      />

      {confirmRequest ? (
        <ConfirmDialog
          title={confirmRequest.title}
          heading={confirmRequest.heading}
          body={confirmRequest.body}
          confirmLabel={confirmRequest.confirmLabel}
          pending={false}
          onClose={() => setConfirmRequest(null)}
          onConfirm={handleConfirm}
        />
      ) : null}
      <PlayerCharacterDialog
        open={role.roleDialogOpen}
        required={role.roleDialogRequired}
        characters={data.characters}
        loading={data.charactersQuery.isLoading}
        currentPlayer={data.playerCharacter}
        selectedCharacterId={role.selectedRoleCharacterId}
        pending={role.bindingRole}
        error={role.roleBindError}
        onSelect={role.setSelectedRoleCharacterId}
        onSubmit={role.submitRoleDialog}
        onClose={role.closeRoleDialog}
      />
      <SessionNarrativeOutcomeDialog
        open={narrativeOutcomeDialogOpen}
        sessionId={sessionId}
        onClose={() => setNarrativeOutcomeDialogOpen(false)}
        showToast={showToast}
      />
      <Toast message={toastMessage} />
    </main>
  )
}
