'use client'

import Link from 'next/link'
import { ArrowLeft, CloudMoon, ShieldCheck } from 'lucide-react'
import { AppShell } from '@/features/layout/AppShell'
import { DreamLedgerPanel } from './DreamLedgerPanel'
import { DreamProposalPanel } from './DreamProposalPanel'
import { DreamRunPanel } from './DreamRunPanel'
import { useDreamMemoryController } from './useDreamMemoryController'

function DreamMemoryContent({ sessionId }: { sessionId: string }) {
  const controller = useDreamMemoryController(sessionId)
  const session = controller.sessionQuery.data

  return (
    <div className="min-w-0 px-4 py-7 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-6xl">
        <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
          <div>
            <Link
              href={`/session/${encodeURIComponent(sessionId)}`}
              className="mb-3 inline-flex items-center gap-1 text-xs font-black text-slate-500 transition hover:text-violet-700 dark:text-slate-300 dark:hover:text-violet-200"
            >
              <ArrowLeft size={14} />返回会话
            </Link>
            <div className="flex items-center gap-3">
              <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-violet-100 text-violet-700 dark:bg-violet-500/15 dark:text-violet-200">
                <CloudMoon size={23} />
              </span>
              <div>
                <h1 className="text-2xl font-black text-slate-950 dark:text-slate-100">Dream Memory</h1>
                <p className="mt-1 text-sm font-semibold text-slate-500 dark:text-slate-300">
                  {session?.title ?? sessionId} · 审阅主 Agent 的长期世界内记忆
                </p>
              </div>
            </div>
          </div>
          <div className="inline-flex max-w-md items-start gap-2 rounded-xl border border-teal-200 bg-teal-50 px-4 py-3 text-xs font-bold leading-5 text-teal-800 dark:border-teal-500/30 dark:bg-teal-500/10 dark:text-teal-200">
            <ShieldCheck size={17} className="mt-0.5 shrink-0" />
            历史证据失效的记忆会立即停止注入 Context；重新 Dream 前不会污染后续对话。
          </div>
        </header>

        {controller.errorMessage ? (
          <div role="alert" className="mb-4 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-bold text-rose-700 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-200">
            {controller.errorMessage}
          </div>
        ) : null}
        {controller.notice ? (
          <div role="status" className="mb-4 rounded-xl border border-violet-200 bg-violet-50 px-4 py-3 text-sm font-bold text-violet-700 dark:border-violet-500/30 dark:bg-violet-500/10 dark:text-violet-200">
            {controller.notice}
          </div>
        ) : null}

        <div className="grid gap-5">
          <DreamRunPanel controller={controller} />
          <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1.45fr)_minmax(360px,1fr)]">
            <DreamProposalPanel controller={controller} />
            <DreamLedgerPanel controller={controller} />
          </div>
        </div>
      </div>
    </div>
  )
}

export function DreamMemoryPage({ sessionId }: { sessionId: string }) {
  return (
    <AppShell>
      <DreamMemoryContent sessionId={sessionId} />
    </AppShell>
  )
}
