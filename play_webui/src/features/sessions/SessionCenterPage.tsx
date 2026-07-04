'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertCircle,
  BookOpen,
  CalendarClock,
  CheckCircle2,
  Clock3,
  FilePlus2,
  FolderOpen,
  Loader2,
  Play,
  RefreshCw,
  Search,
  Sparkles,
} from 'lucide-react'
import { Dialog } from '@/components/common/Dialog'
import { AppShell, useAppShell } from '@/features/layout/AppShell'
import { getCurrentScene } from '@/lib/api/scene'
import { createSession, getSessionHistory, listSessions } from '@/lib/api/sessions'
import { listSessionStatusTables } from '@/lib/api/statusTables'
import { listStories } from '@/lib/api/stories'
import { cn } from '@/lib/utils/cn'
import type { Scene } from '@/types/scene'
import type { SessionSummary, Turn } from '@/types/session'
import type { StatusTable } from '@/types/statusTables'
import type { StorySummary } from '@/types/story'

type ActivityFilter = 'all' | 'recent' | 'stale'
type SortMode = 'active' | 'created' | 'title' | 'story'
type ComputedActivity = 'recent' | 'stale'

type StorySessionAggregate = {
  story: StorySummary
  sessions: SessionSummary[]
  error: string | null
}

type SessionCenterItem = SessionSummary & {
  storyTitle: string
  storySummary: string
  latestAt: number
  createdAtMs: number
  computedActivity: ComputedActivity
  searchText: string
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

const activityMeta: Record<ComputedActivity, { label: string; badgeClass: string; dotClass: string }> = {
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

function pickCoverClass(value: string | number) {
  const source = String(value)
  const total = source.split('').reduce((sum, char) => sum + char.charCodeAt(0), 0)
  return coverClasses[total % coverClasses.length]
}

function latestTimestamp(session: SessionSummary) {
  return Math.max(getTimestamp(session.updatedAt), getTimestamp(session.createdAt))
}

function isThisWeek(timestamp: number) {
  if (!timestamp) return false
  const now = new Date()
  const start = new Date(now)
  const dayOffset = (start.getDay() + 6) % 7
  start.setDate(start.getDate() - dayOffset)
  start.setHours(0, 0, 0, 0)
  return timestamp >= start.getTime()
}

function toErrorMessage(reason: unknown) {
  return reason instanceof Error ? reason.message : '加载失败'
}

function toSessionCenterItem(
  session: SessionSummary,
  story: StorySummary,
  now: number,
): SessionCenterItem {
  const latestAt = latestTimestamp(session)
  const createdAtMs = getTimestamp(session.createdAt)
  const computedActivity: ComputedActivity = latestAt && now - latestAt <= RECENT_WINDOW_MS ? 'recent' : 'stale'
  const storySummary = story.summary ?? ''
  const searchText = [
    session.id,
    session.title ?? '',
    session.description ?? '',
    story.title,
    storySummary,
  ].join(' ').toLowerCase()

  return {
    ...session,
    storyTitle: story.title,
    storySummary,
    latestAt,
    createdAtMs,
    computedActivity,
    searchText,
  }
}

function sceneSummary(scene?: Scene | null) {
  if (!scene) return '暂无场景数据'
  const parts = [
    scene.time ? `时间：${scene.time}` : '',
    scene.location ? `地点：${scene.location}` : '',
    scene.presentCharacters?.length ? `在场：${scene.presentCharacters.join('、')}` : '',
    scene.mood ? `氛围：${scene.mood}` : '',
  ].filter(Boolean)
  const attrs = Object.entries(scene.attrs ?? {})
    .filter(([, value]) => value)
    .slice(0, 4)
    .map(([key, value]) => `${key}：${value}`)

  return [...parts, ...attrs].join('；') || '暂无场景数据'
}

function latestTurnSummary(turns?: Turn[] | null) {
  const latest = turns?.[turns.length - 1]
  if (!latest) return '暂无回合记录'
  const latestMessage = [...latest.messages].reverse().find((message) => message.content.trim())
  return latestMessage?.content || '暂无回合记录'
}

function tableOriginSummary(tables?: StatusTable[] | null) {
  if (!tables?.length) return '暂无状态表'
  const templateCopy = tables.filter((table) => table.origin === 'template_copy').length
  const sessionNative = tables.filter((table) => table.origin === 'session_native').length
  const unknown = tables.length - templateCopy - sessionNative
  return [
    templateCopy ? `模板副本 ${templateCopy}` : '',
    sessionNative ? `会话新建 ${sessionNative}` : '',
    unknown ? `未知来源 ${unknown}` : '',
  ].filter(Boolean).join('，')
}

function Panel({
  title,
  description,
  action,
  children,
}: {
  title: string
  description?: string
  action?: ReactNode
  children: ReactNode
}) {
  return (
    <section className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
      <header className="flex items-start justify-between gap-4 border-b border-slate-200 bg-white px-5 py-4">
        <div className="min-w-0">
          <h2 className="text-lg font-black text-slate-950">{title}</h2>
          {description ? <p className="mt-1 text-sm leading-6 text-slate-500">{description}</p> : null}
        </div>
        {action}
      </header>
      {children}
    </section>
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

function SessionArtwork({ item, className = 'h-28' }: { item: Pick<SessionCenterItem, 'id' | 'storyId'>; className?: string }) {
  return (
    <div className={cn('relative overflow-hidden bg-gradient-to-br', pickCoverClass(`${item.storyId}-${item.id}`), className)}>
      <div className="absolute bottom-[-24px] left-5 h-20 w-24 rounded-t-full bg-white/15" />
      <div className="absolute bottom-0 left-20 h-20 w-8 rounded-t-full bg-white/60 shadow-[60px_20px_0_-8px_rgba(255,255,255,0.34),108px_16px_0_-10px_rgba(255,255,255,0.24)]" />
      <div className="absolute inset-x-0 bottom-0 h-14 bg-gradient-to-t from-slate-950/45 to-transparent" />
    </div>
  )
}

function ActivityBadge({ activity }: { activity: ComputedActivity }) {
  const meta = activityMeta[activity]
  return (
    <span className={cn('inline-flex h-7 items-center gap-2 rounded-full px-3 text-xs font-black', meta.badgeClass)}>
      <span className={cn('h-2 w-2 rounded-full', meta.dotClass)} />
      {meta.label}
    </span>
  )
}

function ContinueCard({
  item,
  selected,
  onSelect,
  onEnter,
}: {
  item: SessionCenterItem
  selected: boolean
  onSelect: () => void
  onEnter: () => void
}) {
  return (
    <article
      role="button"
      tabIndex={0}
      onClick={onSelect}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault()
          onSelect()
        }
      }}
      className={cn(
        'min-w-0 overflow-hidden rounded-lg border bg-white text-left shadow-sm transition hover:-translate-y-0.5 hover:border-violet-300 hover:shadow-lg',
        selected ? 'border-violet-500 shadow-[0_0_0_3px_rgba(124,58,237,0.12)]' : 'border-slate-200',
      )}
      aria-label={`选择会话 ${item.title || item.id}`}
    >
      <SessionArtwork item={item} />
      <div className="p-4">
        <div className="mb-3 flex items-center justify-between gap-2">
          <ActivityBadge activity={item.computedActivity} />
          <span className="truncate text-xs font-black text-slate-400">{item.id}</span>
        </div>
        <h3 className="truncate text-base font-black text-slate-950">{item.title || item.id}</h3>
        <p className="mt-2 line-clamp-2 min-h-10 text-sm leading-5 text-slate-500">{item.description || item.storySummary || '暂无会话描述'}</p>
        <div className="mt-4 grid grid-cols-2 gap-2">
          <div className="min-w-0 rounded-lg bg-slate-50 px-3 py-2">
            <b className="block truncate text-sm text-slate-950">{item.storyTitle}</b>
            <span className="mt-1 block text-xs font-bold text-slate-500">story</span>
          </div>
          <div className="min-w-0 rounded-lg bg-slate-50 px-3 py-2">
            <b className="block truncate text-sm text-slate-950">{formatDate(item.updatedAt ?? item.createdAt)}</b>
            <span className="mt-1 block text-xs font-bold text-slate-500">updated</span>
          </div>
        </div>
        <button
          type="button"
          onClick={(event) => {
            event.stopPropagation()
            onEnter()
          }}
          className="mt-4 inline-flex h-9 w-full items-center justify-center gap-2 rounded-lg bg-slate-950 px-3 text-sm font-black text-white transition hover:bg-slate-800"
        >
          <Play size={15} />
          进入会话
        </button>
      </div>
    </article>
  )
}

function SessionRow({
  item,
  selected,
  onSelect,
  onEnter,
}: {
  item: SessionCenterItem
  selected: boolean
  onSelect: () => void
  onEnter: () => void
}) {
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onSelect}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault()
          onSelect()
        }
      }}
      className={cn(
        'grid min-h-[72px] cursor-pointer grid-cols-[38px_minmax(0,1fr)_auto] items-center gap-3 border-t border-slate-200 bg-white px-4 py-3 text-left transition hover:bg-violet-50/30 lg:grid-cols-[38px_minmax(0,1.25fr)_minmax(150px,0.8fr)_minmax(140px,0.8fr)_124px_88px]',
        selected ? 'bg-violet-50/60' : '',
      )}
      aria-label={`选择会话 ${item.title || item.id}`}
    >
      <span className={cn('flex h-10 w-10 items-center justify-center rounded-lg text-sm font-black', item.computedActivity === 'recent' ? 'bg-teal-100 text-teal-700' : 'bg-sky-100 text-sky-700')}>
        S
      </span>
      <span className="min-w-0">
        <span className="block truncate text-sm font-black text-slate-950">{item.title || item.id}</span>
        <span className="mt-1 block truncate text-xs font-semibold text-slate-400">{item.id} · 更新 {formatDate(item.updatedAt ?? item.createdAt)}</span>
      </span>
      <span className="hidden min-w-0 lg:block">
        <span className="block truncate text-sm font-black text-slate-950">{item.storyTitle}</span>
        <span className="mt-1 block truncate text-xs font-semibold text-slate-400">story #{item.storyId}</span>
      </span>
      <span className="hidden min-w-0 lg:block">
        <span className="block truncate text-sm font-semibold text-slate-700">{item.description || item.storySummary || '暂无描述'}</span>
        <span className="mt-1 block truncate text-xs font-semibold text-slate-400">session profile</span>
      </span>
      <span className="hidden lg:block">
        <ActivityBadge activity={item.computedActivity} />
      </span>
      <button
        type="button"
        onClick={(event) => {
          event.stopPropagation()
          onEnter()
        }}
        className="inline-flex h-9 items-center justify-center rounded-lg bg-slate-950 px-3 text-xs font-black text-white transition hover:bg-slate-800"
      >
        进入
      </button>
    </div>
  )
}

