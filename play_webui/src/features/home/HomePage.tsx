'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useMemo } from 'react'
import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertCircle,
  BookOpen,
  ChevronRight,
  Clock3,
  FilePlus2,
  Loader2,
  Play,
  Sparkles,
} from 'lucide-react'
import { AppShell, useAppShell } from '@/features/layout/AppShell'
import { createSession, listSessions } from '@/lib/api/sessions'
import { listStories } from '@/lib/api/stories'
import { cn } from '@/lib/utils/cn'
import type { SessionSummary } from '@/types/session'
import type { StoryComputedStatus, StorySummary } from '@/types/story'

type StoryHomeItem = StorySummary & {
  sessions: SessionSummary[]
  latestSession?: SessionSummary | null
  latestAt: number
  computedStatus: StoryComputedStatus
  sessionsError: string | null
}

type SessionHomeItem = SessionSummary & {
  storyTitle: string
  storySummary: string
  latestAt: number
  computedActivity: 'recent' | 'stale'
}

const RECENT_WINDOW_DAYS = 7
const RECENT_WINDOW_MS = RECENT_WINDOW_DAYS * 24 * 60 * 60 * 1000

const coverClasses = [
  'from-slate-900 via-slate-700 to-cyan-100',
  'from-teal-900 via-emerald-700 to-amber-100',
  'from-stone-900 via-amber-800 to-teal-100',
  'from-indigo-900 via-sky-700 to-slate-100',
  'from-zinc-900 via-stone-700 to-rose-100',
]

const statusMeta: Record<StoryComputedStatus, { label: string; badgeClass: string; dotClass: string }> = {
  live: {
    label: '进行中',
    badgeClass: 'bg-teal-100 text-teal-700',
    dotClass: 'bg-teal-500',
  },
  draft: {
    label: '未开始',
    badgeClass: 'bg-amber-100 text-amber-700',
    dotClass: 'bg-amber-500',
  },
}

const activityMeta: Record<SessionHomeItem['computedActivity'], { label: string; badgeClass: string; dotClass: string }> = {
  recent: {
    label: '最近活跃',
    badgeClass: 'bg-teal-100 text-teal-700',
    dotClass: 'bg-teal-500',
  },
  stale: {
    label: '较久未更新',
    badgeClass: 'bg-sky-100 text-sky-700',
    dotClass: 'bg-sky-500',
  },
}

function formatDate(value?: string | null) {
  if (!value) return '暂无'
  return value.replace('T', ' ').slice(0, 16)
}

function getTimestamp(value?: string | null) {
  if (!value) return 0
  const timestamp = new Date(value).getTime()
  return Number.isFinite(timestamp) ? timestamp : 0
}

function latestTimestamp(session: SessionSummary) {
  return Math.max(getTimestamp(session.updatedAt), getTimestamp(session.createdAt))
}

function toErrorMessage(reason: unknown) {
  return reason instanceof Error ? reason.message : '加载失败'
}

function pickCoverClass(value: string | number) {
  const source = String(value)
  const total = source.split('').reduce((sum, char) => sum + char.charCodeAt(0), 0)
  return coverClasses[total % coverClasses.length]
}

function toStoryHomeItem(
  story: StorySummary,
  sessions: SessionSummary[],
  sessionsError: string | null,
): StoryHomeItem {
  const sortedSessions = [...sessions].sort((first, second) => latestTimestamp(second) - latestTimestamp(first))
  const latestSession = sortedSessions[0] ?? null
  const latestAt = Math.max(
    getTimestamp(story.updatedAt),
    getTimestamp(story.createdAt),
    ...sortedSessions.map(latestTimestamp),
  )

  return {
    ...story,
    sessions: sortedSessions,
    latestSession,
    latestAt,
    computedStatus: sortedSessions.length ? 'live' : 'draft',
    sessionsError,
  }
}

function toSessionHomeItem(session: SessionSummary, story: StorySummary, now: number): SessionHomeItem {
  const latestAt = latestTimestamp(session)

  return {
    ...session,
    storyTitle: story.title,
    storySummary: story.summary ?? '',
    latestAt,
    computedActivity: latestAt && now - latestAt <= RECENT_WINDOW_MS ? 'recent' : 'stale',
  }
}

