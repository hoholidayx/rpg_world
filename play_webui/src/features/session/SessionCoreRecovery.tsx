'use client'

import React from 'react'
import Link from 'next/link'
import { AlertTriangle, Loader2, RefreshCw } from 'lucide-react'

export type SessionCoreRecoveryState =
  | { kind: 'ready' }
  | { kind: 'loading'; source: 'session' | 'history' }
  | { kind: 'error'; source: 'session' | 'history'; message: string }

type QueryState = {
  available: boolean
  error: unknown
  isError: boolean
}

function errorMessage(error: unknown, fallback: string) {
  return error instanceof Error && error.message.trim() ? error.message : fallback
}

export function resolveSessionCoreRecovery({
  session,
  history,
}: {
  session: QueryState
  history: QueryState
}): SessionCoreRecoveryState {
  if (!session.available) {
    return session.isError
      ? {
          kind: 'error',
          source: 'session',
          message: errorMessage(session.error, 'Session 暂时无法读取。'),
        }
      : { kind: 'loading', source: 'session' }
  }
  if (!history.available) {
    return history.isError
      ? {
          kind: 'error',
          source: 'history',
          message: errorMessage(history.error, '权威历史暂时无法读取。'),
        }
      : { kind: 'loading', source: 'history' }
  }
  return { kind: 'ready' }
}

export function SessionCoreRecovery({
  state,
  retrying,
  onRetry,
}: {
  state: Exclude<SessionCoreRecoveryState, { kind: 'ready' }>
  retrying: boolean
  onRetry: () => void
}) {
  const loading = state.kind === 'loading'
  const subject = state.source === 'session' ? 'Session' : '权威历史'

  return (
    <main className="flex min-h-screen items-center justify-center bg-[#f7f8fc] px-4 text-slate-900 dark:bg-[#0b1020] dark:text-slate-100">
      <section
        role={loading ? 'status' : 'alert'}
        className="w-full max-w-xl rounded-2xl border border-slate-200 bg-white px-6 py-10 text-center shadow-xl shadow-slate-200/60 dark:border-slate-800 dark:bg-slate-950 dark:shadow-black/30"
      >
        <span className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-violet-100 text-violet-700 dark:bg-violet-500/15 dark:text-violet-200">
          {loading || retrying
            ? <Loader2 size={25} className="animate-spin" />
            : <AlertTriangle size={25} />}
        </span>
        <h1 className="mt-5 text-xl font-black">
          {loading ? `正在读取${subject}` : `${subject}加载失败`}
        </h1>
        <p className="mt-3 text-sm font-semibold leading-6 text-slate-500 dark:text-slate-300">
          {loading
            ? '完成核心数据加载后即可继续游玩。'
            : state.message}
        </p>
        {!loading ? (
          <div className="mt-6 flex flex-wrap justify-center gap-3">
            <button
              type="button"
              disabled={retrying}
              onClick={onRetry}
              className="inline-flex h-11 items-center gap-2 rounded-xl bg-violet-600 px-5 text-sm font-black text-white transition hover:bg-violet-700 disabled:cursor-wait disabled:opacity-60"
            >
              <RefreshCw size={16} className={retrying ? 'animate-spin' : ''} />
              {retrying ? '正在重试' : '重试'}
            </button>
            <Link
              href="/sessions"
              className="inline-flex h-11 items-center rounded-xl border border-slate-200 bg-white px-5 text-sm font-black text-slate-600 transition hover:border-violet-300 hover:text-violet-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300"
            >
              返回会话中心
            </Link>
          </div>
        ) : null}
      </section>
    </main>
  )
}
