'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { BookOpenText, Images, LogOut, UsersRound } from 'lucide-react'
import { ConfirmDialog } from '@/components/common/Dialog'
import { ThemeSwitcher } from '@/components/theme/ThemeSwitcher'
import { buildDreamPageHref } from '@/features/dream/dreamNavigation'
import { NotificationCenter } from '@/features/notifications/NotificationCenter'
import { sessionContextUsageConfig } from '@/lib/config/appConfig'
import { deleteSession } from '@/lib/api/sessions'
import { cn } from '@/lib/utils/cn'
import type { CharacterCard } from '@/types/characters'
import type { SessionOpeningOption, SessionPlayerCharacter } from '@/types/session'
import { SessionComposer } from './SessionComposer'
import { SessionDerivationDialog } from './SessionDerivationDialog'
import { SessionSettingsMenu } from './SessionSettingsMenu'
import { SessionMediaBackground } from './SessionMediaBackground'
import { SessionMediaGallery } from './SessionMediaGallery'
import { SessionRPModulesDialog } from './SessionRPModulesDialog'
import { SessionStatusHud } from './SessionStatusHud'
import { SessionStoryPanel, type SessionStoryTab } from './SessionStoryPanel'
import { SessionTimeline } from './SessionTimeline'
import { SessionWorldPanel, type SessionWorldTab } from './SessionWorldPanel'
import { useSessionRoomData } from './hooks/useSessionRoomData'
import { useSessionDerivation } from './hooks/useSessionDerivation'
import { useSessionRoomLayout } from './hooks/useSessionRoomLayout'
import { useSessionMainLLM } from './hooks/useSessionMainLLM'
import { useSessionMedia } from './hooks/useSessionMedia'
import { usePinnedStatusTables } from './hooks/usePinnedStatusTables'
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

type SessionWorkspaceState =
  | { kind: 'world'; tab: SessionWorldTab; focusTableId?: number }
  | { kind: 'story'; tab: SessionStoryTab }
  | null

function sortedStatusTables<T extends { sortOrder: number; id: number }>(tables: T[]) {
  return [...tables].sort((first, second) => (
    first.sortOrder - second.sortOrder || first.id - second.id
  ))
}

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
              {pending ? '处理中...' : required ? '继续' : '切换角色'}
            </button>
          </div>
        </footer>
      </section>
    </div>
  )
}