function DetailField({ label, note, children }: { label: string; note: string; children: ReactNode }) {
  return (
    <section className="mt-4">
      <div className="mb-2 flex items-center justify-between gap-3 text-xs font-black uppercase text-slate-500">
        <span>{label}</span>
        <span>{note}</span>
      </div>
      <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-3 text-sm leading-6 text-slate-700">
        {children}
      </div>
    </section>
  )
}

function SessionInspector({
  item,
  scene,
  statusTables,
  turns,
  loading,
  errors,
  onEnter,
}: {
  item: SessionCenterItem | null
  scene?: Scene | null
  statusTables?: StatusTable[] | null
  turns?: Turn[] | null
  loading: boolean
  errors: string[]
  onEnter: () => void
}) {
  if (!item) {
    return (
      <aside className="overflow-hidden rounded-lg border border-dashed border-slate-300 bg-white/70 px-5 py-12 text-center text-sm font-semibold text-slate-500">
        选择一个会话查看详情
      </aside>
    )
  }

  const sceneCount = statusTables?.filter((table) => table.statusKind === 'scene').length ?? 0
  const normalCount = statusTables?.filter((table) => table.statusKind === 'normal').length ?? 0

  return (
    <aside className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-lg shadow-slate-200/70">
      <SessionArtwork item={item} className="h-28" />
      <div className="p-5">
        <div className="mb-3 flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="line-clamp-2 text-xl font-black leading-7 text-slate-950">{item.title || item.id}</h2>
            <p className="mt-1 truncate text-xs font-bold text-slate-400">{item.id} · {item.workspace} · story #{item.storyId}</p>
          </div>
          {loading ? <Loader2 size={18} className="mt-1 shrink-0 animate-spin text-slate-400" /> : null}
        </div>

        <ActivityBadge activity={item.computedActivity} />

        {errors.length ? (
          <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-semibold leading-5 text-amber-700">
            {errors.join(' / ')}
          </div>
        ) : null}

        <DetailField label="当前场景" note="scene">
          {sceneSummary(scene)}
        </DetailField>
        <DetailField label="最近回合" note={turns?.length ? `turn ${turns[turns.length - 1]?.turnId}` : 'turn'}>
          {latestTurnSummary(turns)}
        </DetailField>
        <DetailField label="运行状态" note="status tables">
          scene {sceneCount} 张，normal {normalCount} 张；{tableOriginSummary(statusTables)}
        </DetailField>
        <DetailField label="关联故事" note="story">
          {item.storyTitle}：{item.storySummary || '暂无故事摘要'}
        </DetailField>

        <button
          type="button"
          onClick={onEnter}
          className="mt-5 inline-flex h-10 w-full items-center justify-center gap-2 rounded-lg bg-violet-600 px-4 text-sm font-black text-white shadow-lg shadow-violet-100 transition hover:bg-violet-700"
        >
          <Play size={16} />
          进入会话
        </button>
      </div>
    </aside>
  )
}

