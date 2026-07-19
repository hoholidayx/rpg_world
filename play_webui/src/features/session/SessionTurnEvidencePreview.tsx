'use client'

import { useEffect, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, BookOpenText, RefreshCw, X } from 'lucide-react'
import { getSessionTurn } from '@/lib/api/sessions'
import { cn } from '@/lib/utils/cn'
import { HISTORY_MESSAGE_ROLE, type HistoryMessageRole } from '@/types/session'
import { formatDateTime } from './sessionRoomHelpers'

export type SessionEvidenceReference = {
  turnId: number
  messageId: number
}

const ROLE_LABELS: Record<HistoryMessageRole, string> = {
  [HISTORY_MESSAGE_ROLE.USER]: '玩家',
  [HISTORY_MESSAGE_ROLE.ASSISTANT]: '叙事者',
  [HISTORY_MESSAGE_ROLE.TOOL]: '工具',
  [HISTORY_MESSAGE_ROLE.SYSTEM]: '系统',
}

const ROLE_TONES: Record<HistoryMessageRole, string> = {
  [HISTORY_MESSAGE_ROLE.USER]: 'border-violet-200 bg-violet-50/80 dark:border-violet-500/30 dark:bg-violet-500/10',
  [HISTORY_MESSAGE_ROLE.ASSISTANT]: 'border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-900',
  [HISTORY_MESSAGE_ROLE.TOOL]: 'border-sky-200 bg-sky-50/80 dark:border-sky-500/30 dark:bg-sky-500/10',
  [HISTORY_MESSAGE_ROLE.SYSTEM]: 'border-slate-200 bg-slate-50 dark:border-slate-700 dark:bg-slate-800/80',
}

export function EvidenceReferenceButton({
  reference,
  onPreview,
}: {
  reference: SessionEvidenceReference
  onPreview: (reference: SessionEvidenceReference) => void
}) {
  return (
    <button
      type="button"
      onClick={() => onPreview(reference)}
      aria-label={`预览 Turn ${reference.turnId} 中的 Evidence 消息 ${reference.messageId}`}
      className="inline-flex min-h-8 items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 py-1 font-mono text-[11px] font-bold text-slate-600 transition hover:border-violet-300 hover:bg-violet-50 hover:text-violet-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:border-violet-500/60 dark:hover:bg-violet-500/10 dark:hover:text-violet-200"
    >
      <BookOpenText size={13} aria-hidden="true" />
      Turn {reference.turnId} · Msg {reference.messageId}
    </button>
  )
}

