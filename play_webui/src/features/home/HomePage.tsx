'use client'

import Link from 'next/link'
import { useQuery } from '@tanstack/react-query'
import { listSessions, listWorkspaces } from '@/lib/api/sessions'

export function HomePage() {
  const { data: workspaces = [] } = useQuery({ queryKey: ['play-workspaces'], queryFn: listWorkspaces })
  const workspace = workspaces[0]?.id ?? 'default'
  const { data: sessions = [] } = useQuery({ queryKey: ['play-sessions', workspace], queryFn: () => listSessions(workspace) })

  return (
    <main className="mx-auto flex min-h-screen max-w-5xl flex-col gap-8 px-6 py-12">
      <header>
        <p className="text-sm uppercase tracking-[0.3em] text-accent">RPG World Play</p>
        <h1 className="mt-3 text-4xl font-bold">继续你的互动叙事</h1>
        <p className="mt-4 max-w-2xl text-muted">Play WebUI 使用独立 Play API 契约，当前为脚手架 mock 数据。</p>
      </header>
      <section className="grid gap-4 md:grid-cols-2">
        {sessions.map((session) => (
          <Link
            key={session.id}
            href={`/session/${session.id}?workspace=${encodeURIComponent(session.workspace)}`}
            className="rounded-3xl border border-white/10 bg-white/5 p-6 transition hover:border-accent/60 hover:bg-white/10"
          >
            <h2 className="text-xl font-semibold">{session.title ?? session.id}</h2>
            <p className="mt-2 text-sm text-muted">工作区：{session.workspace}</p>
          </Link>
        ))}
      </section>
    </main>
  )
}