function SessionOpeningDialog({
  open,
  characterName,
  options,
  selectedOpeningId,
  pending,
  error,
  onSelect,
  onSubmit,
  onBack,
}: {
  open: boolean
  characterName: string
  options: SessionOpeningOption[]
  selectedOpeningId: number | null
  pending: boolean
  error: string | null
  onSelect: (openingId: number) => void
  onSubmit: () => void
  onBack: () => void
}) {
  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/50 px-4 py-8 backdrop-blur-sm">
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="session-opening-title"
        className="flex max-h-[calc(100vh-4rem)] w-full max-w-4xl flex-col overflow-hidden rounded-lg border border-slate-200 bg-white shadow-2xl shadow-slate-950/20 dark:border-slate-700 dark:bg-slate-950 dark:shadow-black/50"
      >
        <header className="border-b border-slate-200 bg-slate-50 px-6 py-5 dark:border-slate-800 dark:bg-slate-900">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-xs font-black uppercase tracking-[0.18em] text-violet-600 dark:text-violet-300">第 2 步 · 会话开局</p>
              <h2 id="session-opening-title" className="mt-1 text-xl font-black text-slate-950 dark:text-slate-100">
                选择故事的起点
              </h2>
              <p className="mt-1 text-sm font-semibold leading-6 text-slate-500 dark:text-slate-300">
                你将扮演「{characterName || '所选角色'}」。开局只决定本 Session 的第一条故事消息，之后仍是自由推演。
              </p>
            </div>
            <span className="rounded-full bg-violet-100 px-3 py-1.5 text-xs font-black text-violet-700 dark:bg-violet-500/15 dark:text-violet-200">
              {options.length} 个可选起点
            </span>
          </div>
        </header>

        <div className="overflow-y-auto px-6 py-5">
          {error ? (
            <p className="mb-4 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm font-bold text-rose-700 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-200">
              {error}
            </p>
          ) : null}
          <div className="grid gap-3">
            {options.map((option, index) => {
              const selected = selectedOpeningId === option.id
              return (
                <button
                  key={option.id}
                  type="button"
                  onClick={() => onSelect(option.id)}
                  disabled={pending}
                  className={cn(
                    'rounded-lg border p-4 text-left transition disabled:cursor-not-allowed disabled:opacity-70',
                    selected
                      ? 'border-violet-400 bg-violet-50 shadow-[inset_0_0_0_1px_rgba(139,92,246,0.16)] dark:border-violet-500/60 dark:bg-violet-500/15'
                      : 'border-slate-200 bg-white hover:border-violet-200 hover:bg-violet-50/40 dark:border-slate-700 dark:bg-slate-900 dark:hover:border-violet-500/50 dark:hover:bg-violet-500/10',
                  )}
                >
                  <span className="flex items-center justify-between gap-3">
                    <span className="min-w-0">
                      <span className="mr-2 text-xs font-black uppercase tracking-wider text-slate-400">Opening {index + 1}</span>
                      <strong className="text-base font-black text-slate-950 dark:text-slate-100">{option.title}</strong>
                    </span>
                    <span className={cn('h-5 w-5 shrink-0 rounded-full border-2', selected ? 'border-[6px] border-violet-600' : 'border-slate-300 dark:border-slate-600')} />
                  </span>
                  <span className="mt-3 block whitespace-pre-wrap text-sm font-semibold leading-7 text-slate-600 dark:text-slate-300">
                    {option.renderedMessage}
                  </span>
                </button>
              )
            })}
          </div>
        </div>

        <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 bg-slate-50 px-6 py-4 dark:border-slate-800 dark:bg-slate-900">
          <p className="text-xs font-semibold text-slate-400 dark:text-slate-300">
            未选择时默认使用第一条；确认后角色与开局会一起提交。
          </p>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onBack}
              disabled={pending}
              className="h-10 rounded-lg border border-slate-200 bg-white px-4 text-sm font-black text-slate-700 transition hover:border-violet-200 hover:text-violet-700 disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-300 dark:hover:border-violet-500/60 dark:hover:text-violet-200"
            >
              返回选择角色
            </button>
            <button
              type="button"
              onClick={onSubmit}
              disabled={!selectedOpeningId || pending}
              className="h-10 rounded-lg bg-violet-600 px-5 text-sm font-black text-white shadow-lg shadow-violet-100 transition hover:bg-violet-700 disabled:cursor-not-allowed disabled:bg-slate-300 disabled:shadow-none dark:shadow-violet-950/40 dark:disabled:bg-slate-700"
            >
              {pending ? '正在开始...' : '从这里开始'}
            </button>
          </div>
        </footer>
      </section>
    </div>
  )
}