function StoryArtwork({ item }: { item: Pick<StoryHomeItem, 'id' | 'title'> }) {
  return (
    <div className={cn('relative h-28 overflow-hidden bg-gradient-to-br', pickCoverClass(item.id))}>
      <div className="absolute bottom-[-26px] left-6 h-24 w-28 rounded-t-full bg-white/15" />
      <div className="absolute bottom-0 left-24 h-24 w-9 rounded-t-full bg-white/60 shadow-[72px_24px_0_-8px_rgba(255,255,255,0.36)]" />
      <div className="absolute inset-x-0 bottom-0 h-16 bg-gradient-to-t from-slate-950/45 to-transparent" />
      <span className="absolute bottom-3 right-3 max-w-[9rem] truncate text-xs font-extrabold text-white/90 drop-shadow">
        story #{item.id}
      </span>
    </div>
  )
}

function SessionArtwork({ item }: { item: Pick<SessionHomeItem, 'id' | 'storyId'> }) {
  return (
    <div className={cn('relative h-14 w-20 shrink-0 overflow-hidden rounded-lg bg-gradient-to-br', pickCoverClass(`${item.storyId}-${item.id}`))}>
      <div className="absolute bottom-[-14px] left-3 h-11 w-14 rounded-t-full bg-white/15" />
      <div className="absolute bottom-0 left-10 h-12 w-5 rounded-t-full bg-white/55 shadow-[32px_11px_0_-6px_rgba(255,255,255,0.28)]" />
      <div className="absolute inset-x-0 bottom-0 h-8 bg-gradient-to-t from-slate-950/35 to-transparent" />
    </div>
  )
}

function StoryStatusBadge({ status }: { status: StoryComputedStatus }) {
  const meta = statusMeta[status]

  return (
    <span className={cn('inline-flex h-7 items-center gap-2 rounded-full px-3 text-xs font-black', meta.badgeClass)}>
      <span className={cn('h-2 w-2 rounded-full', meta.dotClass)} />
      {meta.label}
    </span>
  )
}

function ActivityBadge({ activity }: { activity: SessionHomeItem['computedActivity'] }) {
  const meta = activityMeta[activity]

  return (
    <span className={cn('inline-flex h-7 items-center gap-2 rounded-full px-3 text-xs font-black', meta.badgeClass)}>
      <span className={cn('h-2 w-2 rounded-full', meta.dotClass)} />
      {meta.label}
    </span>
  )
}

function MetricCard({
  label,
  value,
  note,
  icon: Icon,
}: {
  label: string
  value: number
  note: string
  icon: typeof BookOpen
}) {
  return (
    <section className="min-h-24 rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-center justify-between gap-3 text-xs font-black uppercase text-slate-500">
        <span>{label}</span>
        <Icon size={18} className="text-slate-400" />
      </div>
      <p className="mt-3 text-3xl font-black leading-none text-slate-950">{value}</p>
      <p className="mt-2 text-xs font-semibold text-slate-400">{note}</p>
    </section>
  )
}

function StoryCard({
  item,
  sessionPending,
  onPlay,
}: {
  item: StoryHomeItem
  sessionPending: boolean
  onPlay: () => void
}) {
  const actionLabel = item.latestSession ? '继续' : '开局'

  return (
    <article className="overflow-hidden rounded-lg border border-slate-200 bg-white text-left shadow-sm transition hover:-translate-y-0.5 hover:border-teal-300 hover:shadow-lg">
      <StoryArtwork item={item} />
      <div className="p-4">
        <div className="mb-3 flex items-center justify-between gap-3">
          <StoryStatusBadge status={item.computedStatus} />
          <span className="truncate text-xs font-black text-slate-400">更新 {formatDate(item.latestSession?.updatedAt ?? item.updatedAt ?? item.createdAt)}</span>
        </div>
        <h2 className="truncate text-lg font-black text-slate-950">{item.title}</h2>
        <p className="mt-2 line-clamp-2 min-h-11 text-sm leading-6 text-slate-500">{item.summary || '暂无故事摘要'}</p>

        <div className="mt-4 grid grid-cols-2 gap-2">
          <div className="min-w-0 rounded-lg bg-slate-50 px-3 py-2">
            <b className="block text-base leading-none text-slate-950">{item.sessions.length}</b>
            <span className="mt-1 block truncate text-xs font-bold text-slate-500">会话</span>
          </div>
          <div className="min-w-0 rounded-lg bg-slate-50 px-3 py-2">
            <b className="block truncate text-sm text-slate-950">{item.latestSession?.title || item.latestSession?.id || '暂无'}</b>
            <span className="mt-1 block truncate text-xs font-bold text-slate-500">最近会话</span>
          </div>
        </div>

        {item.sessionsError ? (
          <p className="mt-3 flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-semibold text-amber-700">
            <AlertCircle size={14} />
            会话加载失败
          </p>
        ) : null}

        <div className="mt-4 flex items-center justify-between gap-3 border-t border-slate-200 pt-3">
          <Link href={`/stories/${item.id}/edit`} className="text-xs font-black text-slate-500 transition hover:text-teal-700">
            编辑故事
          </Link>
          <button
            type="button"
            disabled={sessionPending}
            onClick={onPlay}
            className="inline-flex h-9 items-center gap-2 rounded-lg bg-slate-950 px-3 text-sm font-black text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {sessionPending ? <Loader2 size={15} className="animate-spin" /> : <Play size={15} />}
            {actionLabel}
          </button>
        </div>
      </div>
    </article>
  )
}

