'use client'

import { useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertCircle,
  BookOpen,
  Edit3,
  FilePlus2,
  Globe2,
  Loader2,
  Play,
  Search,
  Sparkles,
  TableProperties,
  UsersRound,
} from 'lucide-react'
import { AppShell, useAppShell } from '@/features/layout/AppShell'
import { listStoryCharacters } from '@/lib/api/characters'
import { listStoryLorebookEntries } from '@/lib/api/lorebook'
import { createSession, listSessions } from '@/lib/api/sessions'
import { listStories } from '@/lib/api/stories'
import { listStoryStatusMounts } from '@/lib/api/statusTables'
import { cn } from '@/lib/utils/cn'
import type { CharacterCard } from '@/types/characters'
import type { LorebookEntry } from '@/types/lorebook'
import type { SessionSummary } from '@/types/session'
import { STATUS_KIND, type StoryStatusMount } from '@/types/statusTables'
import { STORY_COMPUTED_STATUS, type StoryComputedStatus, type StoryLibraryItem, type StorySummary } from '@/types/story'

type StoryFilter = 'all' | StoryComputedStatus
type StorySort = 'active' | 'updated' | 'title' | 'sessions'

type StoryAggregate = {
  storyId: number
  characters: CharacterCard[]
  lorebookEntries: LorebookEntry[]
  statusMounts: StoryStatusMount[]
  sessions: SessionSummary[]
  error: string | null
}

type StoryLibraryViewItem = StoryLibraryItem & {
  aggregateError: string | null
  latestAt: number
}

const coverClasses = [
  'from-slate-800 via-slate-600 to-cyan-100',
  'from-teal-900 via-emerald-700 to-amber-100',
  'from-zinc-900 via-stone-700 to-rose-100',
  'from-indigo-900 via-sky-700 to-slate-100',
  'from-amber-800 via-orange-500 to-teal-100',
]

