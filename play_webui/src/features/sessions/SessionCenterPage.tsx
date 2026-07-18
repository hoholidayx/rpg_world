'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertCircle,
  CheckCircle2,
  CloudMoon,
  Eye,
  FilePlus2,
  Loader2,
  Play,
  RefreshCw,
  Search,
  Sparkles,
  Trash2,
  UserRound,
} from 'lucide-react'
import { ConfirmDialog, Dialog } from '@/components/common/Dialog'
import { SideDrawer } from '@/components/common/SideDrawer'
import { buildDreamPageHref } from '@/features/dream/dreamNavigation'
import { AppShell, useAppShell } from '@/features/layout/AppShell'
import { getCurrentScene } from '@/lib/api/scene'
import { createSession, deleteSession, getSessionHistoryPage, listSessions } from '@/lib/api/sessions'
import { listStories } from '@/lib/api/stories'
import { cn } from '@/lib/utils/cn'
import type { Scene } from '@/types/scene'
import {
  HISTORY_MESSAGE_ROLE,
  SESSION_ACTIVITY,
  type HistoryPage,
  type SessionComputedActivity,
  type SessionSummary,
} from '@/types/session'
import type { StorySummary } from '@/types/story'

type ActivityFilter = 'all' | SessionComputedActivity
type SortMode = 'active' | 'created' | 'title' | 'story'
type DeleteNotice = { message: string; pendingCleanup: boolean }

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
  computedActivity: SessionComputedActivity
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

