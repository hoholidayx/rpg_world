'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeft,
  CheckCircle2,
  Globe2,
  Loader2,
  Play,
  Save,
  TableProperties,
  Trash2,
  UsersRound,
} from 'lucide-react'
import { AppShell, useAppShell } from '@/features/layout/AppShell'
import { listStoryCharacters, unmountCharacter } from '@/lib/api/characters'
import { listStoryLorebookEntries, unmountLorebookEntry } from '@/lib/api/lorebook'
import { listSessions } from '@/lib/api/sessions'
import { createStory, listStories, updateStory } from '@/lib/api/stories'
import { listStoryStatusMounts, unmountStatusTemplate } from '@/lib/api/statusTables'
import { cn } from '@/lib/utils/cn'
import type { CharacterCard } from '@/types/characters'
import type { LorebookEntry } from '@/types/lorebook'
import type { SessionSummary } from '@/types/session'
import type { StoryStatusMount } from '@/types/statusTables'
import type { StoryInput, StorySummary } from '@/types/story'

type DraftState = StoryInput

const emptyDraft: DraftState = {
  title: '',
  summary: '',
  firstMessage: '',
  storyPrompt: '',
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

function firstLetter(value: string) {
  return value.trim().slice(0, 1).toUpperCase() || '#'
}

function draftFromStory(story: StorySummary): DraftState {
  return {
    title: story.title,
    summary: story.summary ?? '',
    firstMessage: story.firstMessage ?? '',
    storyPrompt: story.storyPrompt ?? '',
  }
}

function isDirty(story: StorySummary | null, draft: DraftState) {
  if (!story) return false
  const original = draftFromStory(story)
  return (
    original.title !== draft.title
    || original.summary !== draft.summary
    || original.firstMessage !== draft.firstMessage
    || original.storyPrompt !== draft.storyPrompt
  )
}

function dirtyFields(story: StorySummary | null, draft: DraftState) {
  if (!story) return []
  const original = draftFromStory(story)
  return [
    original.title !== draft.title ? 'title' : '',
    original.summary !== draft.summary ? 'summary' : '',
    original.firstMessage !== draft.firstMessage ? 'first_message' : '',
    original.storyPrompt !== draft.storyPrompt ? 'story_prompt' : '',
  ].filter(Boolean)
}

function parseDraft(value: string | null): DraftState | null {
  if (!value) return null
  try {
    const parsed = JSON.parse(value)
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return null
    const input = parsed as Partial<DraftState>
    return {
      title: typeof input.title === 'string' ? input.title : '',
      summary: typeof input.summary === 'string' ? input.summary : '',
      firstMessage: typeof input.firstMessage === 'string' ? input.firstMessage : '',
      storyPrompt: typeof input.storyPrompt === 'string' ? input.storyPrompt : '',
    }
  } catch {
    return null
  }
}

function sortSessions(sessions: SessionSummary[]) {
  return [...sessions].sort((first, second) => {
    const firstTime = Math.max(getTimestamp(first.updatedAt), getTimestamp(first.createdAt))
    const secondTime = Math.max(getTimestamp(second.updatedAt), getTimestamp(second.createdAt))
    return secondTime - firstTime
  })
}

function FieldShell({
  label,
  hint,
  children,
  full = false,
}: {
  label: string
  hint: string
  children: React.ReactNode
  full?: boolean
}) {
  return (
    <label className={cn('min-w-0', full ? 'md:col-span-2' : '')}>
      <span className="mb-2 flex items-center justify-between gap-3 text-xs font-black uppercase text-slate-500">
        <span>{label}</span>
        <span>{hint}</span>
      </span>
      {children}
    </label>
  )
}

function Panel({
  title,
  description,
  action,
  children,
}: {
  title: string
  description?: string
  action?: React.ReactNode
  children: React.ReactNode
}) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white shadow-sm">
      <header className="flex items-start justify-between gap-4 border-b border-slate-200 bg-white px-5 py-4">
        <div className="min-w-0">
          <h2 className="text-lg font-black text-slate-950">{title}</h2>
          {description ? <p className="mt-1 text-sm leading-6 text-slate-500">{description}</p> : null}
        </div>
        {action}
      </header>
      <div className="p-5">{children}</div>
    </section>
  )
}