function SessionRow({ item, onEnter }: { item: SessionHomeItem; onEnter: () => void }) {
  return (
    <article className="grid gap-3 rounded-lg border border-slate-200 bg-white px-4 py-3 shadow-sm transition hover:border-violet-300 hover:shadow-md md:grid-cols-[auto_minmax(0,1fr)_minmax(150px,0.45fr)_auto] md:items-center">
      <div className="flex min-w-0 items-center gap-3">
        <SessionArtwork item={item} />
        <div className="min-w-0">
          <Link href={`/session/${item.id}`} className="block truncate text-sm font-black text-slate-950 hover:text-violet-700">
            {item.title || item.id}
          </Link>
          <p className="mt-1 truncate text-xs font-semibold text-slate-400">{item.id} · 更新 {formatDate(item.updatedAt ?? item.createdAt)}</p>
        </div>
      </div>
      <p className="line-clamp-2 text-sm leading-6 text-slate-500 md:line-clamp-1">{item.description || item.storySummary || '暂无描述'}</p>
      <div className="min-w-0">
        <p className="truncate text-sm font-black text-slate-950">{item.storyTitle}</p>
        <p className="mt-1 truncate text-xs font-semibold text-slate-400">story #{item.storyId}</p>
      </div>
      <div className="flex items-center justify-between gap-3 md:justify-end">
        <ActivityBadge activity={item.computedActivity} />
        <button
          type="button"
          onClick={onEnter}
          className="inline-flex h-9 items-center justify-center rounded-lg bg-violet-600 px-3 text-xs font-black text-white transition hover:bg-violet-700"
        >
          进入
        </button>
      </div>
    </article>
  )
}

function StorySkeleton() {
  return (
    <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
      <div className="h-28 animate-pulse bg-slate-200" />
      <div className="space-y-4 p-4">
        <div className="h-5 w-2/3 animate-pulse rounded bg-slate-200" />
        <div className="space-y-2">
          <div className="h-3 animate-pulse rounded bg-slate-100" />
          <div className="h-3 w-4/5 animate-pulse rounded bg-slate-100" />
        </div>
        <div className="grid grid-cols-2 gap-2">
          {[0, 1].map((item) => <div key={item} className="h-12 animate-pulse rounded-lg bg-slate-100" />)}
        </div>
      </div>
    </div>
  )
}

function SessionSkeleton() {
  return (
    <div className="h-24 animate-pulse rounded-lg border border-slate-200 bg-white shadow-sm" />
  )
}

function EmptyState({
  title,
  description,
  action,
}: {
  title: string
  description: string
  action?: React.ReactNode
}) {
  return (
    <section className="rounded-lg border border-dashed border-slate-300 bg-white/70 px-6 py-12 text-center">
      <Sparkles size={28} className="mx-auto text-violet-600" />
      <h2 className="mt-3 text-lg font-black text-slate-950">{title}</h2>
      <p className="mt-2 text-sm font-semibold text-slate-500">{description}</p>
      {action ? <div className="mt-5">{action}</div> : null}
    </section>
  )
}