export function SessionTurnEvidencePreview({
  sessionId,
  reference,
  onClose,
}: {
  sessionId: string
  reference: SessionEvidenceReference
  onClose: () => void
}) {
  const closeButtonRef = useRef<HTMLButtonElement>(null)
  const returnFocusRef = useRef<HTMLElement | null>(null)
  const query = useQuery({
    queryKey: ['play-session-turn-preview', sessionId, reference.turnId],
    queryFn: () => getSessionTurn(sessionId, reference.turnId),
    retry: false,
    staleTime: 0,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  })

  useEffect(() => {
    returnFocusRef.current = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null
    closeButtonRef.current?.focus()

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
      event.preventDefault()
      event.stopImmediatePropagation()
      onClose()
    }
    document.addEventListener('keydown', handleKeyDown, true)
    return () => {
      document.removeEventListener('keydown', handleKeyDown, true)
      const target = returnFocusRef.current
      window.requestAnimationFrame(() => {
        if (target?.isConnected) target.focus()
      })
    }
  }, [onClose])

  const citedMessagePresent = Boolean(
    query.data?.messages.some((message) => message.messageId === reference.messageId),
  )

  return (
    <div
      className="fixed inset-0 z-[80] flex items-center justify-center bg-slate-950/20 p-3 backdrop-blur-[1px] sm:p-6"
      role="presentation"
      onMouseDown={(event) => {
        if (event.currentTarget === event.target) onClose()
      }}
    >
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="turn-evidence-preview-title"
        className="flex max-h-[min(760px,calc(100vh-32px))] w-full max-w-3xl flex-col overflow-hidden rounded-2xl border border-slate-200 bg-[#f7f8fc] shadow-2xl shadow-slate-950/30 dark:border-slate-700 dark:bg-[#0b1020] dark:shadow-black/70"
      >
        <header className="flex shrink-0 items-start justify-between gap-4 border-b border-slate-200 bg-white px-5 py-4 dark:border-slate-800 dark:bg-slate-950 sm:px-6">
          <div className="min-w-0">
            <span className="text-[10px] font-black uppercase tracking-[0.12em] text-violet-700 dark:text-violet-300">Evidence turn preview</span>
            <h2 id="turn-evidence-preview-title" className="mt-1 text-lg font-black text-slate-950 dark:text-slate-100">
              Turn {reference.turnId} 完整消息
            </h2>
            <p className="mt-1 text-xs font-semibold text-slate-500 dark:text-slate-300">
              引用目标 Msg {reference.messageId} · 只读预览，不改变当前时间线分页
            </p>
          </div>
          <button
            ref={closeButtonRef}
            type="button"
            onClick={onClose}
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-500 transition hover:border-violet-200 hover:bg-violet-50 hover:text-violet-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:border-violet-500/60 dark:hover:bg-violet-500/10 dark:hover:text-violet-200"
            aria-label="关闭 Turn 消息预览"
          >
            <X size={17} />
          </button>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-4 sm:p-6">
          {query.isLoading ? (
            <div className="flex min-h-56 flex-col items-center justify-center text-center">
              <RefreshCw size={22} className="animate-spin text-violet-600" />
              <p className="mt-3 text-sm font-bold text-slate-500 dark:text-slate-300">正在读取 Turn {reference.turnId}…</p>
            </div>
          ) : null}

          {query.isError ? (
            <div className="flex min-h-56 flex-col items-center justify-center rounded-2xl border border-dashed border-amber-300 bg-amber-50 px-6 text-center dark:border-amber-500/40 dark:bg-amber-500/10">
              <AlertTriangle size={24} className="text-amber-700 dark:text-amber-300" />
              <h3 className="mt-3 text-base font-black text-amber-900 dark:text-amber-100">无法读取该 Evidence 对应的 Turn</h3>
              <p className="mt-2 max-w-lg text-sm font-semibold leading-6 text-amber-800 dark:text-amber-200">
                该 Turn 可能已被删除或截断，也可能暂时无法从 Play API 读取。
              </p>
              <button type="button" onClick={() => { void query.refetch() }} className="mt-4 inline-flex h-10 items-center gap-2 rounded-xl bg-amber-700 px-4 text-xs font-black text-white transition hover:bg-amber-800">
                <RefreshCw size={14} /> 重新读取
              </button>
            </div>
          ) : null}

          {query.data ? (
            <div className="space-y-4">
              {!citedMessagePresent ? (
                <div className="flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm font-semibold leading-6 text-amber-800 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-200">
                  <AlertTriangle size={17} className="mt-0.5 shrink-0" />
                  Turn 仍然存在，但引用的 Msg {reference.messageId} 已不在当前主历史中。
                </div>
              ) : null}

              {query.data.messages.map((message) => {
                const cited = message.messageId === reference.messageId
                return (
                  <article
                    key={message.messageId || `${message.turnId}-${message.seqInTurn}`}
                    data-evidence-message-id={message.messageId}
                    className={cn(
                      'rounded-2xl border p-4 shadow-sm sm:p-5',
                      ROLE_TONES[message.role],
                      cited ? 'ring-2 ring-violet-400 ring-offset-2 ring-offset-[#f7f8fc] dark:ring-violet-500 dark:ring-offset-[#0b1020]' : '',
                    )}
                  >
                    <div className="flex flex-wrap items-center gap-2 text-[11px] font-bold text-slate-400">
                      <strong className="text-xs font-black text-slate-700 dark:text-slate-200">{ROLE_LABELS[message.role]}</strong>
                      <span>Seq {message.seqInTurn}</span>
                      <span>Msg {message.messageId}</span>
                      <span>{message.mode.toUpperCase()}</span>
                      {message.createdAt ? <span>{formatDateTime(message.createdAt)}</span> : null}
                      {cited ? <span className="ml-auto rounded-full bg-violet-600 px-2.5 py-1 text-[10px] font-black text-white">引用消息</span> : null}
                    </div>
                    <div className={cn(
                      'mt-3 whitespace-pre-wrap break-words text-sm font-semibold leading-7 text-slate-800 dark:text-slate-100',
                      message.role === HISTORY_MESSAGE_ROLE.TOOL ? 'font-mono text-xs' : '',
                    )}>
                      {message.content || '（空消息）'}
                    </div>
                  </article>
                )
              })}

              {query.data.outcome ? (
                <article className="rounded-2xl border border-teal-200 bg-teal-50 p-4 text-teal-900 dark:border-teal-500/30 dark:bg-teal-500/10 dark:text-teal-100 sm:p-5">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <strong className="text-sm font-black">剧情裁定 · {query.data.outcome.label}</strong>
                    {query.data.outcome.actor ? <span className="rounded-full bg-white/70 px-2.5 py-1 text-[10px] font-black dark:bg-slate-950/30">actor · {query.data.outcome.actor}</span> : null}
                  </div>
                  <p className="mt-2 whitespace-pre-wrap text-sm font-semibold leading-6">{query.data.outcome.reason}</p>
                </article>
              ) : null}
            </div>
          ) : null}
        </div>
      </section>
    </div>
  )
}