const activityMeta: Record<SessionComputedActivity, { label: string; badgeClass: string; dotClass: string }> = {
  [SESSION_ACTIVITY.RECENT]: {
    label: '最近活跃',
    badgeClass: 'bg-teal-100 text-teal-700',
    dotClass: 'bg-teal-500',
  },
  [SESSION_ACTIVITY.STALE]: {
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

function sessionInitial(item: Pick<SessionCenterItem, 'id' | 'title'>) {
  return Array.from(item.title?.trim() || item.id)[0]?.toUpperCase() || 'S'
}

function latestTimestamp(session: SessionSummary) {
  return Math.max(getTimestamp(session.updatedAt), getTimestamp(session.createdAt))
}

function playerCharacterLabel(item: Pick<SessionCenterItem, 'playerCharacter'>) {
  return item.playerCharacter?.name || '待绑定角色'
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
  const computedActivity: SessionComputedActivity = latestAt && now - latestAt <= RECENT_WINDOW_MS
    ? SESSION_ACTIVITY.RECENT
    : SESSION_ACTIVITY.STALE
  const storySummary = story.summary ?? ''
  const searchText = [
    session.id,
    session.title ?? '',
    session.description ?? '',
    session.playerCharacter?.name ?? '',
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
    .slice(0, 5)
    .map(([key, value]) => `${key}：${value}`)

  return [...parts, ...attrs].join('；') || '暂无场景数据'
}

function latestTurnSummary(history?: HistoryPage | null) {
  const latest = history?.turns.at(-1)
  if (!latest) return '暂无已提交回合'
  const messages = [...latest.messages].reverse()
  const latestMessage = messages.find((message) => (
    message.role === HISTORY_MESSAGE_ROLE.ASSISTANT && message.content.trim()
  )) ?? messages.find((message) => message.content.trim())
  return latestMessage?.content || '暂无已提交回合'
}

function ActivityBadge({ activity }: { activity: SessionComputedActivity }) {
  const meta = activityMeta[activity]
  return (
    <span className={cn('inline-flex h-7 shrink-0 items-center gap-2 rounded-full px-3 text-xs font-black', meta.badgeClass)}>
      <span className={cn('h-2 w-2 rounded-full', meta.dotClass)} />
      {meta.label}
    </span>
  )
}

function SessionArtwork({
  item,
  className = 'h-32',
}: {
  item: Pick<SessionCenterItem, 'id' | 'storyId' | 'title'>
  className?: string
}) {
  return (
    <div className={cn('relative overflow-hidden rounded-xl bg-gradient-to-br', pickCoverClass(`${item.storyId}-${item.id}`), className)}>
      <div className="absolute -right-8 -top-14 h-36 w-36 rounded-full border-[24px] border-white/10" />
      <div className="absolute bottom-[-32px] left-8 h-24 w-28 rounded-t-full bg-white/15" />
      <div className="absolute bottom-0 left-24 h-20 w-9 rounded-t-full bg-white/50 shadow-[66px_18px_0_-8px_rgba(255,255,255,0.28),118px_14px_0_-10px_rgba(255,255,255,0.18)]" />
      <span className="absolute right-6 top-1/2 -translate-y-1/2 text-7xl font-black text-white/25">
        {sessionInitial(item)}
      </span>
      <div className="absolute inset-x-0 bottom-0 h-20 bg-gradient-to-t from-slate-950/55 to-transparent" />
    </div>
  )
}

function SessionAvatar({ item }: { item: SessionCenterItem }) {
  return (
    <span className={cn(
      'flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br text-sm font-black text-white shadow-sm',
      pickCoverClass(`${item.storyId}-${item.id}`),
    )}>
      {sessionInitial(item)}
    </span>
  )
}

function SessionListItem({
  item,
  onEnter,
  onDetails,
}: {
  item: SessionCenterItem
  onEnter: () => void
  onDetails: () => void
}) {
  const description = item.description || item.storySummary || '暂无会话描述'
  const playerCharacter = playerCharacterLabel(item)

  return (
    <article className="border-t border-slate-200 bg-white transition hover:bg-violet-50/25">
      <div className="hidden min-h-[92px] grid-cols-[44px_minmax(180px,1.35fr)_minmax(140px,0.75fr)_minmax(130px,0.65fr)_112px_210px] items-center gap-3 px-4 py-4 xl:grid">
        <SessionAvatar item={item} />
        <div className="min-w-0">
          <button
            type="button"
            onClick={onEnter}
            className="block max-w-full truncate text-left text-sm font-black text-slate-950 transition hover:text-violet-700"
          >
            {item.title || item.id}
          </button>
          <p className="mt-1 truncate text-xs font-semibold text-slate-400">{item.id}</p>
          <p className="mt-1 truncate text-xs font-semibold text-slate-500">{description}</p>
        </div>
        <div className="min-w-0">
          <p className="truncate text-sm font-black text-slate-900">{item.storyTitle}</p>
          <p className="mt-1 flex items-center gap-1.5 truncate text-xs font-semibold text-slate-500">
            <UserRound size={13} className="shrink-0" />
            <span className="truncate">{playerCharacter}</span>
          </p>
        </div>
        <div className="min-w-0">
          <p className="truncate text-sm font-bold text-slate-800">{formatDate(item.updatedAt ?? item.createdAt)}</p>
          <p className="mt-1 truncate text-xs font-semibold text-slate-400">创建于 {formatDate(item.createdAt)}</p>
        </div>
        <ActivityBadge activity={item.computedActivity} />
        <div className="grid grid-cols-3 gap-2">
          <Link
            href={buildDreamPageHref(item.id, '/sessions')}
            className="inline-flex h-9 items-center justify-center gap-1.5 whitespace-nowrap rounded-lg border border-slate-200 bg-white px-2 text-xs font-black text-slate-700 transition hover:border-violet-300 hover:text-violet-700"
            aria-label={`管理会话 ${item.title || item.id} 的 Dream 记忆`}
            title="Dream 记忆"
          >
            <CloudMoon size={14} />
            记忆
          </Link>
          <button
            type="button"
            onClick={onDetails}
            className="inline-flex h-9 items-center justify-center gap-1.5 whitespace-nowrap rounded-lg border border-slate-200 bg-white px-2 text-xs font-black text-slate-700 transition hover:border-violet-300 hover:text-violet-700"
            aria-label={`查看会话 ${item.title || item.id} 详情`}
          >
            <Eye size={14} />
            详情
          </button>
          <button
            type="button"
            onClick={onEnter}
            className="inline-flex h-9 items-center justify-center gap-1.5 whitespace-nowrap rounded-lg bg-slate-950 px-2 text-xs font-black text-white transition hover:bg-slate-800"
          >
            <Play size={13} />
            进入
          </button>
        </div>
      </div>

      <div className="p-4 xl:hidden">
        <div className="flex items-start gap-3">
          <SessionAvatar item={item} />
          <div className="min-w-0 flex-1">
            <button
              type="button"
              onClick={onEnter}
              className="block max-w-full truncate text-left text-base font-black text-slate-950 transition hover:text-violet-700"
            >
              {item.title || item.id}
            </button>
            <p className="mt-1 truncate text-xs font-semibold text-slate-400">{item.id}</p>
          </div>
          <ActivityBadge activity={item.computedActivity} />
        </div>
        <p className="mt-3 line-clamp-2 text-sm font-semibold leading-6 text-slate-500">{description}</p>
        <div className="mt-3 grid gap-2 rounded-xl bg-slate-50 p-3 sm:grid-cols-3">
          <div className="min-w-0">
            <span className="block text-[10px] font-black uppercase tracking-wide text-slate-400">故事</span>
            <span className="mt-1 block truncate text-xs font-bold text-slate-800">{item.storyTitle}</span>
          </div>
          <div className="min-w-0">
            <span className="block text-[10px] font-black uppercase tracking-wide text-slate-400">玩家角色</span>
            <span className="mt-1 block truncate text-xs font-bold text-slate-800">{playerCharacter}</span>
          </div>
          <div className="min-w-0">
            <span className="block text-[10px] font-black uppercase tracking-wide text-slate-400">最近更新</span>
            <span className="mt-1 block truncate text-xs font-bold text-slate-800">{formatDate(item.updatedAt ?? item.createdAt)}</span>
          </div>
        </div>
        <div className="mt-4 grid grid-cols-3 gap-2">
          <Link
            href={buildDreamPageHref(item.id, '/sessions')}
            className="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white px-3 text-sm font-black text-slate-700 transition hover:border-violet-300 hover:text-violet-700"
            aria-label={`管理会话 ${item.title || item.id} 的 Dream 记忆`}
            title="Dream 记忆"
          >
            <CloudMoon size={15} />
            记忆
          </Link>
          <button
            type="button"
            onClick={onDetails}
            className="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white px-3 text-sm font-black text-slate-700 transition hover:border-violet-300 hover:text-violet-700"
          >
            <Eye size={15} />
            查看详情
          </button>
          <button
            type="button"
            onClick={onEnter}
            className="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-slate-950 px-3 text-sm font-black text-white transition hover:bg-slate-800"
          >
            <Play size={15} />
            进入会话
          </button>
        </div>
      </div>
    </article>
  )
}

function DetailSection({
  title,
  note,
  loading = false,
  error,
  onRetry,
  children,
}: {
  title: string
  note: string
  loading?: boolean
  error?: string | null
  onRetry?: () => void
  children: ReactNode
}) {
  return (
    <section className="mt-5">
      <div className="mb-2 flex items-center justify-between gap-3">
        <h3 className="text-xs font-black uppercase tracking-[0.1em] text-slate-500">{title}</h3>
        <span className="text-[10px] font-black uppercase tracking-[0.1em] text-slate-400">{note}</span>
      </div>
      <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-semibold leading-6 text-slate-700">
        {loading ? (
          <div className="space-y-2" aria-label={`${title}加载中`}>
            <div className="h-3 w-full animate-pulse rounded bg-slate-200" />
            <div className="h-3 w-3/4 animate-pulse rounded bg-slate-200" />
          </div>
        ) : error ? (
          <div className="flex items-start justify-between gap-3 text-amber-700">
            <span>{error}</span>
            {onRetry ? (
              <button
                type="button"
                onClick={onRetry}
                className="shrink-0 rounded-md border border-amber-200 bg-white px-2 py-1 text-xs font-black transition hover:border-amber-300"
              >
                重试
              </button>
            ) : null}
          </div>
        ) : children}
      </div>
    </section>
  )
}

function SessionDetailDrawer({
  open,
  suspended,
  item,
  scene,
  history,
  sceneLoading,
  historyLoading,
  sceneError,
  historyError,
  onRetryScene,
  onRetryHistory,
  onClose,
  onEnter,
  onDelete,
}: {
  open: boolean
  suspended: boolean
  item: SessionCenterItem | null
  scene?: Scene | null
  history?: HistoryPage | null
  sceneLoading: boolean
  historyLoading: boolean
  sceneError: string | null
  historyError: string | null
  onRetryScene: () => void
  onRetryHistory: () => void
  onClose: () => void
  onEnter: () => void
  onDelete: () => void
}) {
  return (
    <SideDrawer
      open={open}
      suspended={suspended}
      side="right"
      eyebrow="会话详情"
      title={item?.title || item?.id || '会话详情'}
      description={item ? `${item.storyTitle} · ${item.id}` : undefined}
      meta={item ? <ActivityBadge activity={item.computedActivity} /> : undefined}
      onClose={onClose}
      panelClassName="max-w-[560px]"
      footer={item ? (
        <div className="flex items-center justify-between gap-3">
          <button
            type="button"
            onClick={onDelete}
            className="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-rose-200 bg-white px-4 text-sm font-black text-rose-700 transition hover:border-rose-300 hover:bg-rose-50"
          >
            <Trash2 size={15} />
            删除
          </button>
          <button
            type="button"
            onClick={onEnter}
            className="inline-flex h-10 flex-1 items-center justify-center gap-2 rounded-lg bg-violet-600 px-5 text-sm font-black text-white shadow-lg shadow-violet-100 transition hover:bg-violet-700 sm:flex-none"
          >
            <Play size={15} />
            进入会话
          </button>
        </div>
      ) : undefined}
    >
      {item ? (
        <>
          <SessionArtwork item={item} />
          <div className="mt-4 grid grid-cols-2 gap-3">
            <div className="rounded-xl bg-slate-50 px-3 py-3">
              <span className="block text-[10px] font-black uppercase tracking-wide text-slate-400">玩家角色</span>
              <span className="mt-1 block truncate text-sm font-black text-slate-900">{playerCharacterLabel(item)}</span>
            </div>
            <div className="rounded-xl bg-slate-50 px-3 py-3">
              <span className="block text-[10px] font-black uppercase tracking-wide text-slate-400">最近更新</span>
              <span className="mt-1 block truncate text-sm font-black text-slate-900">{formatDate(item.updatedAt ?? item.createdAt)}</span>
            </div>
            <div className="rounded-xl bg-slate-50 px-3 py-3">
              <span className="block text-[10px] font-black uppercase tracking-wide text-slate-400">所属故事</span>
              <span className="mt-1 block truncate text-sm font-black text-slate-900">{item.storyTitle}</span>
            </div>
            <div className="rounded-xl bg-slate-50 px-3 py-3">
              <span className="block text-[10px] font-black uppercase tracking-wide text-slate-400">创建时间</span>
              <span className="mt-1 block truncate text-sm font-black text-slate-900">{formatDate(item.createdAt)}</span>
            </div>
          </div>

          <DetailSection title="会话描述" note="profile">
            {item.description || '暂无会话描述'}
          </DetailSection>
          <DetailSection title="故事概览" note="story">
            <span className="line-clamp-5">{item.storySummary || '暂无故事摘要'}</span>
          </DetailSection>
          <DetailSection
            title="当前场景"
            note="scene"
            loading={sceneLoading}
            error={sceneError}
            onRetry={onRetryScene}
          >
            {sceneSummary(scene)}
          </DetailSection>
          <DetailSection
            title="最后一轮"
            note={history?.endTurnId ? `turn ${history.endTurnId}` : 'committed turn'}
            loading={historyLoading}
            error={historyError}
            onRetry={onRetryHistory}
          >
            <span className="line-clamp-8 whitespace-pre-wrap break-words">{latestTurnSummary(history)}</span>
          </DetailSection>
        </>
      ) : null}
    </SideDrawer>
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

function SessionListSkeleton() {
  return (
    <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
      <div className="border-b border-slate-200 px-5 py-4">
        <div className="h-6 w-32 animate-pulse rounded bg-slate-200" />
        <div className="mt-2 h-4 w-64 max-w-full animate-pulse rounded bg-slate-100" />
      </div>
      <div className="grid gap-3 border-b border-slate-200 p-4 md:grid-cols-2 xl:grid-cols-4">
        {[0, 1, 2, 3].map((item) => <div key={item} className="h-11 animate-pulse rounded-lg bg-slate-100" />)}
      </div>
      {[0, 1, 2, 3].map((item) => (
        <div key={item} className="flex h-24 items-center gap-4 border-t border-slate-100 px-5">
          <div className="h-11 w-11 animate-pulse rounded-xl bg-slate-200" />
          <div className="flex-1">
            <div className="h-4 w-48 max-w-full animate-pulse rounded bg-slate-200" />
            <div className="mt-3 h-3 w-72 max-w-full animate-pulse rounded bg-slate-100" />
          </div>
        </div>
      ))}
    </section>
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
  const [detailSessionId, setDetailSessionId] = useState<string | null>(null)
  const [detailOpen, setDetailOpen] = useState(false)
  const [createDialogOpen, setCreateDialogOpen] = useState(false)
  const [createStoryId, setCreateStoryId] = useState<number | null>(null)
  const [createTitle, setCreateTitle] = useState('')
  const [deleteTarget, setDeleteTarget] = useState<SessionCenterItem | null>(null)
  const [deleteNotice, setDeleteNotice] = useState<DeleteNotice | null>(null)

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

  const detailItem = useMemo(
    () => allItems.find((item) => item.id === detailSessionId) ?? null,
    [allItems, detailSessionId],
  )
  const detailQueryEnabled = Boolean(detailOpen && detailItem)
  const detailSessionIdForQuery = detailQueryEnabled ? detailItem?.id ?? '' : ''
  const sceneQuery = useQuery({
    queryKey: ['play-session-scene', detailSessionIdForQuery],
    queryFn: () => getCurrentScene(detailSessionIdForQuery),
    enabled: detailQueryEnabled,
    refetchOnWindowFocus: false,
  })
  const historyQuery = useQuery({
    queryKey: ['play-session-history-page', detailSessionIdForQuery, 'session-center-detail', 1],
    queryFn: () => getSessionHistoryPage(detailSessionIdForQuery, { limit: 1 }),
    enabled: detailQueryEnabled,
    refetchOnWindowFocus: false,
  })

  useEffect(() => {
    setDetailOpen(false)
    setDetailSessionId(null)
  }, [currentWorkspace])

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

  const deleteSessionMutation = useMutation({
    mutationFn: (item: SessionCenterItem) => deleteSession(item.id),
    onSuccess: (result, item) => {
      queryClient.setQueryData<SessionSummary[]>(
        ['play-sessions', currentWorkspace, item.storyId],
        (sessions) => sessions?.filter((session) => session.id !== item.id),
      )
      queryClient.removeQueries({ queryKey: ['play-session-scene', item.id] })
      queryClient.removeQueries({ queryKey: ['play-session-status-tables', item.id] })
      queryClient.removeQueries({ queryKey: ['play-session-history', item.id] })
      queryClient.removeQueries({ queryKey: ['play-session-history-page', item.id] })
      queryClient.removeQueries({ queryKey: ['play-session', item.id] })
      queryClient.removeQueries({ queryKey: ['play-session-composer', item.id] })
      queryClient.removeQueries({ queryKey: ['play-session-summaries', item.id] })
      queryClient.removeQueries({ queryKey: ['play-session-summary', item.id] })
      queryClient.removeQueries({ queryKey: ['play-session-context-preview', item.id] })
      queryClient.removeQueries({ queryKey: ['session-main-llm', item.id] })
      queryClient.removeQueries({ queryKey: ['session-rp-modules', item.id] })
      queryClient.invalidateQueries({ queryKey: ['play-sessions', currentWorkspace] })
      queryClient.invalidateQueries({ queryKey: ['play-story-library-aggregate', currentWorkspace, item.storyId] })
      if (detailSessionId === item.id) {
        setDetailOpen(false)
        setDetailSessionId(null)
      }
      setDeleteTarget(null)
      setDeleteNotice({
        pendingCleanup: result.runtimeCleanup === 'pending',
        message: result.runtimeCleanup === 'pending'
          ? '会话记录已删除，但运行目录仍待清理；可在设置的数据清理中处理。'
          : `会话“${item.title || item.id}”已永久删除。`,
      })
    },
  })

  const aggregatesLoading = sessionQueries.some((query) => query.isLoading)
  const initialSessionsLoading = aggregatesLoading && allItems.length === 0
  const aggregateErrors = aggregates.filter((aggregate) => aggregate.error)
  const hasActiveFilters = Boolean(search.trim()) || activityFilter !== 'all' || storyFilter !== 'all'

  function enterSession(item: Pick<SessionCenterItem, 'id'> | null) {
    if (!item) return
    router.push(`/session/${item.id}`)
  }

  function openDetails(item: SessionCenterItem) {
    setDetailSessionId(item.id)
    setDetailOpen(true)
  }

  function clearFilters() {
    setSearch('')
    setActivityFilter('all')
    setStoryFilter('all')
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
    <div className="min-w-0 px-4 py-7 sm:px-5 xl:px-7 xl:py-8">
      <section className="mb-5 grid gap-4 xl:grid-cols-[minmax(0,1fr)_auto] xl:items-end">
        <div>
          <p className="mb-2 flex items-center gap-2 text-sm font-black text-slate-500">
            <span className="h-2.5 w-2.5 rounded-full bg-emerald-500" />
            {currentWorkspace ?? '未选择 workspace'} / session center
          </p>
          <h1 className="text-3xl font-black text-slate-950">会话中心</h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-500">
            在一个列表中查找、管理并继续所有会话；默认按最近更新时间排列。
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

      {deleteNotice ? (
        <section className={cn(
          'mb-4 flex items-start gap-3 rounded-lg border px-4 py-3 text-sm font-semibold leading-6',
          deleteNotice.pendingCleanup
            ? 'border-amber-200 bg-amber-50 text-amber-800'
            : 'border-emerald-200 bg-emerald-50 text-emerald-800',
        )}>
          {deleteNotice.pendingCleanup
            ? <AlertCircle size={18} className="mt-0.5 shrink-0" />
            : <CheckCircle2 size={18} className="mt-0.5 shrink-0" />}
          <span>{deleteNotice.message}</span>
        </section>
      ) : null}

      {!currentWorkspace ? (
        <section className="rounded-xl border border-dashed border-slate-300 bg-white/70 px-6 py-12 text-center text-sm font-semibold text-slate-500">
          请选择 workspace 后查看会话中心
        </section>
      ) : storiesQuery.isError ? (
        <section className="rounded-xl border border-rose-200 bg-rose-50 px-6 py-6 text-sm font-semibold text-rose-700">
          故事列表加载失败：{toErrorMessage(storiesQuery.error)}
        </section>
      ) : storiesQuery.isLoading ? (
        <SessionListSkeleton />
      ) : stories.length === 0 ? (
        <section className="rounded-xl border border-dashed border-slate-300 bg-white/70 px-6 py-12 text-center">
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
      ) : initialSessionsLoading ? (
        <SessionListSkeleton />
      ) : allItems.length === 0 ? (
        <div className="grid gap-4">
          {aggregateErrors.length ? (
            <div className="rounded-xl border border-amber-200 bg-amber-50 px-5 py-3 text-sm font-semibold text-amber-700">
              <span className="mr-2 inline-flex align-[-2px]"><AlertCircle size={16} /></span>
              部分 story 会话加载失败：{aggregateErrors.map((item) => `${item.story.title}（${item.error}）`).join('；')}
            </div>
          ) : null}
          <section className="rounded-xl border border-dashed border-slate-300 bg-white/70 px-6 py-12 text-center">
            <CheckCircle2 size={28} className="mx-auto text-violet-600" />
            <h2 className="mt-3 text-lg font-black text-slate-950">还没有会话</h2>
            <p className="mt-2 text-sm font-semibold text-slate-500">选择一个 story 创建新会话后，就可以从这里继续游玩。</p>
            <button
              type="button"
              onClick={openCreateDialog}
              className="mt-5 inline-flex h-10 items-center gap-2 rounded-lg bg-violet-600 px-4 text-sm font-black text-white transition hover:bg-violet-700"
            >
              <FilePlus2 size={16} />
              新建会话
            </button>
          </section>
        </div>
      ) : (
        <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <header className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-200 px-5 py-4">
            <div>
              <h2 className="text-lg font-black text-slate-950">全部会话</h2>
              <p className="mt-1 text-sm font-semibold leading-6 text-slate-500">搜索、筛选或直接进入最近更新的故事进度。</p>
            </div>
            <span className="inline-flex h-8 items-center rounded-full bg-slate-100 px-3 text-xs font-black text-slate-600" aria-live="polite">
              显示 {filteredItems.length} / {allItems.length}
            </span>
          </header>

          <div className="border-b border-slate-200 bg-slate-50/50 p-4">
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-[minmax(280px,1fr)_auto_minmax(160px,auto)_minmax(170px,auto)]" aria-label="筛选会话">
              <label className="flex h-11 items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-500 shadow-sm focus-within:border-violet-300 focus-within:ring-4 focus-within:ring-violet-100">
                <Search size={17} />
                <input
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="搜索会话、故事或玩家角色"
                  className="min-w-0 flex-1 bg-transparent text-slate-900 outline-none placeholder:text-slate-400"
                />
              </label>
              <div className="grid h-11 grid-cols-3 rounded-lg border border-slate-200 bg-white p-1 shadow-sm" role="group" aria-label="会话活跃度">
                {[
                  ['all', '全部'],
                  [SESSION_ACTIVITY.RECENT, '最近活跃'],
                  [SESSION_ACTIVITY.STALE, '较久未更新'],
                ].map(([value, label]) => (
                  <button
                    key={value}
                    type="button"
                    onClick={() => setActivityFilter(value as ActivityFilter)}
                    aria-pressed={activityFilter === value}
                    className={cn(
                      'whitespace-nowrap rounded-md px-2 text-xs font-black transition',
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
                className="h-11 min-w-0 rounded-lg border border-slate-200 bg-white px-3 text-sm font-bold text-slate-700 shadow-sm outline-none transition focus:border-violet-300 focus:ring-4 focus:ring-violet-100"
                aria-label="故事筛选"
              >
                <option value="all">全部故事</option>
                {stories.map((story) => <option key={story.id} value={story.id}>{story.title}</option>)}
              </select>
              <select
                value={sortMode}
                onChange={(event) => setSortMode(event.target.value as SortMode)}
                className="h-11 min-w-0 rounded-lg border border-slate-200 bg-white px-3 text-sm font-bold text-slate-700 shadow-sm outline-none transition focus:border-violet-300 focus:ring-4 focus:ring-violet-100"
                aria-label="排序"
              >
                <option value="active">最近活跃优先</option>
                <option value="created">最近创建优先</option>
                <option value="title">会话标题 A-Z</option>
                <option value="story">故事标题 A-Z</option>
              </select>
            </div>
            <div className="mt-3 flex min-h-6 flex-wrap items-center justify-between gap-2 text-xs font-semibold text-slate-500">
              <span>{filteredItems.length === allItems.length ? `共 ${allItems.length} 个会话` : `当前筛选出 ${filteredItems.length} 个会话`}</span>
              {hasActiveFilters ? (
                <button
                  type="button"
                  onClick={clearFilters}
                  className="font-black text-violet-700 transition hover:text-violet-900"
                >
                  清除筛选
                </button>
              ) : null}
            </div>
          </div>

          {aggregatesLoading ? (
            <p className="flex items-center gap-2 border-b border-slate-200 px-5 py-2 text-xs font-bold text-slate-400">
              <Loader2 size={14} className="animate-spin" />
              正在加载其余 story 的会话
            </p>
          ) : null}
          {aggregateErrors.length ? (
            <div className="border-b border-amber-200 bg-amber-50 px-5 py-3 text-sm font-semibold text-amber-700">
              <span className="mr-2 inline-flex align-[-2px]"><AlertCircle size={16} /></span>
              部分 story 会话加载失败：{aggregateErrors.map((item) => `${item.story.title}（${item.error}）`).join('；')}
            </div>
          ) : null}

          {filteredItems.length ? (
            <div>
              <div className="hidden min-h-11 grid-cols-[44px_minmax(180px,1.35fr)_minmax(140px,0.75fr)_minmax(130px,0.65fr)_112px_210px] items-center gap-3 bg-slate-50 px-4 text-xs font-black uppercase tracking-wide text-slate-500 xl:grid">
                <span />
                <span>会话</span>
                <span>故事与角色</span>
                <span>最近更新</span>
                <span>状态</span>
                <span>操作</span>
              </div>
              {filteredItems.map((item) => (
                <SessionListItem
                  key={item.id}
                  item={item}
                  onEnter={() => enterSession(item)}
                  onDetails={() => openDetails(item)}
                />
              ))}
            </div>
          ) : (
            <section className="border-t border-dashed border-slate-200 px-6 py-12 text-center">
              <Search size={24} className="mx-auto text-slate-400" />
              <h3 className="mt-3 text-base font-black text-slate-900">没有匹配的会话</h3>
              <p className="mt-2 text-sm font-semibold text-slate-500">调整关键词或清除当前筛选后再试。</p>
              <button
                type="button"
                onClick={clearFilters}
                className="mt-4 inline-flex h-9 items-center rounded-lg border border-violet-200 bg-violet-50 px-4 text-sm font-black text-violet-700 transition hover:border-violet-300 hover:bg-violet-100"
              >
                清除筛选
              </button>
            </section>
          )}
        </section>
      )}

      <SessionDetailDrawer
        open={detailOpen && Boolean(detailItem)}
        suspended={Boolean(deleteTarget)}
        item={detailItem}
        scene={sceneQuery.data ?? null}
        history={historyQuery.data ?? null}
        sceneLoading={sceneQuery.isLoading}
        historyLoading={historyQuery.isLoading}
        sceneError={sceneQuery.isError ? `场景加载失败：${toErrorMessage(sceneQuery.error)}` : null}
        historyError={historyQuery.isError ? `回合加载失败：${toErrorMessage(historyQuery.error)}` : null}
        onRetryScene={() => { void sceneQuery.refetch() }}
        onRetryHistory={() => { void historyQuery.refetch() }}
        onClose={() => setDetailOpen(false)}
        onEnter={() => enterSession(detailItem)}
        onDelete={() => {
          if (!detailItem) return
          deleteSessionMutation.reset()
          setDeleteNotice(null)
          setDeleteTarget(detailItem)
        }}
      />

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
      {deleteTarget ? (
        <ConfirmDialog
          title="删除会话"
          heading={`永久删除“${deleteTarget.title || deleteTarget.id}”？`}
          body={(
            <div>
              <p>
                会话 <strong>{deleteTarget.id}</strong> 的主历史、冷备、角色绑定、状态表、剧情记忆、配置覆盖和全部运行文件都会永久删除，且无法恢复。
              </p>
              {deleteSessionMutation.error ? (
                <p className="mt-3 font-bold text-rose-800">
                  删除失败：{toErrorMessage(deleteSessionMutation.error)}
                </p>
              ) : null}
            </div>
          )}
          confirmLabel="永久删除"
          pending={deleteSessionMutation.isPending}
          onClose={() => {
            if (!deleteSessionMutation.isPending) setDeleteTarget(null)
          }}
          onConfirm={() => deleteSessionMutation.mutate(deleteTarget)}
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