export function SessionRoom({ sessionId }: { sessionId: string }) {
  const router = useRouter()
  const queryClient = useQueryClient()
  const logger = useMemo(() => createSessionRoomLogger(sessionId), [sessionId])
  const [inputMode, setInputMode] = useState<SessionInputMode>('ic')
  const [narrativeStyleId, setNarrativeStyleId] = useState<NarrativeStyleId>(null)
  const [composerText, setComposerText] = useState('')
  const [confirmRequest, setConfirmRequest] = useState<ConfirmRequest | null>(null)
  const [toastMessage, setToastMessage] = useState('')
  const [rpModulesDialogOpen, setRPModulesDialogOpen] = useState(false)
  const [mediaGalleryOpen, setMediaGalleryOpen] = useState(false)
  const [workspacePanel, setWorkspacePanel] = useState<SessionWorkspaceState>(null)
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [deleteRedirecting, setDeleteRedirecting] = useState(false)
  const toastTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const deleteRedirectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const showToast = useCallback((message: string) => {
    setToastMessage(message)
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current)
    toastTimerRef.current = setTimeout(() => setToastMessage(''), 2200)
  }, [])

  useEffect(() => {
    setComposerText('')
    setInputMode('ic')
    setNarrativeStyleId(null)
    setWorkspacePanel(null)
    logger.info('session room entered', { status: 'session_changed' })
  }, [logger, sessionId])

  useEffect(() => {
    return () => {
      if (toastTimerRef.current) clearTimeout(toastTimerRef.current)
      if (deleteRedirectTimerRef.current) clearTimeout(deleteRedirectTimerRef.current)
    }
  }, [])

  const layout = useSessionRoomLayout({ sessionId, logger })
  const data = useSessionRoomData({
    sessionId,
    inputMode,
    narrativeStyleId,
    showToast,
    logger,
  })
  const orderedNormalStatusTables = useMemo(
    () => sortedStatusTables(data.normalStatusTablesQuery.data ?? []),
    [data.normalStatusTablesQuery.data],
  )
  const pinnedStatus = usePinnedStatusTables({
    sessionId,
    tables: orderedNormalStatusTables,
    ready: data.normalStatusTablesQuery.isSuccess,
  })
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

  const composerConfig = data.composerQuery.data
  const baseStyle = composerConfig?.narrativeStyles.find((style) => style.isBase)
  const narrativeStyles = useMemo<NarrativeStyle[]>(() => [
    {
      id: null,
      label: baseStyle ? `故事默认 · ${baseStyle.name}` : '故事默认 · 无额外风格',
    },
    ...(composerConfig?.narrativeStyles ?? []).map((style) => ({
      id: style.narrativeStyleId,
      label: style.name,
    })),
  ], [baseStyle, composerConfig?.narrativeStyles])

  useEffect(() => {
    if (
      narrativeStyleId !== null
      && composerConfig
      && !composerConfig.narrativeStyles.some((style) => style.narrativeStyleId === narrativeStyleId)
    ) {
      setNarrativeStyleId(null)
    }
  }, [composerConfig, narrativeStyleId])
  const roleSelectionBlocked = (
    !data.session
    || data.playerCharacterInvalid
    || role.roleDialogRequired
    || role.openingDialogOpen
    || role.bindingRole
  )
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
  const media = useSessionMedia({
    sessionId,
    workspaceId: data.session?.workspace ?? null,
    storyId: data.session?.storyId ?? null,
    latestCommittedTurnId: data.lastPersistedTurnId,
    galleryOpen: mediaGalleryOpen,
    showToast,
  })
  const mediaBackground = media.backgroundQuery.data?.background ?? null
  const mediaBackgroundRevision = media.backgroundQuery.data?.revisionToken ?? 'none'
  const handleTurnCommitted = useCallback((turnId: number) => {
    media.requestBackgroundEvaluation(turnId, true)
    void queryClient.invalidateQueries({
      queryKey: ['play-session-story-memories', sessionId],
      refetchType: 'none',
    })
  }, [media.requestBackgroundEvaluation, queryClient, sessionId])

  const handleComposerTextChange = useCallback((value: string) => {
    setComposerText(value)
  }, [])

  const handleCommittedNarrativeStyle = useCallback((sentStyleId: NarrativeStyleId) => {
    setNarrativeStyleId((current) => current === sentStyleId ? null : current)
  }, [])

  const stream = useSessionStreamTurn({
    sessionId,
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
    onActiveSession: (activeSession) => {
      router.push(`/session/${encodeURIComponent(activeSession)}`)
    },
    onCommittedNarrativeStyle: handleCommittedNarrativeStyle,
    onTurnCommitted: handleTurnCommitted,
  })

  const deleteSessionMutation = useMutation({
    mutationFn: () => deleteSession(sessionId),
    onSuccess: (result) => {
      queryClient.removeQueries({ queryKey: ['play-session', sessionId] })
      queryClient.removeQueries({ queryKey: ['play-session-history-page', sessionId] })
      queryClient.removeQueries({ queryKey: ['play-session-history', sessionId] })
      queryClient.removeQueries({ queryKey: ['play-session-scene', sessionId] })
      queryClient.removeQueries({ queryKey: ['play-session-status-tables', sessionId] })
      queryClient.removeQueries({ queryKey: ['play-session-composer', sessionId] })
      queryClient.removeQueries({ queryKey: ['play-session-summaries', sessionId] })
      queryClient.removeQueries({ queryKey: ['play-session-summary', sessionId] })
      queryClient.removeQueries({ queryKey: ['play-session-story-memories', sessionId] })
      queryClient.removeQueries({ queryKey: ['play-session-context-preview', sessionId] })
      queryClient.removeQueries({ queryKey: ['session-main-llm', sessionId] })
      queryClient.removeQueries({ queryKey: ['session-rp-modules', sessionId] })
      queryClient.removeQueries({ queryKey: ['play-session-media-gallery', sessionId] })
      queryClient.removeQueries({ queryKey: ['play-session-media-background', sessionId] })
      queryClient.removeQueries({ queryKey: ['play-session-media-providers', sessionId] })
      queryClient.removeQueries({ queryKey: ['play-session-media-source-turns', sessionId] })
      queryClient.removeQueries({ queryKey: ['play-session-dream-proposal', sessionId] })
      queryClient.removeQueries({ queryKey: ['play-session-dream-proposals', sessionId] })
      queryClient.removeQueries({ queryKey: ['play-session-dream-memories', sessionId] })
      queryClient.removeQueries({ queryKey: ['play-session-dream-evidence-history', sessionId] })
      queryClient.invalidateQueries({ queryKey: ['play-sessions'] })
      if (result.runtimeCleanup === 'pending') {
        setDeleteRedirecting(true)
        showToast('会话已删除，运行目录仍待数据清理处理')
        deleteRedirectTimerRef.current = setTimeout(() => {
          router.replace('/sessions')
        }, 1200)
        return
      }
      setDeleteDialogOpen(false)
      router.replace('/sessions')
    },
  })

  const timelineActions = useSessionTimelineActions({
    sessionId,
    session: data.session,
    playerCharacter: data.playerCharacter,
    playerCharacterInvalid: data.playerCharacterInvalid,
    inputMode,
    narrativeStyleId,
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
  const derivation = useSessionDerivation({
    sessionId,
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
      data-workspace={data.session?.workspace ?? ''}
      data-story-id={data.session?.storyId ?? ''}
      data-session-id={sessionId}
      className="min-h-screen bg-[#f7f8fc] text-slate-900 dark:bg-[#0b1020] dark:text-slate-100 lg:h-screen lg:min-h-0 lg:overflow-hidden"
    >
      <section
        style={layout.sessionExperienceStyle}
        className="relative isolate flex min-h-screen min-w-0 flex-col overflow-hidden lg:h-screen lg:min-h-0"
      >
        <SessionMediaBackground
          sessionId={sessionId}
          background={mediaBackground}
          revisionToken={mediaBackgroundRevision}
        />
        <header className="relative z-20 flex min-h-[73px] flex-wrap items-center justify-between gap-3 border-b border-slate-200 bg-white/90 px-3 py-3 backdrop-blur-md dark:border-slate-800 dark:bg-slate-950/90 sm:px-5">
          <div className="flex min-w-0 w-full items-center gap-3 sm:w-auto sm:flex-1">
            <Link
              href="/"
              aria-label="返回 RPG World Play 首页"
              className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-violet-500 to-indigo-600 text-sm font-black text-white shadow-lg shadow-violet-200 transition hover:scale-105 dark:shadow-violet-950/40"
            >
              R
            </Link>
            <div className="min-w-0">
              <h1 className="truncate text-lg font-black text-slate-950 dark:text-slate-100 sm:text-xl">{data.session?.title ?? '加载会话中'}</h1>
              <div className="mt-1 hidden flex-wrap items-center gap-x-3 gap-y-1 text-xs font-semibold text-slate-400 dark:text-slate-400 sm:flex">
                <span>story <code className="font-mono text-slate-600 dark:text-slate-300">#{data.session?.storyId ?? '-'}</code></span>
                <span>session <code className="font-mono text-slate-600 dark:text-slate-300">{data.session?.id ?? sessionId}</code></span>
                {data.session?.updatedAt ? <span>更新 {formatDateTime(data.session.updatedAt)}</span> : null}
              </div>
            </div>
          </div>
          <div className="flex w-full max-w-full items-center gap-2 overflow-x-auto pb-0.5 sm:w-auto">
            <button
              type="button"
              onClick={() => {
                layout.setSettingsOpen(false)
                setWorkspacePanel({ kind: 'world', tab: 'characters' })
              }}
              className={cn(
                'flex h-10 shrink-0 items-center gap-2 rounded-lg border bg-white px-3 text-sm font-black shadow-sm transition dark:bg-slate-900',
                workspacePanel?.kind === 'world'
                  ? 'border-violet-300 bg-violet-50 text-violet-700 dark:border-violet-500/60 dark:bg-violet-500/15 dark:text-violet-200'
                  : 'border-slate-200 text-slate-700 hover:border-violet-200 hover:bg-violet-50 hover:text-violet-700 dark:border-slate-700 dark:text-slate-300',
              )}
              aria-label="打开角色与状态面板"
            >
              <UsersRound size={17} />
              <span className="hidden xl:inline">角色与状态</span>
            </button>
            <button
              type="button"
              onClick={() => {
                layout.setSettingsOpen(false)
                setWorkspacePanel({ kind: 'story', tab: 'summaries' })
              }}
              className={cn(
                'flex h-10 shrink-0 items-center gap-2 rounded-lg border bg-white px-3 text-sm font-black shadow-sm transition dark:bg-slate-900',
                workspacePanel?.kind === 'story'
                  ? 'border-indigo-300 bg-indigo-50 text-indigo-700 dark:border-indigo-500/60 dark:bg-indigo-500/15 dark:text-indigo-200'
                  : 'border-slate-200 text-slate-700 hover:border-indigo-200 hover:bg-indigo-50 hover:text-indigo-700 dark:border-slate-700 dark:text-slate-300',
              )}
              aria-label="打开故事与记忆面板"
            >
              <BookOpenText size={17} />
              <span className="hidden xl:inline">故事与记忆</span>
            </button>
            <ThemeSwitcher menuAlign="right" menuSide="bottom" triggerSize="compact" />
            <NotificationCenter />
            <button
              type="button"
              onClick={() => setMediaGalleryOpen(true)}
              className="flex h-10 shrink-0 items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 text-sm font-black text-slate-700 shadow-sm transition hover:border-violet-200 hover:bg-violet-50 hover:text-violet-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:border-violet-500/60 dark:hover:bg-violet-500/10 dark:hover:text-violet-200"
              aria-label="打开 Session 图像工作室"
            >
              <Images size={16} />
              <span className="hidden sm:inline">图像</span>
            </button>
            <button
              type="button"
              onClick={stream.handleExitSession}
              className="flex h-10 shrink-0 items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 text-sm font-black text-slate-700 shadow-sm transition hover:border-violet-200 hover:bg-violet-50 hover:text-violet-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:border-violet-500/60 dark:hover:bg-violet-500/10 dark:hover:text-violet-200"
              aria-label="退出当前会话"
            >
              <LogOut size={16} />
              <span className="hidden sm:inline">退出</span>
            </button>
            <SessionSettingsMenu
              open={layout.settingsOpen}
              fontScale={layout.fontScale}
              showThinking={layout.showThinking}
              showTools={layout.showTools}
              playerCharacter={data.playerCharacter}
              onToggleOpen={() => layout.setSettingsOpen((current) => !current)}
              onFontScaleChange={layout.setFontScale}
              onResetFontScale={layout.resetFontScale}
              onShowThinkingChange={layout.setShowThinking}
              onShowToolsChange={layout.setShowTools}
              onOpenRoleDialog={role.openRoleDialog}
              onOpenRPModulesDialog={() => {
                layout.setSettingsOpen(false)
                setRPModulesDialogOpen(true)
              }}
              onOpenDreamMemory={() => {
                layout.setSettingsOpen(false)
                const returnTo = `/session/${encodeURIComponent(sessionId)}`
                router.push(buildDreamPageHref(sessionId, returnTo))
              }}
              onDeleteSession={() => {
                layout.setSettingsOpen(false)
                deleteSessionMutation.reset()
                setDeleteRedirecting(false)
                setDeleteDialogOpen(true)
              }}
            />
          </div>
        </header>

        <SessionStatusHud
          sceneTables={data.sceneTablesQuery.data ?? []}
          pinnedTables={pinnedStatus.pinnedTables}
          panelOpen={workspacePanel !== null}
          onOpenStatusPanel={(tableId) => setWorkspacePanel({ kind: 'world', tab: 'status', focusTableId: tableId })}
        />

        <SessionTimeline
          sessionId={sessionId}
          messages={data.visibleMessages}
          showThinking={layout.showThinking}
          showTools={layout.showTools}
          backgroundActive={Boolean(mediaBackground)}
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
          onDerive={derivation.openDialog}
          onDelete={timelineActions.handleDelete}
          onEditCancel={timelineActions.cancelEdit}
          onEditSend={timelineActions.handleSendEdit}
        />

        <div className="relative z-10">
          <SessionComposer
            sessionId={sessionId}
            text={composerText}
            mode={inputMode}
            narrativeStyleId={narrativeStyleId}
            narrativeStyles={narrativeStyles}
            turnModes={composerConfig?.modes ?? []}
            quickReplies={composerConfig?.quickReplies ?? []}
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
            onQuickReply={timelineActions.handleQuickReply}
            onStop={() => {
              void stream.stopActiveStream()
            }}
          />
        </div>
      </section>

      <SessionWorldPanel
        open={workspacePanel?.kind === 'world'}
        activeTab={workspacePanel?.kind === 'world' ? workspacePanel.tab : 'characters'}
        focusTableId={workspacePanel?.kind === 'world' ? workspacePanel.focusTableId : undefined}
        sceneTables={data.sceneTablesQuery.data ?? []}
        sceneTablesLoading={data.sceneTablesQuery.isLoading}
        normalTables={orderedNormalStatusTables}
        normalTablesLoading={data.normalStatusTablesQuery.isLoading || !pinnedStatus.initialized}
        characters={data.characters}
        charactersLoading={data.charactersQuery.isLoading}
        scene={data.sceneQuery.data}
        playerCharacter={data.playerCharacter}
        pinnedIdSet={pinnedStatus.pinnedIdSet}
        onTogglePinned={pinnedStatus.togglePinned}
        onTabChange={(tab, focusTableId) => setWorkspacePanel({ kind: 'world', tab, focusTableId })}
        onClose={() => setWorkspacePanel(null)}
      />
      <SessionStoryPanel
        sessionId={sessionId}
        open={workspacePanel?.kind === 'story'}
        activeTab={workspacePanel?.kind === 'story' ? workspacePanel.tab : 'summaries'}
        onTabChange={(tab) => setWorkspacePanel({ kind: 'story', tab })}
        onClose={() => setWorkspacePanel(null)}
        onManageDream={() => {
          setWorkspacePanel(null)
          const returnTo = `/session/${encodeURIComponent(sessionId)}`
          router.push(buildDreamPageHref(sessionId, returnTo))
        }}
      />

      <SessionDerivationDialog
        open={derivation.open}
        sourceSessionId={sessionId}
        sourceTitle={data.session?.title ?? ''}
        turnId={derivation.turnId}
        title={derivation.title}
        pending={derivation.pending}
        error={derivation.error}
        onTitleChange={derivation.setTitle}
        onClose={derivation.closeDialog}
        onSubmit={derivation.submit}
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
      {deleteDialogOpen ? (
        <ConfirmDialog
          title="删除会话"
          heading={deleteRedirecting ? '会话已删除' : `永久删除“${data.session?.title || sessionId}”？`}
          body={(
            <div>
              <p>
                会话 <strong>{sessionId}</strong> 的主历史、冷备、角色绑定、状态表、剧情记忆、配置覆盖和全部运行文件都会永久删除，且无法恢复。
              </p>
              {deleteRedirecting ? (
                <p className="mt-3 font-bold text-rose-800">运行目录仍待清理，即将返回会话中心。</p>
              ) : null}
              {deleteSessionMutation.error ? (
                <p className="mt-3 font-bold text-rose-800">
                  删除失败：{deleteSessionMutation.error instanceof Error ? deleteSessionMutation.error.message : '未知错误'}
                </p>
              ) : null}
            </div>
          )}
          confirmLabel={deleteRedirecting ? '正在返回' : '永久删除'}
          pending={deleteSessionMutation.isPending || deleteRedirecting}
          onClose={() => {
            if (!deleteSessionMutation.isPending && !deleteRedirecting) setDeleteDialogOpen(false)
          }}
          onConfirm={() => {
            stream.prepareForSessionDeletion()
            deleteSessionMutation.mutate()
          }}
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
      <SessionOpeningDialog
        open={role.openingDialogOpen}
        characterName={data.characters.find((character) => character.id === role.pendingRoleCharacterId)?.name ?? ''}
        options={role.openingOptions}
        selectedOpeningId={role.selectedOpeningId}
        pending={role.bindingRole}
        error={role.roleBindError}
        onSelect={role.setSelectedOpeningId}
        onSubmit={role.submitOpeningDialog}
        onBack={role.backToRoleDialog}
      />
      <SessionRPModulesDialog
        open={rpModulesDialogOpen}
        sessionId={sessionId}
        onClose={() => setRPModulesDialogOpen(false)}
        showToast={showToast}
      />
      <SessionMediaGallery
        open={mediaGalleryOpen}
        sessionId={sessionId}
        media={media}
        onClose={() => setMediaGalleryOpen(false)}
      />
      <Toast message={toastMessage} />
    </main>
  )
}