function HomeContent() {
  const router = useRouter()
  const queryClient = useQueryClient()
  const { currentWorkspace } = useAppShell()
  const now = useMemo(() => Date.now(), [currentWorkspace])

  const storiesQuery = useQuery({
    queryKey: ['play-stories', currentWorkspace],
    queryFn: () => listStories(currentWorkspace ?? ''),
    enabled: Boolean(currentWorkspace),
  })
  const stories = useMemo(() => storiesQuery.data ?? [], [storiesQuery.data])

  const sessionQueries = useQueries({
    queries: stories.map((story) => ({
      queryKey: ['play-sessions', currentWorkspace, story.id],
      queryFn: () => listSessions(currentWorkspace ?? '', story.id),
      enabled: Boolean(currentWorkspace),
    })),
  })

  const storyItems = useMemo(() => stories
    .map((story, index) => toStoryHomeItem(
      story,
      sessionQueries[index]?.data ?? [],
      sessionQueries[index]?.isError ? toErrorMessage(sessionQueries[index]?.error) : null,
    ))
    .sort((first, second) => second.latestAt - first.latestAt),
  [sessionQueries, stories])

  const sessionItems = useMemo(() => storyItems
    .flatMap((story) => story.sessions.map((session) => toSessionHomeItem(session, story, now)))
    .sort((first, second) => second.latestAt - first.latestAt),
  [now, storyItems])

  const recentStories = storyItems.slice(0, 6)
  const recentSessions = sessionItems.slice(0, 6)
  const liveStoryCount = storyItems.filter((item) => item.computedStatus === 'live').length
  const recentSessionCount = sessionItems.filter((item) => item.computedActivity === 'recent').length
  const sessionErrors = storyItems.filter((item) => item.sessionsError)
  const sessionsLoading = sessionQueries.some((query) => query.isLoading)
  const initialLoading = storiesQuery.isLoading || (sessionsLoading && storyItems.length === 0)

  const createSessionMutation = useMutation({
    mutationFn: (story: StoryHomeItem) => {
      if (!currentWorkspace) throw new Error('workspace missing')
      return createSession(currentWorkspace, story.id, `${story.title} 新会话`)
    },
    onSuccess: (session, story) => {
      queryClient.invalidateQueries({ queryKey: ['play-sessions', currentWorkspace, story.id] })
      queryClient.invalidateQueries({ queryKey: ['play-story-library-aggregate', currentWorkspace, story.id] })
      router.push(`/session/${session.id}`)
    },
  })

  function playStory(story: StoryHomeItem) {
    if (story.latestSession) {
      router.push(`/session/${story.latestSession.id}`)
      return
    }
    createSessionMutation.mutate(story)
  }

  function enterSession(session: SessionHomeItem) {
    router.push(`/session/${session.id}`)
  }

  return (
    <div className="min-w-0 px-5 py-8 xl:px-7">
      <section className="mb-6 grid gap-4 xl:grid-cols-[minmax(0,1fr)_auto] xl:items-end">
        <div>
          <p className="mb-2 flex items-center gap-2 text-sm font-black text-slate-500">
            <span className="h-2.5 w-2.5 rounded-full bg-violet-500" />
            {currentWorkspace ?? '未选择 workspace'} / home
          </p>
          <h1 className="text-3xl font-black text-slate-950">首页</h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-500">
            按 story 聚合最近会话，保留故事库与会话中心一致的继续游玩入口。
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Link
            href="/stories"
            className="inline-flex h-10 items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 text-sm font-black text-slate-700 shadow-sm transition hover:border-teal-300 hover:text-teal-700"
          >
            <BookOpen size={16} />
            故事库
          </Link>
          <Link
            href="/sessions"
            className="inline-flex h-10 items-center gap-2 rounded-lg bg-violet-600 px-4 text-sm font-black text-white shadow-lg shadow-violet-100 transition hover:bg-violet-700"
          >
            <Clock3 size={16} />
            会话中心
          </Link>
        </div>
      </section>

      <section className="mb-6 grid gap-3 md:grid-cols-3" aria-label="首页概览">
        <MetricCard label="故事" value={storyItems.length} note={`${liveStoryCount} 个已有会话`} icon={BookOpen} />
        <MetricCard label="会话" value={sessionItems.length} note="按当前 workspace 聚合" icon={Clock3} />
        <MetricCard label="最近活跃" value={recentSessionCount} note={`${RECENT_WINDOW_DAYS} 天内有更新`} icon={Play} />
      </section>

      {!currentWorkspace ? (
        <EmptyState title="请选择 workspace" description="选择 workspace 后即可查看首页故事与会话。" />
      ) : storiesQuery.isError ? (
        <section className="rounded-lg border border-rose-200 bg-rose-50 px-6 py-6 text-sm font-semibold text-rose-700">
          故事加载失败：{toErrorMessage(storiesQuery.error)}
        </section>
      ) : initialLoading ? (
        <div className="grid gap-6">
          <section>
            <div className="mb-3 h-6 w-28 animate-pulse rounded bg-slate-200" />
            <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-3">
              {[0, 1, 2].map((item) => <StorySkeleton key={item} />)}
            </div>
          </section>
          <section>
            <div className="mb-3 h-6 w-28 animate-pulse rounded bg-slate-200" />
            <div className="grid gap-3">
              {[0, 1, 2].map((item) => <SessionSkeleton key={item} />)}
            </div>
          </section>
        </div>
      ) : stories.length === 0 ? (
        <EmptyState
          title="还没有故事"
          description="新建一个 story 后，首页会展示最近故事和关联会话。"
          action={(
            <Link
              href="/stories/new"
              className="inline-flex h-10 items-center gap-2 rounded-lg bg-slate-950 px-4 text-sm font-black text-white transition hover:bg-slate-800"
            >
              <FilePlus2 size={16} />
              新建故事
            </Link>
          )}
        />
      ) : (
        <div className="grid gap-6">
          {sessionErrors.length ? (
            <section className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm font-semibold text-amber-700">
              <span className="mr-2 inline-flex align-[-2px]"><AlertCircle size={16} /></span>
              部分 story 会话加载失败：{sessionErrors.map((item) => `${item.title}（${item.sessionsError}）`).join('；')}
            </section>
          ) : null}

          <section className="overflow-hidden rounded-lg border border-slate-200 bg-white/60 shadow-sm">
            <header className="flex items-start justify-between gap-4 border-b border-slate-200 bg-white px-5 py-4">
              <div>
                <h2 className="text-lg font-black text-slate-950">最近故事</h2>
                <p className="mt-1 text-sm leading-6 text-slate-500">与故事库一致，按故事更新时间和最近会话排序。</p>
              </div>
              <Link href="/stories" className="inline-flex h-9 shrink-0 items-center gap-1 rounded-lg border border-slate-200 bg-white px-3 text-xs font-black text-slate-700 transition hover:border-teal-300 hover:text-teal-700">
                查看全部
                <ChevronRight size={14} />
              </Link>
            </header>
            <div className="grid gap-4 p-4 md:grid-cols-2 2xl:grid-cols-3">
              {recentStories.map((item) => (
                <StoryCard
                  key={item.id}
                  item={item}
                  sessionPending={createSessionMutation.isPending && createSessionMutation.variables?.id === item.id}
                  onPlay={() => playStory(item)}
                />
              ))}
            </div>
          </section>

          <section className="overflow-hidden rounded-lg border border-slate-200 bg-white/60 shadow-sm">
            <header className="flex items-start justify-between gap-4 border-b border-slate-200 bg-white px-5 py-4">
              <div>
                <h2 className="text-lg font-black text-slate-950">最近会话</h2>
                <p className="mt-1 text-sm leading-6 text-slate-500">与会话中心一致，按全局 session_id 进入游玩。</p>
              </div>
              <Link href="/sessions" className="inline-flex h-9 shrink-0 items-center gap-1 rounded-lg border border-slate-200 bg-white px-3 text-xs font-black text-slate-700 transition hover:border-violet-300 hover:text-violet-700">
                查看全部
                <ChevronRight size={14} />
              </Link>
            </header>
            {sessionsLoading && recentSessions.length === 0 ? (
              <div className="grid gap-3 p-4">
                {[0, 1, 2].map((item) => <SessionSkeleton key={item} />)}
              </div>
            ) : recentSessions.length ? (
              <div className="grid gap-3 p-4">
                {recentSessions.map((item) => (
                  <SessionRow key={item.id} item={item} onEnter={() => enterSession(item)} />
                ))}
              </div>
            ) : (
              <div className="border-t border-dashed border-slate-200 px-6 py-12 text-center">
                <h2 className="text-lg font-black text-slate-950">还没有会话</h2>
                <p className="mt-2 text-sm font-semibold text-slate-500">从最近故事中选择“开局”即可创建第一个会话。</p>
              </div>
            )}
          </section>
        </div>
      )}
    </div>
  )
}

export function HomePage() {
  return (
    <AppShell>
      <HomeContent />
    </AppShell>
  )
}