const statusMeta: Record<StoryComputedStatus, { label: string; badgeClass: string; dotClass: string }> = {
  [STORY_COMPUTED_STATUS.LIVE]: {
    label: '进行中',
    badgeClass: 'bg-teal-100 text-teal-700',
    dotClass: 'bg-teal-500',
  },
  [STORY_COMPUTED_STATUS.DRAFT]: {
    label: '未开始',
    badgeClass: 'bg-amber-100 text-amber-700',
    dotClass: 'bg-amber-500',
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

function pickCoverClass(storyId: number) {
  return coverClasses[Math.abs(storyId) % coverClasses.length]
}

function emptyAggregate(storyId: number): StoryAggregate {
  return {
    storyId,
    characters: [],
    lorebookEntries: [],
    statusMounts: [],
    sessions: [],
    error: null,
  }
}

function isFulfilled<T>(result: PromiseSettledResult<T>): result is PromiseFulfilledResult<T> {
  return result.status === 'fulfilled'
}

async function loadStoryAggregate(workspace: string, storyId: number): Promise<StoryAggregate> {
  const [characters, lorebookEntries, statusMounts, sessions] = await Promise.allSettled([
    listStoryCharacters(workspace, storyId),
    listStoryLorebookEntries(workspace, storyId),
    listStoryStatusMounts(workspace, storyId),
    listSessions(workspace, storyId),
  ])
  const errors = [characters, lorebookEntries, statusMounts, sessions]
    .filter((result) => result.status === 'rejected')
    .map((result) => result.reason instanceof Error ? result.reason.message : '加载失败')

  return {
    storyId,
    characters: isFulfilled(characters) ? characters.value : [],
    lorebookEntries: isFulfilled(lorebookEntries) ? lorebookEntries.value : [],
    statusMounts: isFulfilled(statusMounts) ? statusMounts.value : [],
    sessions: isFulfilled(sessions) ? sessions.value : [],
    error: errors.length ? errors.join(' / ') : null,
  }
}

function buildSearchText(
  story: StorySummary,
  aggregate: StoryAggregate,
) {
  const characterText = aggregate.characters.map((character) => `${character.name} ${character.personality} ${character.content}`).join(' ')
  const lorebookText = aggregate.lorebookEntries.map((entry) => `${entry.name} ${entry.description} ${entry.content} ${entry.tags.join(' ')}`).join(' ')
  const statusText = aggregate.statusMounts.map((mount) => `${mount.tableName} ${mount.description} ${mount.statusKind}`).join(' ')
  const sessionText = aggregate.sessions.map((session) => `${session.title ?? ''} ${session.description ?? ''}`).join(' ')
  const openingText = story.openings.map((opening) => `${opening.title} ${opening.message}`).join(' ')
  return `${story.title} ${story.summary ?? ''} ${story.storyPrompt} ${openingText} ${characterText} ${lorebookText} ${statusText} ${sessionText}`.toLowerCase()
}

function toLibraryItem(story: StorySummary, aggregate: StoryAggregate): StoryLibraryViewItem {
  const sortedSessions = [...aggregate.sessions].sort((first, second) => {
    const firstTime = Math.max(getTimestamp(first.updatedAt), getTimestamp(first.createdAt))
    const secondTime = Math.max(getTimestamp(second.updatedAt), getTimestamp(second.createdAt))
    return secondTime - firstTime
  })
  const latest = sortedSessions[0] ?? null
  const latestAt = Math.max(
    getTimestamp(story.updatedAt),
    getTimestamp(story.createdAt),
    ...sortedSessions.map((session) => Math.max(getTimestamp(session.updatedAt), getTimestamp(session.createdAt))),
  )
  const computedStatus: StoryComputedStatus = sortedSessions.length ? STORY_COMPUTED_STATUS.LIVE : STORY_COMPUTED_STATUS.DRAFT
  const sceneStatusCount = aggregate.statusMounts.filter((mount) => mount.statusKind === STATUS_KIND.SCENE).length

  return {
    ...story,
    characterCount: aggregate.characters.length,
    lorebookCount: aggregate.lorebookEntries.length,
    statusTableCount: aggregate.statusMounts.length,
    sceneStatusCount,
    sessions: sortedSessions,
    latestSession: latest,
    computedStatus,
    searchText: buildSearchText(story, aggregate),
    aggregateError: aggregate.error,
    latestAt,
  }
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
      <div className="flex items-center justify-between gap-3 text-sm font-bold text-slate-500">
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
  loading,
  sessionPending,
  onEdit,
  onPlay,
}: {
  item: StoryLibraryViewItem
  loading: boolean
  sessionPending: boolean
  onEdit: () => void
  onPlay: () => void
}) {
  const meta = statusMeta[item.computedStatus]
  const actionLabel = item.latestSession ? '继续' : '开局'

  return (
    <article
      className="overflow-hidden rounded-lg border border-slate-200 bg-white text-left shadow-sm transition hover:-translate-y-0.5 hover:border-teal-300 hover:shadow-lg"
    >
      <div className={cn('relative h-36 overflow-hidden bg-gradient-to-br', pickCoverClass(item.id))}>
        <div className="absolute bottom-[-28px] left-6 h-24 w-28 rounded-t-full bg-white/15" />
        <div className="absolute bottom-0 left-24 h-24 w-9 rounded-t-full bg-white/65 shadow-[72px_26px_0_-8px_rgba(255,255,255,0.38)]" />
        <div className="absolute inset-x-3 bottom-3 flex items-center justify-between gap-3">
          <span className={cn('inline-flex h-7 items-center gap-2 rounded-full px-3 text-xs font-black', meta.badgeClass)}>
            <span className={cn('h-2 w-2 rounded-full', meta.dotClass)} />
            {meta.label}
          </span>
          <span className="text-xs font-extrabold text-white/90 drop-shadow">story #{item.id}</span>
        </div>
      </div>

      <div className="p-4">
        <div className="flex items-start justify-between gap-3">
          <h2 className="min-w-0 flex-1 truncate text-lg font-black text-slate-950">{item.title}</h2>
          {loading ? <Loader2 size={16} className="mt-1 shrink-0 animate-spin text-slate-400" /> : null}
        </div>
        <p className="mt-2 line-clamp-2 min-h-11 text-sm leading-6 text-slate-500">{item.summary || '暂无故事摘要'}</p>

        <div className="mt-4 grid grid-cols-4 gap-2" aria-label="挂载资产">
          {[
            ['角色', item.characterCount],
            ['世界书', item.lorebookCount],
            ['状态表', item.statusTableCount],
            ['会话', item.sessions.length],
          ].map(([label, value]) => (
            <div key={label} className="min-w-0 rounded-lg bg-slate-50 px-3 py-2">
              <b className="block text-base leading-none text-slate-950">{value}</b>
              <span className="mt-1 block truncate text-xs font-bold text-slate-500">{label}</span>
            </div>
          ))}
        </div>

        {item.aggregateError ? (
          <p className="mt-3 flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-semibold text-amber-700">
            <AlertCircle size={14} />
            部分聚合数据加载失败
          </p>
        ) : null}

        <div className="mt-4 flex items-center justify-between gap-3 border-t border-slate-200 pt-3">
          <span className="truncate text-xs font-bold text-slate-400">更新 {formatDate(item.latestSession?.updatedAt ?? item.updatedAt)}</span>
          <div className="flex shrink-0 items-center gap-2">
            <button
              type="button"
              onClick={(event) => {
                event.stopPropagation()
                onEdit()
              }}
              className="flex h-8 items-center gap-1 rounded-lg border border-slate-200 bg-white px-3 text-xs font-black text-slate-700 transition hover:border-teal-300 hover:text-teal-700"
            >
              <Edit3 size={13} />
              编辑
            </button>
            <button
              type="button"
              disabled={sessionPending}
              onClick={(event) => {
                event.stopPropagation()
                onPlay()
              }}
              className="flex h-8 items-center gap-1 rounded-lg bg-slate-950 px-3 text-xs font-black text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {sessionPending ? <Loader2 size={13} className="animate-spin" /> : <Play size={13} />}
              {actionLabel}
            </button>
          </div>
        </div>
      </div>
    </article>
  )
}

function StorySkeleton() {
  return (
    <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
      <div className="h-36 animate-pulse bg-slate-200" />
      <div className="space-y-4 p-4">
        <div className="h-5 w-2/3 animate-pulse rounded bg-slate-200" />
        <div className="space-y-2">
          <div className="h-3 animate-pulse rounded bg-slate-100" />
          <div className="h-3 w-4/5 animate-pulse rounded bg-slate-100" />
        </div>
        <div className="grid grid-cols-4 gap-2">
          {[0, 1, 2, 3].map((item) => <div key={item} className="h-12 animate-pulse rounded-lg bg-slate-100" />)}
        </div>
      </div>
    </div>
  )
}

function StoriesContent() {
  const router = useRouter()
  const queryClient = useQueryClient()
  const { currentWorkspace } = useAppShell()
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState<StoryFilter>('all')
  const [sort, setSort] = useState<StorySort>('active')

  const storiesQuery = useQuery({
    queryKey: ['play-stories', currentWorkspace],
    queryFn: () => listStories(currentWorkspace ?? ''),
    enabled: Boolean(currentWorkspace),
  })
  const stories = useMemo(() => storiesQuery.data ?? [], [storiesQuery.data])

  const aggregateQueries = useQueries({
    queries: stories.map((story) => ({
      queryKey: ['play-story-library-aggregate', currentWorkspace, story.id],
      queryFn: () => loadStoryAggregate(currentWorkspace ?? '', story.id),
      enabled: Boolean(currentWorkspace),
    })),
  })

  const aggregateByStory = useMemo(() => {
    const result = new Map<number, StoryAggregate>()
    aggregateQueries.forEach((query, index) => {
      const story = stories[index]
      if (!story) return
      result.set(story.id, query.data ?? emptyAggregate(story.id))
    })
    return result
  }, [aggregateQueries, stories])

  const libraryItems = useMemo(
    () => stories.map((story) => toLibraryItem(story, aggregateByStory.get(story.id) ?? emptyAggregate(story.id))),
    [aggregateByStory, stories],
  )

  // 落地备注：当前后端没有 story aggregate/search 接口；这里先按效果图说明做前端本地过滤。
  // 搜索语料来自 story 主数据 + 前端额外拉取的 mounts/sessions，未来可替换为服务端聚合搜索。
  const filteredItems = useMemo(() => {
    const query = search.trim().toLowerCase()
    return libraryItems
      .filter((item) => (filter === 'all' ? true : item.computedStatus === filter))
      .filter((item) => !query || item.searchText.includes(query))
      .sort((first, second) => {
        if (sort === 'title') return first.title.localeCompare(second.title, 'zh-CN')
        if (sort === 'sessions') return second.sessions.length - first.sessions.length || second.latestAt - first.latestAt
        if (sort === 'updated') return getTimestamp(second.updatedAt) - getTimestamp(first.updatedAt)
        return second.latestAt - first.latestAt
      })
  }, [filter, libraryItems, search, sort])

  const aggregatesLoading = aggregateQueries.some((query) => query.isLoading)

  const liveCount = libraryItems.filter((item) => item.computedStatus === STORY_COMPUTED_STATUS.LIVE).length
  const draftCount = libraryItems.filter((item) => item.computedStatus === STORY_COMPUTED_STATUS.DRAFT).length
  const totalCharacters = libraryItems.reduce((sum, item) => sum + item.characterCount, 0)
  const totalLorebook = libraryItems.reduce((sum, item) => sum + item.lorebookCount, 0)
  const totalStatus = libraryItems.reduce((sum, item) => sum + item.statusTableCount, 0)
  const totalSceneStatus = libraryItems.reduce((sum, item) => sum + item.sceneStatusCount, 0)

  const createSessionMutation = useMutation({
    mutationFn: (story: StoryLibraryViewItem) => {
      if (!currentWorkspace) throw new Error('workspace missing')
      return createSession(currentWorkspace, story.id, `${story.title} 新会话`)
    },
    onSuccess: (session) => {
      queryClient.invalidateQueries({ queryKey: ['play-story-library-aggregate', currentWorkspace] })
      router.push(`/session/${session.id}`)
    },
  })

  function openCreateStory() {
    router.push('/stories/new')
  }

  function openEditStory(story: StorySummary | null) {
    if (!story) return
    router.push(`/stories/${story.id}/edit`)
  }

  function playStory(story: StoryLibraryViewItem | null) {
    if (!story) return
    if (story.latestSession) {
      router.push(`/session/${story.latestSession.id}`)
      return
    }
    createSessionMutation.mutate(story)
  }

  return (
    <div className="min-w-0 px-5 py-8 xl:px-7">
      <section className="mb-6 grid gap-4 xl:grid-cols-[minmax(0,1fr)_auto] xl:items-end">
        <div>
          <p className="mb-2 flex items-center gap-2 text-sm font-black text-slate-500">
            <span className="h-2.5 w-2.5 rounded-full bg-teal-500" />
            {currentWorkspace ?? '未选择 workspace'} / Play catalog
          </p>
          <h1 className="text-3xl font-black text-slate-950">故事库</h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-500">
            管理 story 主数据、开场模板、角色与世界书挂载，并从这里按全局 session_id 进入游玩会话。
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={openCreateStory}
            disabled={!currentWorkspace}
            className="flex h-10 items-center gap-2 rounded-lg bg-slate-950 px-4 text-sm font-black text-white shadow-lg shadow-slate-200 transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
          >
            <FilePlus2 size={16} />
            新建故事
          </button>
        </div>
      </section>

      <section className="mb-5 grid gap-3 xl:grid-cols-[minmax(280px,1fr)_auto_auto] xl:items-center" aria-label="筛选故事">
        <label className="flex h-11 items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-500 shadow-sm focus-within:border-teal-300 focus-within:ring-4 focus-within:ring-teal-100">
          <Search size={17} />
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="搜索故事标题、摘要、角色、世界书条目"
            className="min-w-0 flex-1 bg-transparent text-slate-900 outline-none placeholder:text-slate-400"
          />
        </label>
        <div className="inline-flex rounded-lg border border-slate-200 bg-white p-1 shadow-sm" role="tablist" aria-label="故事状态">
          {[
            ['all', '全部'],
            [STORY_COMPUTED_STATUS.LIVE, '进行中'],
            [STORY_COMPUTED_STATUS.DRAFT, '未开始'],
          ].map(([value, label]) => (
            <button
              key={value}
              type="button"
              onClick={() => setFilter(value as StoryFilter)}
              className={cn(
                'h-8 rounded-md px-3 text-xs font-black transition',
                filter === value ? 'bg-slate-950 text-white' : 'text-slate-500 hover:bg-slate-50 hover:text-slate-950',
              )}
            >
              {label}
            </button>
          ))}
        </div>
        <select
          value={sort}
          onChange={(event) => setSort(event.target.value as StorySort)}
          className="h-11 rounded-lg border border-slate-200 bg-white px-3 text-sm font-bold text-slate-700 shadow-sm outline-none transition focus:border-teal-300 focus:ring-4 focus:ring-teal-100"
          aria-label="排序"
        >
          <option value="active">最近活跃优先</option>
          <option value="updated">最近更新优先</option>
          <option value="title">故事标题 A-Z</option>
          <option value="sessions">会话数量优先</option>
        </select>
      </section>

      <section className="mb-6 grid gap-3 md:grid-cols-2 2xl:grid-cols-4" aria-label="故事库概览">
        <MetricCard label="故事" value={libraryItems.length} note={`${liveCount} 个进行中，${draftCount} 个未开始`} icon={BookOpen} />
        <MetricCard label="挂载角色" value={totalCharacters} note="来自 story 角色挂载表" icon={UsersRound} />
        <MetricCard label="世界书条目" value={totalLorebook} note="跨 story 可复用挂载" icon={Globe2} />
        <MetricCard label="状态表模板" value={totalStatus} note={`scene 模板 ${totalSceneStatus} 张`} icon={TableProperties} />
      </section>

      {!currentWorkspace ? (
        <section className="rounded-lg border border-dashed border-slate-300 bg-white/70 px-6 py-12 text-center text-sm font-semibold text-slate-500">
          请选择 workspace 后查看故事库
        </section>
      ) : storiesQuery.isError ? (
        <section className="rounded-lg border border-rose-200 bg-rose-50 px-6 py-6 text-sm font-semibold text-rose-700">
          故事库加载失败：{storiesQuery.error instanceof Error ? storiesQuery.error.message : '未知错误'}
        </section>
      ) : storiesQuery.isLoading ? (
        <section className="grid gap-4 md:grid-cols-2 2xl:grid-cols-3">
          {[0, 1, 2, 3, 4, 5].map((item) => <StorySkeleton key={item} />)}
        </section>
      ) : libraryItems.length === 0 ? (
        <section className="rounded-lg border border-dashed border-slate-300 bg-white/70 px-6 py-12 text-center">
          <Sparkles size={28} className="mx-auto text-teal-600" />
          <h2 className="mt-3 text-lg font-black text-slate-950">还没有故事</h2>
          <p className="mt-2 text-sm font-semibold text-slate-500">新建一个 story 后即可绑定角色、世界书、状态表并创建会话。</p>
          <button
            type="button"
            onClick={openCreateStory}
            className="mt-5 inline-flex h-10 items-center gap-2 rounded-lg bg-slate-950 px-4 text-sm font-black text-white transition hover:bg-slate-800"
          >
            <FilePlus2 size={16} />
            新建故事
          </button>
        </section>
      ) : (
        <section>
          {aggregatesLoading ? (
            <p className="mb-3 flex items-center gap-2 text-xs font-bold text-slate-400">
              <Loader2 size={14} className="animate-spin" />
              正在补齐挂载资源和最近会话
            </p>
          ) : null}
          {filteredItems.length ? (
            <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-3" aria-label="故事列表">
              {filteredItems.map((item) => (
                <StoryCard
                  key={item.id}
                  item={item}
                  loading={aggregateQueries[stories.findIndex((story) => story.id === item.id)]?.isLoading ?? false}
                  sessionPending={createSessionMutation.isPending && createSessionMutation.variables?.id === item.id}
                  onEdit={() => openEditStory(item)}
                  onPlay={() => playStory(item)}
                />
              ))}
            </div>
          ) : (
            <section className="rounded-lg border border-dashed border-slate-300 bg-white/70 px-6 py-12 text-center text-sm font-semibold text-slate-500">
              没有匹配当前搜索和筛选的故事
            </section>
          )}
        </section>
      )}
    </div>
  )
}

export function StoriesPage() {
  return (
    <AppShell>
      <StoriesContent />
    </AppShell>
  )
}