function Chip({
  children,
  tone = 'slate',
}: {
  children: React.ReactNode
  tone?: 'slate' | 'teal' | 'violet' | 'amber'
}) {
  const className = {
    slate: 'bg-slate-100 text-slate-600',
    teal: 'bg-teal-100 text-teal-700',
    violet: 'bg-violet-100 text-violet-700',
    amber: 'bg-amber-100 text-amber-700',
  }[tone]

  return (
    <span className={cn('inline-flex min-h-8 items-center rounded-full px-3 text-xs font-black', className)}>
      {children}
    </span>
  )
}

function AssetRow({
  name,
  meta,
  chip,
  tone,
  pending,
  onRemove,
}: {
  name: string
  meta: string
  chip: string
  tone: 'teal' | 'violet' | 'amber' | 'slate'
  pending?: boolean
  onRemove?: () => void
}) {
  const avatarClass = {
    teal: 'bg-teal-100 text-teal-700',
    violet: 'bg-violet-100 text-violet-700',
    amber: 'bg-amber-100 text-amber-700',
    slate: 'bg-slate-100 text-slate-600',
  }[tone]

  return (
    <div className="grid min-h-14 grid-cols-[38px_minmax(0,1fr)_auto] items-center gap-3 rounded-lg border border-slate-200 bg-white px-3 py-2">
      <span className={cn('flex h-10 w-10 items-center justify-center rounded-lg text-sm font-black', avatarClass)}>{firstLetter(name)}</span>
      <span className="min-w-0">
        <span className="block truncate text-sm font-black text-slate-950">{name}</span>
        <span className="mt-1 block truncate text-xs font-semibold text-slate-400">{meta}</span>
      </span>
      {onRemove ? (
        <button
          type="button"
          disabled={pending}
          onClick={onRemove}
          className="flex h-8 items-center gap-1 rounded-lg border border-slate-200 bg-white px-2 text-xs font-black text-slate-500 transition hover:border-rose-200 hover:text-rose-600 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {pending ? <Loader2 size={13} className="animate-spin" /> : <Trash2 size={13} />}
          移除
        </button>
      ) : (
        <span className="rounded-full bg-slate-100 px-2 py-1 text-[11px] font-black text-slate-500">{chip}</span>
      )}
    </div>
  )
}

function StatCard({
  value,
  label,
}: {
  value: number
  label: string
}) {
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
      <b className="block text-2xl leading-none text-slate-950">{value}</b>
      <span className="mt-2 block text-xs font-black text-slate-500">{label}</span>
    </div>
  )
}