function NewSessionDialog({
  stories,
  pending,
  error,
  selectedStoryId,
  title,
  onStoryChange,
  onTitleChange,
  onClose,
  onSubmit,
}: {
  stories: StorySummary[]
  pending: boolean
  error: string | null
  selectedStoryId: number | null
  title: string
  onStoryChange: (storyId: number) => void
  onTitleChange: (title: string) => void
  onClose: () => void
  onSubmit: () => void
}) {
  return (
    <Dialog title="新建会话" onClose={onClose} size="xl">
      {stories.length ? (
        <>
          <div className="space-y-4 px-6 py-5">
            <label className="block">
              <span className="mb-2 block text-xs font-black uppercase text-slate-500">story</span>
              <select
                value={selectedStoryId ?? ''}
                onChange={(event) => onStoryChange(Number(event.target.value))}
                className="h-11 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm font-bold text-slate-800 outline-none transition focus:border-violet-300 focus:ring-4 focus:ring-violet-100"
              >
                {stories.map((story) => (
                  <option key={story.id} value={story.id}>{story.title}</option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="mb-2 block text-xs font-black uppercase text-slate-500">title</span>
              <input
                value={title}
                onChange={(event) => onTitleChange(event.target.value)}
                placeholder="可选，会默认使用故事标题"
                className="h-11 w-full rounded-lg border border-slate-200 bg-slate-50 px-3 text-sm font-semibold text-slate-900 outline-none transition focus:border-violet-300 focus:ring-4 focus:ring-violet-100"
              />
            </label>
            {error ? <p className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm font-semibold text-rose-700">{error}</p> : null}
          </div>
          <footer className="flex items-center justify-end gap-2 border-t border-slate-200 bg-slate-50 px-6 py-4">
            <button
              type="button"
              onClick={onClose}
              className="h-10 rounded-lg border border-slate-200 bg-white px-4 text-sm font-black text-slate-700 transition hover:border-violet-200 hover:text-violet-700"
            >
              取消
            </button>
            <button
              type="button"
              onClick={onSubmit}
              disabled={pending || selectedStoryId === null}
              className="inline-flex h-10 items-center gap-2 rounded-lg bg-violet-600 px-4 text-sm font-black text-white transition hover:bg-violet-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {pending ? <Loader2 size={16} className="animate-spin" /> : <FilePlus2 size={16} />}
              创建并进入
            </button>
          </footer>
        </>
      ) : (
        <div className="px-6 py-8 text-center">
          <Sparkles size={28} className="mx-auto text-violet-600" />
          <h3 className="mt-3 text-lg font-black text-slate-950">还没有故事</h3>
          <p className="mt-2 text-sm font-semibold leading-6 text-slate-500">会话必须绑定 story。先创建故事后，再从会话中心开局。</p>
          <Link
            href="/stories/new"
            className="mt-5 inline-flex h-10 items-center gap-2 rounded-lg bg-slate-950 px-4 text-sm font-black text-white transition hover:bg-slate-800"
          >
            <FilePlus2 size={16} />
            新建故事
          </Link>
        </div>
      )}
    </Dialog>
  )
}

function SessionCenterContent() {
  const router = useRouter()
  const queryClient = useQueryClient()
  const { currentWorkspace } = useAppShell()
  const [search, setSearch] = useState('')
  const [activityFilter, setActivityFilter] = useState<ActivityFilter>('all')
  const [storyFilter, setStoryFilter] = useState('all')
  const [sortMode, setSortMode] = useState<SortMode>('active')
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null)
  const [createDialogOpen, setCreateDialogOpen] = useState(false)
  const [createStoryId, setCreateStoryId] = useState<number | null>(null)
  const [createTitle, setCreateTitle] = useState('')

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

  const aggregates = useMemo<StorySessionAggregate[]>(() => stories.map((story, index) => {
    const query = sessionQueries[index]
    return {
      story,
      sessions: query?.data ?? [],
      error: query?.isError ? toErrorMessage(query.error) : null,
    }
  }), [sessionQueries, stories])

  const allItems = useMemo(() => aggregates
    .flatMap((aggregate) => aggregate.sessions.map((session) => toSessionCenterItem(session, aggregate.story, now)))
    .sort((first, second) => second.latestAt - first.latestAt),
  [aggregates, now])

  const filteredItems = useMemo(() => {
    const query = search.trim().toLowerCase()
    return allItems
      .filter((item) => activityFilter === 'all' || item.computedActivity === activityFilter)
      .filter((item) => storyFilter === 'all' || String(item.storyId) === storyFilter)
      .filter((item) => !query || item.searchText.includes(query))
      .sort((first, second) => {
        if (sortMode === 'created') return second.createdAtMs - first.createdAtMs
        if (sortMode === 'title') return (first.title || first.id).localeCompare(second.title || second.id, 'zh-CN')
        if (sortMode === 'story') return first.storyTitle.localeCompare(second.storyTitle, 'zh-CN') || second.latestAt - first.latestAt
        return second.latestAt - first.latestAt
      })
  }, [activityFilter, allItems, search, sortMode, storyFilter])

  const selectedItem = useMemo(
    () => allItems.find((item) => item.id === selectedSessionId) ?? filteredItems[0] ?? allItems[0] ?? null,
    [allItems, filteredItems, selectedSessionId],
  )

  useEffect(() => {
    if (!selectedItem) {
      if (selectedSessionId !== null) setSelectedSessionId(null)
      return
    }
    if (selectedItem.id !== selectedSessionId) setSelectedSessionId(selectedItem.id)
  }, [selectedItem, selectedSessionId])

  const selectedSessionIdForQuery = selectedItem?.id ?? ''
  const sceneQuery = useQuery({
    queryKey: ['play-session-scene', selectedSessionIdForQuery],
    queryFn: () => getCurrentScene(selectedSessionIdForQuery),
    enabled: Boolean(selectedItem),
  })
  const statusTablesQuery = useQuery({
    queryKey: ['play-session-status-tables', selectedSessionIdForQuery],
    queryFn: () => listSessionStatusTables(selectedSessionIdForQuery),
    enabled: Boolean(selectedItem),
  })
  const historyQuery = useQuery({
    queryKey: ['play-session-history', selectedSessionIdForQuery],
    queryFn: () => getSessionHistory(selectedSessionIdForQuery),
    enabled: Boolean(selectedItem),
  })

  const createSessionMutation = useMutation({
    mutationFn: ({ storyId, title }: { storyId: number; title: string }) => {
      if (!currentWorkspace) throw new Error('workspace missing')
      return createSession(currentWorkspace, storyId, title)
    },
    onSuccess: (session, variables) => {
      queryClient.invalidateQueries({ queryKey: ['play-sessions', currentWorkspace] })
      queryClient.invalidateQueries({ queryKey: ['play-story-library-aggregate', currentWorkspace, variables.storyId] })
      setCreateDialogOpen(false)
      router.push(`/session/${session.id}`)
    },
  })

  const aggregatesLoading = sessionQueries.some((query) => query.isLoading)
  const initialSessionsLoading = aggregatesLoading && allItems.length === 0
  const aggregateErrors = aggregates.filter((aggregate) => aggregate.error)
  const recentCount = allItems.filter((item) => item.computedActivity === 'recent').length
  const storyCountWithSessions = new Set(allItems.map((item) => item.storyId)).size
  const createdThisWeek = allItems.filter((item) => isThisWeek(item.createdAtMs)).length
  const continueItems = allItems.slice(0, 3)
  const detailErrors = [
    sceneQuery.isError ? `场景加载失败：${toErrorMessage(sceneQuery.error)}` : '',
    statusTablesQuery.isError ? `状态表加载失败：${toErrorMessage(statusTablesQuery.error)}` : '',
    historyQuery.isError ? `历史加载失败：${toErrorMessage(historyQuery.error)}` : '',
  ].filter(Boolean)

  function enterSession(item: Pick<SessionCenterItem, 'id'> | null) {
    if (!item) return
    router.push(`/session/${item.id}`)
  }

  function openCreateDialog() {
    createSessionMutation.reset()
    const firstStory = stories[0]
    setCreateStoryId(firstStory?.id ?? null)
    setCreateTitle(firstStory ? `${firstStory.title} 新会话` : '')
    setCreateDialogOpen(true)
  }

  function changeCreateStory(storyId: number) {
    const story = stories.find((item) => item.id === storyId)
    setCreateStoryId(storyId)
    setCreateTitle(story ? `${story.title} 新会话` : '')
  }

  function submitCreateSession() {
    if (createStoryId === null) return
    const story = stories.find((item) => item.id === createStoryId)
    createSessionMutation.mutate({
      storyId: createStoryId,
      title: createTitle.trim() || (story ? `${story.title} 新会话` : ''),
    })
  }

  return (
    <div className="min-w-0 px-5 py-8 xl:px-7">
      <section className="mb-6 grid gap-4 xl:grid-cols-[minmax(0,1fr)_auto] xl:items-end">
        <div>
          <p className="mb-2 flex items-center gap-2 text-sm font-black text-slate-500">
            <span className="h-2.5 w-2.5 rounded-full bg-emerald-500" />
            {currentWorkspace ?? '未选择 workspace'} / session center
          </p>
          <h1 className="text-3xl font-black text-slate-950">会话中心</h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-500">
            从最近更新的 session 继续游玩，也可以按 story、更新时间和本地搜索检索完整会话列表；会话内链路只使用全局短 session_id。
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => {
              queryClient.invalidateQueries({ queryKey: ['play-stories', currentWorkspace] })
              queryClient.invalidateQueries({ queryKey: ['play-sessions', currentWorkspace] })
            }}
            disabled={!currentWorkspace}
            title="刷新"
            aria-label="刷新"
            className="flex h-10 w-10 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-500 shadow-sm transition hover:border-violet-300 hover:text-violet-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            <RefreshCw size={17} />
          </button>
          <button
            type="button"
            onClick={openCreateDialog}
            disabled={!currentWorkspace || storiesQuery.isLoading}
            className="inline-flex h-10 items-center gap-2 rounded-lg bg-violet-600 px-4 text-sm font-black text-white shadow-lg shadow-violet-100 transition hover:bg-violet-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            <FilePlus2 size={16} />
            新建会话
          </button>
        </div>
      </section>

      <section className="mb-5 grid gap-3 xl:grid-cols-[minmax(280px,1fr)_auto_auto_auto] xl:items-center" aria-label="筛选会话">
        <label className="flex h-11 items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-500 shadow-sm focus-within:border-violet-300 focus-within:ring-4 focus-within:ring-violet-100">
          <Search size={17} />
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="搜索 session_id、标题、描述、故事"
            className="min-w-0 flex-1 bg-transparent text-slate-900 outline-none placeholder:text-slate-400"
          />
        </label>
        <div className="inline-flex rounded-lg border border-slate-200 bg-white p-1 shadow-sm" role="tablist" aria-label="会话活跃度">
          {[
            ['all', '全部'],
            ['recent', '最近活跃'],
            ['stale', '较久未更新'],
          ].map(([value, label]) => (
            <button
              key={value}
              type="button"
              onClick={() => setActivityFilter(value as ActivityFilter)}
              className={cn(
                'h-8 rounded-md px-3 text-xs font-black transition',
                activityFilter === value ? 'bg-slate-950 text-white' : 'text-slate-500 hover:bg-slate-50 hover:text-slate-950',
              )}
            >
              {label}
            </button>
          ))}
        </div>
        <select
          value={storyFilter}
          onChange={(event) => setStoryFilter(event.target.value)}
          className="h-11 rounded-lg border border-slate-200 bg-white px-3 text-sm font-bold text-slate-700 shadow-sm outline-none transition focus:border-violet-300 focus:ring-4 focus:ring-violet-100"
          aria-label="故事筛选"
        >
          <option value="all">全部故事</option>
          {stories.map((story) => <option key={story.id} value={story.id}>{story.title}</option>)}
        </select>
        <select
          value={sortMode}
          onChange={(event) => setSortMode(event.target.value as SortMode)}
          className="h-11 rounded-lg border border-slate-200 bg-white px-3 text-sm font-bold text-slate-700 shadow-sm outline-none transition focus:border-violet-300 focus:ring-4 focus:ring-violet-100"
          aria-label="排序"
        >
          <option value="active">最近活跃优先</option>
          <option value="created">最近创建优先</option>
          <option value="title">会话标题 A-Z</option>
          <option value="story">故事标题 A-Z</option>
        </select>
      </section>

      <section className="mb-6 grid gap-3 md:grid-cols-2 2xl:grid-cols-4" aria-label="会话中心概览">
        <MetricCard label="全部会话" value={allItems.length} note="当前 workspace 聚合结果" icon={BookOpen} />
        <MetricCard label="最近活跃" value={recentCount} note={`${RECENT_WINDOW_DAYS} 天内有更新`} icon={Clock3} />
        <MetricCard label="关联故事" value={storyCountWithSessions} note={`${stories.length} 个 story 可筛选`} icon={FolderOpen} />
        <MetricCard label="本周新建" value={createdThisWeek} note="按 createdAt 统计" icon={CalendarClock} />
      </section>

      {!currentWorkspace ? (
        <section className="rounded-lg border border-dashed border-slate-300 bg-white/70 px-6 py-12 text-center text-sm font-semibold text-slate-500">
          请选择 workspace 后查看会话中心
        </section>
      ) : storiesQuery.isError ? (
        <section className="rounded-lg border border-rose-200 bg-rose-50 px-6 py-6 text-sm font-semibold text-rose-700">
          故事列表加载失败：{toErrorMessage(storiesQuery.error)}
        </section>
      ) : storiesQuery.isLoading ? (
        <section className="grid gap-4">
          {[0, 1, 2].map((item) => (
            <div key={item} className="h-28 animate-pulse rounded-lg border border-slate-200 bg-white shadow-sm" />
          ))}
        </section>
      ) : stories.length === 0 ? (
        <section className="rounded-lg border border-dashed border-slate-300 bg-white/70 px-6 py-12 text-center">
          <Sparkles size={28} className="mx-auto text-violet-600" />
          <h2 className="mt-3 text-lg font-black text-slate-950">还没有故事</h2>
          <p className="mt-2 text-sm font-semibold text-slate-500">会话必须绑定 story。先创建故事后，就可以从这里开局。</p>
          <Link
            href="/stories/new"
            className="mt-5 inline-flex h-10 items-center gap-2 rounded-lg bg-slate-950 px-4 text-sm font-black text-white transition hover:bg-slate-800"
          >
            <FilePlus2 size={16} />
            新建故事
          </Link>
        </section>
      ) : (
        <>
          {aggregatesLoading ? (
            <p className="mb-3 flex items-center gap-2 text-xs font-bold text-slate-400">
              <Loader2 size={14} className="animate-spin" />
              正在按 story 聚合会话
            </p>
          ) : null}
          {aggregateErrors.length ? (
            <section className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm font-semibold text-amber-700">
              <span className="mr-2 inline-flex align-[-2px]"><AlertCircle size={16} /></span>
              部分 story 会话加载失败：{aggregateErrors.map((item) => `${item.story.title}（${item.error}）`).join('；')}
            </section>
          ) : null}

          {initialSessionsLoading ? (
            <section className="grid gap-4">
              {[0, 1, 2].map((item) => (
                <div key={item} className="h-28 animate-pulse rounded-lg border border-slate-200 bg-white shadow-sm" />
              ))}
            </section>
          ) : allItems.length === 0 ? (
            <section className="rounded-lg border border-dashed border-slate-300 bg-white/70 px-6 py-12 text-center">
              <CheckCircle2 size={28} className="mx-auto text-violet-600" />
              <h2 className="mt-3 text-lg font-black text-slate-950">还没有会话</h2>
              <p className="mt-2 text-sm font-semibold text-slate-500">选择一个 story 创建新会话后，会自动进入 `/session/{'{session_id}'}`。</p>
              <button
                type="button"
                onClick={openCreateDialog}
                className="mt-5 inline-flex h-10 items-center gap-2 rounded-lg bg-violet-600 px-4 text-sm font-black text-white transition hover:bg-violet-700"
              >
                <FilePlus2 size={16} />
                新建会话
              </button>
            </section>
          ) : (
            <div className="grid gap-5">
              <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px] xl:items-stretch">
                <Panel
                  title="继续游玩"
                  description="最近高价值入口，按会话更新时间优先展示。"
                  action={(
                    <button
                      type="button"
                      onClick={() => queryClient.invalidateQueries({ queryKey: ['play-sessions', currentWorkspace] })}
                      className="inline-flex h-9 items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 text-xs font-black text-slate-700 transition hover:border-violet-300 hover:text-violet-700"
                    >
                      <RefreshCw size={14} />
                      刷新
                    </button>
                  )}
                >
                  <div className="grid gap-3 p-4 2xl:grid-cols-3">
                    {continueItems.map((item) => (
                      <ContinueCard
                        key={item.id}
                        item={item}
                        selected={item.id === selectedItem?.id}
                        onSelect={() => setSelectedSessionId(item.id)}
                        onEnter={() => enterSession(item)}
                      />
                    ))}
                  </div>
                </Panel>

                <SessionInspector
                  item={selectedItem}
                  scene={sceneQuery.data ?? null}
                  statusTables={statusTablesQuery.data ?? null}
                  turns={historyQuery.data ?? null}
                  loading={sceneQuery.isLoading || statusTablesQuery.isLoading || historyQuery.isLoading}
                  errors={detailErrors}
                  onEnter={() => enterSession(selectedItem)}
                />
              </div>

              <Panel
                title="完整会话列表"
                description="完整列表更适合管理和调试；筛选、排序和搜索都在前端本地完成。"
              >
                {filteredItems.length ? (
                  <div className="overflow-hidden">
                    <div className="hidden min-h-11 grid-cols-[38px_minmax(0,1.25fr)_minmax(150px,0.8fr)_minmax(140px,0.8fr)_124px_88px] items-center gap-3 bg-slate-50 px-4 text-xs font-black uppercase text-slate-500 lg:grid">
                      <span />
                      <span>会话</span>
                      <span>故事</span>
                      <span>描述</span>
                      <span>状态</span>
                      <span>操作</span>
                    </div>
                    {filteredItems.map((item) => (
                      <SessionRow
                        key={item.id}
                        item={item}
                        selected={item.id === selectedItem?.id}
                        onSelect={() => setSelectedSessionId(item.id)}
                        onEnter={() => enterSession(item)}
                      />
                    ))}
                  </div>
                ) : (
                  <section className="border-t border-dashed border-slate-200 px-6 py-12 text-center text-sm font-semibold text-slate-500">
                    没有匹配当前搜索和筛选的会话
                  </section>
                )}
              </Panel>
            </div>
          )}
        </>
      )}

      {createDialogOpen ? (
        <NewSessionDialog
          stories={stories}
          pending={createSessionMutation.isPending}
          error={createSessionMutation.error ? toErrorMessage(createSessionMutation.error) : null}
          selectedStoryId={createStoryId}
          title={createTitle}
          onStoryChange={changeCreateStory}
          onTitleChange={setCreateTitle}
          onClose={() => setCreateDialogOpen(false)}
          onSubmit={submitCreateSession}
        />
      ) : null}
    </div>
  )
}

export function SessionCenterPage() {
  return (
    <AppShell>
      <SessionCenterContent />
    </AppShell>
  )
}
