'use client'

import Link from 'next/link'
import { useQuery } from '@tanstack/react-query'
import { listSessions, listWorkspaces } from '@/lib/api/sessions'

export function HomePage() {
  const {
    data: workspaces = [],
    isLoading: workspacesLoading,
    error: workspacesError,
  } = useQuery({ queryKey: ['play-workspaces'], queryFn: listWorkspaces })
  const workspace = workspaces[0]?.id ?? 'default'
  const {
    data: sessions = [],
    isLoading: sessionsLoading,
    error: sessionsError,
  } = useQuery({ queryKey: ['play-sessions', workspace], queryFn: () => listSessions(workspace) })
  const loading = workspacesLoading || sessionsLoading
  const error = workspacesError ?? sessionsError

  return (
    <main className="mx-auto flex min-h-screen max-w-5xl flex-col gap-8 px-6 py-12">
      <header>
        <p className="text-sm uppercase tracking-[0.3em] text-accent">RPG World Play</p>
        <h1 className="mt-3 text-4xl font-bold">继续你的互动叙事</h1>
        <p className="mt-4 max-w-2xl text-muted">Play WebUI 使用独立 Play API 契约，当前加载演示工作区与 mock 会话。</p>
      </header>
      {loading ? (
        <section className="rounded-3xl border border-white/10 bg-white/5 p-6 text-muted">正在加载 Play API mock 数据...</section>
      ) : null}
      {error ? (
        <section className="rounded-3xl border border-red-400/30 bg-red-400/10 p-6 text-red-100">
          Play API 加载失败：{error instanceof Error ? error.message : '未知错误'}
        </section>
      ) : null}
      <section className="grid gap-4 md:grid-cols-2">
        {sessions.map((session) => (
          <Link
            key={session.id}
            href={`/session/${session.id}?workspace=${encodeURIComponent(session.workspace)}`}
            className="rounded-3xl border border-white/10 bg-white/5 p-6 transition hover:border-accent/60 hover:bg-white/10"
          >
            <h2 className="text-xl font-semibold">{session.title ?? session.id}</h2>
            <p className="mt-2 text-sm text-muted">{session.description ?? '演示会话'}</p>
            <p className="mt-4 text-xs uppercase tracking-[0.2em] text-accent/80">工作区：{session.workspace}</p>
          </Link>
        ))}
        {!loading && !error && sessions.length === 0 ? (
          <div className="rounded-3xl border border-dashed border-white/10 p-8 text-muted">暂无可继续的会话。</div>
        ) : null}
      </section>
    </main>
  )
}