function StoryEditContent({
  storyId,
  mode,
}: {
  storyId?: number
  mode: 'create' | 'edit'
}) {
  const router = useRouter()
  const queryClient = useQueryClient()
  const { currentWorkspace } = useAppShell()
  const isCreate = mode === 'create'
  const [draft, setDraft] = useState<DraftState>(emptyDraft)
  const [draftReady, setDraftReady] = useState(false)
  const [draftSavedAt, setDraftSavedAt] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const storiesQuery = useQuery({
    queryKey: ['play-stories', currentWorkspace],
    queryFn: () => listStories(currentWorkspace ?? ''),
    enabled: Boolean(currentWorkspace && !isCreate && Number.isFinite(storyId)),
  })
  const stories = storiesQuery.data ?? []
  const story = isCreate ? null : stories.find((item) => item.id === storyId) ?? null
  const draftStorageKey = currentWorkspace
    ? isCreate ? `play-story-create-draft:${currentWorkspace}` : `play-story-edit-draft:${currentWorkspace}:${storyId}`
    : null

  const charactersQuery = useQuery({
    queryKey: ['play-story-characters', currentWorkspace, storyId],
    queryFn: () => listStoryCharacters(currentWorkspace ?? '', storyId ?? 0),
    enabled: Boolean(currentWorkspace && story && !isCreate && storyId !== undefined),
  })
  const lorebookQuery = useQuery({
    queryKey: ['play-story-lorebook', currentWorkspace, storyId],
    queryFn: () => listStoryLorebookEntries(currentWorkspace ?? '', storyId ?? 0),
    enabled: Boolean(currentWorkspace && story && !isCreate && storyId !== undefined),
  })
  const statusMountsQuery = useQuery({
    queryKey: ['play-story-status-mounts', currentWorkspace, storyId],
    queryFn: () => listStoryStatusMounts(currentWorkspace ?? '', storyId ?? 0),
    enabled: Boolean(currentWorkspace && story && !isCreate && storyId !== undefined),
  })
  const sessionsQuery = useQuery({
    queryKey: ['play-sessions', currentWorkspace, storyId],
    queryFn: () => listSessions(currentWorkspace ?? '', storyId ?? 0),
    enabled: Boolean(currentWorkspace && story && !isCreate && storyId !== undefined),
  })

  const characters = charactersQuery.data ?? []
  const lorebookEntries = lorebookQuery.data ?? []
  const statusMounts = statusMountsQuery.data ?? []
  const sessions = useMemo(() => sortSessions(sessionsQuery.data ?? []), [sessionsQuery.data])
  const sceneMountCount = statusMounts.filter((mount) => mount.statusKind === 'scene').length
  const dirty = isCreate
    ? Boolean(draft.title.trim() || draft.summary || draft.firstMessage || draft.storyPrompt)
    : isDirty(story, draft)
  const changedFields = isCreate
    ? ['new_story_draft']
    : dirtyFields(story, draft)

  useEffect(() => {
    if (!isCreate || !draftStorageKey) return
    const savedDraft = parseDraft(window.localStorage.getItem(draftStorageKey))
    setDraft(savedDraft ?? emptyDraft)
    setDraftReady(true)
    setDraftSavedAt(savedDraft ? new Date().toISOString() : null)
  }, [draftStorageKey, isCreate])

  useEffect(() => {
    if (isCreate || !story || !draftStorageKey) return
    const savedDraft = parseDraft(window.localStorage.getItem(draftStorageKey))
    setDraft(savedDraft ?? draftFromStory(story))
    setDraftReady(true)
    setDraftSavedAt(savedDraft ? new Date().toISOString() : null)
  }, [draftStorageKey, isCreate, story])

  useEffect(() => {
    if (!draftStorageKey || !draftReady) return
    if (!dirty) {
      window.localStorage.removeItem(draftStorageKey)
      setDraftSavedAt(null)
      return
    }
    window.localStorage.setItem(draftStorageKey, JSON.stringify(draft))
    setDraftSavedAt(new Date().toISOString())
  }, [draft, draftReady, draftStorageKey, dirty])

  function invalidateStoryEditData() {
    queryClient.invalidateQueries({ queryKey: ['play-stories', currentWorkspace] })
    if (storyId === undefined) return
    queryClient.invalidateQueries({ queryKey: ['play-story-characters', currentWorkspace, storyId] })
    queryClient.invalidateQueries({ queryKey: ['play-story-lorebook', currentWorkspace, storyId] })
    queryClient.invalidateQueries({ queryKey: ['play-story-status-mounts', currentWorkspace, storyId] })
    queryClient.invalidateQueries({ queryKey: ['play-story-library-aggregate', currentWorkspace, storyId] })
  }

  const saveMutation = useMutation({
    mutationFn: () => {
      if (!currentWorkspace) throw new Error('workspace missing')
      const input = {
        title: draft.title.trim(),
        summary: draft.summary,
        firstMessage: draft.firstMessage,
        storyPrompt: draft.storyPrompt,
      }
      if (isCreate) return createStory(currentWorkspace, input)
      if (!story) throw new Error('story missing')
      return updateStory(currentWorkspace, story.id, input)
    },
    onSuccess: (updated) => {
      setError(null)
      if (draftStorageKey) window.localStorage.removeItem(draftStorageKey)
      queryClient.setQueryData<StorySummary[]>(['play-stories', currentWorkspace], (current) => {
        const stories = current ?? []
        return stories.some((item) => item.id === updated.id)
          ? stories.map((item) => item.id === updated.id ? updated : item)
          : [updated, ...stories]
      })
      if (isCreate) {
        setDraftReady(false)
        setDraft(emptyDraft)
        router.replace(`/stories/${updated.id}/edit`)
        return
      }
      setDraft(draftFromStory(updated))
      queryClient.invalidateQueries({ queryKey: ['play-story-library-aggregate', currentWorkspace, storyId] })
    },
    onError: (reason) => setError(reason instanceof Error ? reason.message : isCreate ? '新建故事失败' : '保存故事失败'),
  })

  const unmountCharacterMutation = useMutation({
    mutationFn: (mountId: number) => {
      if (!currentWorkspace) throw new Error('workspace missing')
      return unmountCharacter(currentWorkspace, storyId ?? 0, mountId)
    },
    onSuccess: invalidateStoryEditData,
  })

  const unmountLorebookMutation = useMutation({
    mutationFn: (mountId: number) => {
      if (!currentWorkspace) throw new Error('workspace missing')
      return unmountLorebookEntry(currentWorkspace, storyId ?? 0, mountId)
    },
    onSuccess: invalidateStoryEditData,
  })

  const unmountStatusMutation = useMutation({
    mutationFn: (mountId: number) => {
      if (!currentWorkspace) throw new Error('workspace missing')
      return unmountStatusTemplate(currentWorkspace, storyId ?? 0, mountId)
    },
    onSuccess: invalidateStoryEditData,
  })

  function discardChanges() {
    setDraft(story ? draftFromStory(story) : emptyDraft)
    setError(null)
    if (draftStorageKey) window.localStorage.removeItem(draftStorageKey)
  }

  function saveStory() {
    if (!draft.title.trim()) {
      setError('title 不能为空')
      return
    }
    saveMutation.mutate()
  }

  if (!isCreate && !Number.isFinite(storyId)) {
    return (
      <div className="min-w-0 px-5 py-8 xl:px-7">
        <Link href="/stories" className="inline-flex h-10 items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 text-sm font-black text-slate-500">
          <ArrowLeft size={16} />
          返回故事库
        </Link>
        <section className="mt-6 rounded-lg border border-rose-200 bg-rose-50 px-6 py-6 text-sm font-semibold text-rose-700">
          story id 无效
        </section>
      </div>
    )
  }

  return (
    <div className="min-w-0 px-5 py-8 xl:px-7">
      <div className="mb-5 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <Link
          href="/stories"
          className="inline-flex h-10 w-fit items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 text-sm font-black text-slate-500 shadow-sm transition hover:border-teal-300 hover:text-teal-700"
        >
          <ArrowLeft size={16} />
          返回故事库
        </Link>
        <div className="flex items-center gap-2 text-sm font-bold text-slate-500">
          <span className={cn('h-2.5 w-2.5 rounded-full', dirty ? 'bg-amber-500' : 'bg-emerald-500')} />
          {dirty ? `自动保存草稿 · ${formatDate(draftSavedAt)}` : `已同步 · ${formatDate(story?.updatedAt)}`}
        </div>
      </div>

      {storiesQuery.isLoading ? (
        <section className="rounded-lg border border-slate-200 bg-white px-6 py-12 text-center text-sm font-semibold text-slate-500">
          <Loader2 size={20} className="mx-auto mb-3 animate-spin" />
          正在加载故事
        </section>
      ) : !isCreate && storiesQuery.isError ? (
        <section className="rounded-lg border border-rose-200 bg-rose-50 px-6 py-6 text-sm font-semibold text-rose-700">
          故事加载失败：{storiesQuery.error instanceof Error ? storiesQuery.error.message : '未知错误'}
        </section>
      ) : !isCreate && !story ? (
        <section className="rounded-lg border border-dashed border-slate-300 bg-white/70 px-6 py-12 text-center text-sm font-semibold text-slate-500">
          当前 workspace 下没有找到 story #{storyId}
        </section>
      ) : (
        <>
          <section className="mb-5 overflow-hidden rounded-lg border border-slate-200 bg-white shadow-lg shadow-slate-200/70">
            <div className="relative min-h-44 bg-gradient-to-br from-slate-800 via-slate-600 to-cyan-100">
              <div className="absolute bottom-[-26px] left-10 h-28 w-36 rounded-t-full bg-white/15" />
              <div className="absolute bottom-0 left-32 h-28 w-10 rounded-t-full bg-white/65 shadow-[86px_30px_0_-10px_rgba(255,255,255,0.42),168px_22px_0_-12px_rgba(255,255,255,0.30)]" />
              <div className="relative z-10 grid min-h-44 gap-5 p-6 md:grid-cols-[minmax(0,1fr)_auto] md:items-end">
                <div className="min-w-0">
                  <p className="mb-2 flex items-center gap-2 text-sm font-black text-white/80">
                    <span className="h-2.5 w-2.5 rounded-full bg-teal-300" />
                    {currentWorkspace} / {isCreate ? 'new story' : `story #${story?.id}`}
                  </p>
                  <h1 className="truncate text-4xl font-black leading-tight text-white">{draft.title || (isCreate ? '未命名故事' : story?.title)}</h1>
                  <p className="mt-3 max-w-3xl text-sm leading-7 text-white/85">{draft.summary || '暂无故事摘要'}</p>
                </div>
                <div className="flex flex-wrap gap-2 md:justify-end">
                  <button
                    type="button"
                    onClick={saveStory}
                    disabled={!dirty || saveMutation.isPending}
                    className="inline-flex h-10 items-center gap-2 rounded-lg bg-indigo-600 px-4 text-sm font-black text-white shadow-lg shadow-slate-950/20 transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {saveMutation.isPending ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
                    保存故事
                  </button>
                </div>
              </div>
            </div>
          </section>

          <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px] xl:items-start">
            <div className="space-y-4">
              <Panel
                title="主数据"
                description="这些字段来自 rpg_stories，用于故事列表、会话创建和固定叙事配置。"
                action={<Chip tone={sessions.length ? 'teal' : 'amber'}>{sessions.length ? 'active' : 'draft'}</Chip>}
              >
                <div className="grid gap-4 md:grid-cols-2">
                  <FieldShell label="title" hint="必填">
                    <input
                      value={draft.title}
                      onChange={(event) => setDraft((current) => ({ ...current, title: event.target.value }))}
                      className="h-11 w-full rounded-lg border border-slate-200 bg-slate-50 px-3 text-sm font-semibold text-slate-900 outline-none transition focus:border-teal-300 focus:ring-4 focus:ring-teal-100"
                    />
                  </FieldShell>
                  <FieldShell label="workspace_id" hint="只读">
                    <input
                      value={currentWorkspace ?? ''}
                      readOnly
                      className="h-11 w-full rounded-lg border border-slate-200 bg-slate-100 px-3 text-sm font-semibold text-slate-500 outline-none"
                    />
                  </FieldShell>
                  <FieldShell label="summary" hint="短摘要" full>
                    <textarea
                      value={draft.summary}
                      onChange={(event) => setDraft((current) => ({ ...current, summary: event.target.value }))}
                      className="min-h-28 w-full resize-y rounded-lg border border-slate-200 bg-slate-50 px-3 py-3 text-sm leading-7 text-slate-800 outline-none transition focus:border-teal-300 focus:ring-4 focus:ring-teal-100"
                    />
                    <p className="mt-2 text-xs font-semibold leading-5 text-slate-400">建议控制在 1-2 句，用于故事库卡片和会话创建时的上下文说明。</p>
                  </FieldShell>
                </div>
              </Panel>

              <Panel
                title="开场与固定提示词"
                description="first_message 用于新会话开场模板；story_prompt 当前只存储和经 API 返回，后续再接入 fix layer。"
                action={<Chip tone="violet">rpg_stories</Chip>}
              >
                <div className="grid gap-4">
                  <FieldShell label="first_message" hint="会话开场" full>
                    <textarea
                      value={draft.firstMessage}
                      onChange={(event) => setDraft((current) => ({ ...current, firstMessage: event.target.value }))}
                      className="min-h-28 w-full resize-y rounded-lg border border-slate-200 bg-slate-50 px-3 py-3 text-sm leading-7 text-slate-800 outline-none transition focus:border-teal-300 focus:ring-4 focus:ring-teal-100"
                    />
                  </FieldShell>
                  <FieldShell label="story_prompt" hint="固定故事提示词" full>
                    <textarea
                      value={draft.storyPrompt}
                      onChange={(event) => setDraft((current) => ({ ...current, storyPrompt: event.target.value }))}
                      className="min-h-44 w-full resize-y rounded-lg border border-slate-200 bg-slate-50 px-3 py-3 font-mono text-sm leading-7 text-slate-800 outline-none transition focus:border-teal-300 focus:ring-4 focus:ring-teal-100"
                    />
                    <p className="mt-2 text-xs font-semibold leading-5 text-slate-400">落地注意：不要在本次设计里假设 story_prompt 已参与 ContextRenderer。</p>
                  </FieldShell>
                </div>
              </Panel>

              <Panel
                title="挂载资产"
                description="角色、世界书和状态表都是 workspace 资产；只有挂载到 story 后才会被 session 感知。"
                action={(
                  <Link href="/characters" className="inline-flex h-10 items-center rounded-lg border border-slate-200 bg-white px-4 text-sm font-black text-slate-700 transition hover:border-teal-300 hover:text-teal-700">
                    管理挂载
                  </Link>
                )}
              >
                <div className="grid gap-4 lg:grid-cols-2">
                  <section>
                    <div className="mb-2 flex items-center justify-between gap-3 text-xs font-black uppercase text-slate-500">
                      <span>角色</span>
                      <span>rpg_story_characters</span>
                    </div>
                    <div className="grid gap-2">
                      {isCreate ? <p className="rounded-lg border border-dashed border-slate-200 px-4 py-6 text-center text-sm font-semibold text-slate-400">保存故事后可挂载角色</p> : null}
                      {!isCreate && charactersQuery.isLoading ? <AssetRow name="加载中" meta="正在读取角色挂载" chip="角色" tone="teal" /> : null}
                      {characters.map((character: CharacterCard) => (
                        <AssetRow
                          key={character.mountId ?? character.id}
                          name={character.name}
                          meta={character.personality || character.content || `character #${character.id}`}
                          chip="角色"
                          tone="teal"
                          pending={unmountCharacterMutation.isPending && unmountCharacterMutation.variables === character.mountId}
                          onRemove={character.mountId ? () => unmountCharacterMutation.mutate(character.mountId as number) : undefined}
                        />
                      ))}
                      {!isCreate && !charactersQuery.isLoading && !characters.length ? <p className="rounded-lg border border-dashed border-slate-200 px-4 py-6 text-center text-sm font-semibold text-slate-400">暂无角色挂载</p> : null}
                    </div>
                  </section>

                  <section>
                    <div className="mb-2 flex items-center justify-between gap-3 text-xs font-black uppercase text-slate-500">
                      <span>世界书</span>
                      <span>rpg_story_lorebook_entries</span>
                    </div>
                    <div className="grid gap-2">
                      {isCreate ? <p className="rounded-lg border border-dashed border-slate-200 px-4 py-6 text-center text-sm font-semibold text-slate-400">保存故事后可挂载世界书</p> : null}
                      {!isCreate && lorebookQuery.isLoading ? <AssetRow name="加载中" meta="正在读取世界书挂载" chip="世界书" tone="violet" /> : null}
                      {lorebookEntries.map((entry: LorebookEntry) => (
                        <AssetRow
                          key={entry.mountId ?? entry.id}
                          name={entry.name}
                          meta={entry.description || entry.content || `entry #${entry.id}`}
                          chip="世界书"
                          tone="violet"
                          pending={unmountLorebookMutation.isPending && unmountLorebookMutation.variables === entry.mountId}
                          onRemove={entry.mountId ? () => unmountLorebookMutation.mutate(entry.mountId as number) : undefined}
                        />
                      ))}
                      {!isCreate && !lorebookQuery.isLoading && !lorebookEntries.length ? <p className="rounded-lg border border-dashed border-slate-200 px-4 py-6 text-center text-sm font-semibold text-slate-400">暂无世界书挂载</p> : null}
                    </div>
                  </section>

                  <section className="lg:col-span-2">
                    <div className="mb-2 flex items-center justify-between gap-3 text-xs font-black uppercase text-slate-500">
                      <span>状态表模板</span>
                      <span>rpg_story_status_tables</span>
                    </div>
                    <div className="grid gap-2">
                      {isCreate ? <p className="rounded-lg border border-dashed border-slate-200 px-4 py-6 text-center text-sm font-semibold text-slate-400">保存故事后可挂载状态表模板</p> : null}
                      {!isCreate && statusMountsQuery.isLoading ? <AssetRow name="加载中" meta="正在读取状态表挂载" chip="状态表" tone="amber" /> : null}
                      {statusMounts.map((mount: StoryStatusMount) => (
                        <AssetRow
                          key={mount.id}
                          name={mount.tableName}
                          meta={`status_kind ${mount.statusKind} · 创建 session 时复制 document_json`}
                          chip={mount.statusKind}
                          tone={mount.statusKind === 'scene' ? 'teal' : 'amber'}
                          pending={unmountStatusMutation.isPending && unmountStatusMutation.variables === mount.id}
                          onRemove={() => unmountStatusMutation.mutate(mount.id)}
                        />
                      ))}
                      {!isCreate && !statusMountsQuery.isLoading && !statusMounts.length ? <p className="rounded-lg border border-dashed border-slate-200 px-4 py-6 text-center text-sm font-semibold text-slate-400">暂无状态表模板挂载</p> : null}
                    </div>
                  </section>
                </div>
              </Panel>
            </div>

            <aside className="space-y-4 xl:sticky xl:top-24">
              <Panel title="发布状态" description="保存后影响后续新建 session；已有 session 使用自己的运行时副本。">
                <div className="grid grid-cols-2 gap-3">
                  <StatCard value={sessions.length} label="sessions" />
                  <StatCard value={characters.length} label="characters" />
                  <StatCard value={lorebookEntries.length} label="lorebook" />
                  <StatCard value={statusMounts.length} label="status tables" />
                </div>
                <div className="mt-4 flex flex-wrap gap-2">
                  {sceneMountCount ? <Chip tone="teal">scene 已挂载</Chip> : <Chip tone="amber">scene 未挂载</Chip>}
                  <Chip tone="violet">story_prompt stored</Chip>
                  <Chip tone="amber">{sessions.length} active sessions</Chip>
                </div>
              </Panel>

              <Panel title="最近会话" description="会话内链路只使用全局短 session_id。">
                <div className="grid gap-2">
                  {sessionsQuery.isLoading ? <AssetRow name="加载中" meta="正在读取最近会话" chip="session" tone="slate" /> : null}
                  {sessions.slice(0, 4).map((session) => (
                    <button
                      key={session.id}
                      type="button"
                      onClick={() => router.push(`/session/${session.id}`)}
                      className="grid min-h-14 grid-cols-[38px_minmax(0,1fr)_auto] items-center gap-3 rounded-lg border border-slate-200 bg-white px-3 py-2 text-left transition hover:border-teal-300 hover:text-teal-700"
                    >
                      <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-teal-100 text-sm font-black text-teal-700">S</span>
                      <span className="min-w-0">
                        <span className="block truncate text-sm font-black text-slate-950">{session.title || session.id}</span>
                        <span className="mt-1 block truncate text-xs font-semibold text-slate-400">{session.id} · {formatDate(session.updatedAt)}</span>
                      </span>
                      <Play size={15} />
                    </button>
                  ))}
                  {!sessionsQuery.isLoading && !sessions.length ? <p className="rounded-lg border border-dashed border-slate-200 px-4 py-6 text-center text-sm font-semibold text-slate-400">暂无会话</p> : null}
                </div>
              </Panel>
            </aside>
          </div>

          {error ? (
            <section className="mt-5 rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-semibold text-rose-700">{error}</section>
          ) : null}

          <section className="mt-5 flex flex-col gap-3 rounded-lg border border-slate-200 bg-white/90 p-3 shadow-lg shadow-slate-200/70 backdrop-blur md:flex-row md:items-center md:justify-between">
            <div className="text-sm font-bold text-slate-500">
              {dirty ? `未提交更改：${changedFields.join('、')}` : '没有未提交更改'}
            </div>
            <div className="flex flex-wrap gap-2 md:justify-end">
              <button
                type="button"
                onClick={discardChanges}
                disabled={!dirty || saveMutation.isPending}
                className="h-10 rounded-lg border border-slate-200 bg-white px-4 text-sm font-black text-slate-700 transition hover:border-teal-300 hover:text-teal-700 disabled:cursor-not-allowed disabled:opacity-60"
              >
                放弃更改
              </button>
              <button
                type="button"
                onClick={saveStory}
                disabled={!dirty || saveMutation.isPending}
                className="inline-flex h-10 items-center gap-2 rounded-lg bg-indigo-600 px-4 text-sm font-black text-white transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {saveMutation.isPending ? <Loader2 size={16} className="animate-spin" /> : <CheckCircle2 size={16} />}
                保存故事
              </button>
            </div>
          </section>
        </>
      )}
    </div>
  )
}

export function StoryEditPage({
  storyId,
  mode = 'edit',
}: {
  storyId?: number
  mode?: 'create' | 'edit'
}) {
  return (
    <AppShell>
      <StoryEditContent storyId={storyId} mode={mode} />
    </AppShell>
  )
}
