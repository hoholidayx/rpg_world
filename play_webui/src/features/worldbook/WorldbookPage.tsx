'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Bold,
  ImagePlus,
  Check,
  Eye,
  FilePlus2,
  Italic,
  List,
  Loader2,
  Plus,
  Save,
  Search,
  UploadCloud,
  X,
  Trash2,
  Type,
} from 'lucide-react'
import { AppShell, useAppShell } from '@/features/layout/AppShell'
import {
  createLorebookEntry,
  deleteLorebookEntry,
  listLorebookEntries,
  listStories,
  listStoryLorebookEntries,
  mountLorebookEntry,
  unmountLorebookEntry,
  updateLorebookEntry,
} from '@/lib/api/lorebook'
import type { LorebookEntry, LorebookEntryInput, StorySummary } from '@/types/lorebook'

type Draft = LorebookEntryInput & {
  metadataText: string
}

const emptyDraft: Draft = {
  name: '',
  description: '',
  content: '',
  tags: [],
  metadata: {},
  metadataText: '{\n  "ui": {}\n}',
}

function formatDate(value?: string | null) {
  if (!value) return '暂无'
  return value.replace('T', ' ').slice(0, 16)
}

function draftFromEntry(entry: LorebookEntry | null): Draft {
  if (!entry) return emptyDraft
  return {
    name: entry.name,
    description: entry.description,
    content: entry.content,
    tags: entry.tags,
    metadata: entry.metadata,
    metadataText: JSON.stringify(entry.metadata ?? {}, null, 2),
  }
}

function metadataVersion(entry: LorebookEntry | null) {
  const ui = entry?.metadata?.ui
  if (ui && typeof ui === 'object' && 'displayVersion' in ui) {
    const value = (ui as { displayVersion?: unknown }).displayVersion
    if (typeof value === 'string' && value) return value
  }
  return `v${entry?.version ?? 1}`
}

function getThumbnailUrl(metadata: Record<string, unknown> | undefined) {
  const ui = metadata?.ui
  if (ui && typeof ui === 'object' && 'thumbnailUrl' in ui) {
    const value = (ui as { thumbnailUrl?: unknown }).thumbnailUrl
    if (typeof value === 'string' && value) return value
  }
  return ''
}

function setMetadataThumbnail(metadataText: string, thumbnailUrl: string) {
  let metadata: Record<string, unknown> = {}
  try {
    const parsed = JSON.parse(metadataText || '{}')
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      metadata = parsed as Record<string, unknown>
    }
  } catch {
    metadata = {}
  }
  const ui = metadata.ui && typeof metadata.ui === 'object' && !Array.isArray(metadata.ui)
    ? { ...(metadata.ui as Record<string, unknown>) }
    : {}
  if (thumbnailUrl) {
    ui.thumbnailUrl = thumbnailUrl
  } else {
    delete ui.thumbnailUrl
  }
  metadata.ui = ui
  return JSON.stringify(metadata, null, 2)
}

function parseMetadataObject(metadataText: string) {
  try {
    const parsed = JSON.parse(metadataText || '{}')
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed as Record<string, unknown> : {}
  } catch {
    return {}
  }
}

function readFileAsDataUrl(file: File) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result || ''))
    reader.onerror = () => reject(reader.error)
    reader.readAsDataURL(file)
  })
}

const fallbackThumbnailClass = 'from-slate-700 via-slate-500 to-indigo-200'

function EntryVisual({ entry }: { entry: LorebookEntry }) {
  const thumbnailUrl = getThumbnailUrl(entry.metadata)
  return (
    <div className={`relative h-16 w-16 shrink-0 overflow-hidden rounded-xl bg-gradient-to-br ${fallbackThumbnailClass}`}>
      {thumbnailUrl ? (
        <img src={thumbnailUrl} alt="" className="h-full w-full object-cover" />
      ) : (
        <>
          <div className="absolute -bottom-5 left-1 h-12 w-12 rounded-full bg-white/20" />
          <div className="absolute bottom-2 left-5 h-10 w-4 rounded-t-full bg-white/55" />
          <div className="absolute bottom-1 left-3 h-3 w-9 rounded bg-black/20" />
          <div className="absolute right-2 top-2 h-2 w-2 rounded-full bg-white/70" />
        </>
      )}
    </div>
  )
}

function ModalShell({
  title,
  onClose,
  children,
}: {
  title: string
  onClose: () => void
  children: ReactNode
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/20 px-4 py-8 backdrop-blur-sm">
      <section className="w-full max-w-3xl overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-2xl shadow-slate-300/70">
        <header className="flex items-center justify-between border-b border-slate-200 px-6 py-5">
          <h2 className="text-xl font-bold text-slate-950">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            className="flex h-9 w-9 items-center justify-center rounded-lg text-slate-500 transition hover:bg-slate-100 hover:text-slate-900"
            aria-label="关闭"
          >
            <X size={18} />
          </button>
        </header>
        {children}
      </section>
    </div>
  )
}

function MarkdownPreview({ value }: { value: string }) {
  const lines = value.split('\n')
  return (
    <div className="min-h-[360px] space-y-3 overflow-y-auto rounded-b-lg border-x border-b border-slate-200 bg-white px-4 py-4 text-sm leading-7 text-slate-700">
      {lines.map((line, index) => {
        const key = `${index}-${line}`
        if (!line.trim()) return <div key={key} className="h-3" />
        if (line.startsWith('### ')) return <h3 key={key} className="text-base font-bold text-slate-950">{line.slice(4)}</h3>
        if (line.startsWith('## ')) return <h2 key={key} className="text-lg font-bold text-slate-950">{line.slice(3)}</h2>
        if (line.startsWith('# ')) return <h1 key={key} className="text-xl font-bold text-slate-950">{line.slice(2)}</h1>
        if (line.startsWith('- ')) return <p key={key} className="pl-4 text-slate-700">• {line.slice(2)}</p>
        if (line.startsWith('> ')) return <blockquote key={key} className="border-l-4 border-violet-200 pl-3 text-slate-500">{line.slice(2)}</blockquote>
        return <p key={key}>{line}</p>
      })}
    </div>
  )
}

function insertMarkdown(content: string, marker: string) {
  if (marker === 'heading') return `${content}${content ? '\n' : ''}## 标题`
  if (marker === 'list') return `${content}${content ? '\n' : ''}- 条目`
  if (marker === 'quote') return `${content}${content ? '\n' : ''}> 引用`
  if (marker === 'bold') return `${content}**文本**`
  if (marker === 'italic') return `${content}*文本*`
  return content
}

function normalizeTag(value: string) {
  return value.trim().replace(/^#/, '')
}

function WorldbookContent() {
  const { currentWorkspace } = useAppShell()
  const queryClient = useQueryClient()
  const textareaRef = useRef<HTMLTextAreaElement | null>(null)
  const [selectedEntryId, setSelectedEntryId] = useState<number | null>(null)
  const [search, setSearch] = useState('')
  const [tagFilter, setTagFilter] = useState('全部')
  const [draft, setDraft] = useState<Draft>(emptyDraft)
  const [tagInput, setTagInput] = useState('')
  const [preview, setPreview] = useState(false)
  const [mountDialogOpen, setMountDialogOpen] = useState(false)
  const [thumbnailDialogOpen, setThumbnailDialogOpen] = useState(false)
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [thumbnailInput, setThumbnailInput] = useState('')

  const storiesQuery = useQuery({
    queryKey: ['play-stories', currentWorkspace],
    queryFn: () => listStories(currentWorkspace ?? ''),
    enabled: Boolean(currentWorkspace),
  })
  const entriesQuery = useQuery({
    queryKey: ['play-lorebook-entries', currentWorkspace],
    queryFn: () => listLorebookEntries(currentWorkspace ?? ''),
    enabled: Boolean(currentWorkspace),
  })
  const stories = storiesQuery.data ?? []
  const entries = entriesQuery.data ?? []
  const storyEntryQueries = useQueries({
    queries: stories.map((story) => ({
      queryKey: ['play-story-lorebook-entries', currentWorkspace, story.id],
      queryFn: () => listStoryLorebookEntries(currentWorkspace ?? '', story.id),
      enabled: Boolean(currentWorkspace),
    })),
  })
  const storyEntryGroups = useMemo(
    () => stories.map((story, index) => ({ story, entries: storyEntryQueries[index]?.data ?? [] })),
    [stories, storyEntryQueries],
  )
  const mountedIds = useMemo(() => {
    const ids = new Set<number>()
    storyEntryGroups.forEach((group) => {
      group.entries.forEach((entry) => ids.add(entry.id))
    })
    return ids
  }, [storyEntryGroups])
  const selectedEntry = entries.find((entry) => entry.id === selectedEntryId) ?? null
  const selectedEntryMounts = useMemo(
    () => storyEntryGroups.flatMap((group) => (
      group.entries
        .filter((entry) => selectedEntry && entry.id === selectedEntry.id && entry.mountId)
        .map((entry) => ({ story: group.story, entry }))
    )),
    [selectedEntry, storyEntryGroups],
  )
  const tagFilters = useMemo(() => {
    const tags: string[] = []
    entries.forEach((entry) => {
      entry.tags.forEach((tag) => {
        if (tag && !tags.includes(tag)) tags.push(tag)
      })
    })
    return ['全部', '已挂载', ...tags.slice(0, 10)]
  }, [entries])

  useEffect(() => {
    if (!selectedEntryId && entries.length) setSelectedEntryId(entries[0].id)
    if (selectedEntryId && entries.length && !entries.some((entry) => entry.id === selectedEntryId)) {
      setSelectedEntryId(entries[0].id)
    }
  }, [entries, selectedEntryId])

  useEffect(() => {
    const nextDraft = draftFromEntry(selectedEntry)
    setDraft(nextDraft)
    setTagInput('')
    setThumbnailInput(getThumbnailUrl(selectedEntry?.metadata))
    setPreview(false)
  }, [selectedEntry])

  useEffect(() => {
    if (!tagFilters.includes(tagFilter)) setTagFilter('全部')
  }, [tagFilter, tagFilters])

  const filteredEntries = entries.filter((entry) => {
    const query = search.trim().toLowerCase()
    const matchesSearch = !query || `${entry.name} ${entry.description} ${entry.tags.join(' ')}`.toLowerCase().includes(query)
    const matchesTag =
      tagFilter === '全部'
      || (tagFilter === '已挂载' ? mountedIds.has(entry.id) : entry.tags.includes(tagFilter))
    return matchesSearch && matchesTag
  })

  const metadataError = useMemo(() => {
    try {
      const parsed = JSON.parse(draft.metadataText || '{}')
      return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? null : 'metadata 必须是 JSON object'
    } catch {
      return 'metadata JSON 格式错误'
    }
  }, [draft.metadataText])
  const draftMetadata = useMemo(() => parseMetadataObject(draft.metadataText), [draft.metadataText])
  const draftThumbnailUrl = getThumbnailUrl(draftMetadata)

  function addDraftTag(value: string) {
    const tag = normalizeTag(value)
    if (!tag) return
    setDraft((current) => (
      current.tags.includes(tag)
        ? current
        : { ...current, tags: [...current.tags, tag] }
    ))
  }

  function removeDraftTag(tag: string) {
    setDraft((current) => ({ ...current, tags: current.tags.filter((item) => item !== tag) }))
  }

  const createMutation = useMutation({
    mutationFn: () => {
      if (!currentWorkspace) throw new Error('workspace missing')
      return createLorebookEntry(currentWorkspace, {
        name: '未命名条目',
        description: '',
        content: '',
        tags: [],
        metadata: { ui: {} },
      })
    },
    onSuccess: (entry) => {
      setSelectedEntryId(entry.id)
      queryClient.invalidateQueries({ queryKey: ['play-lorebook-entries', currentWorkspace] })
    },
  })

  const saveMutation = useMutation({
    mutationFn: () => {
      if (!currentWorkspace || !selectedEntry) throw new Error('entry missing')
      return updateLorebookEntry(currentWorkspace, selectedEntry.id, {
        name: draft.name,
        description: draft.description,
        content: draft.content,
        tags: draft.tags,
        metadata: JSON.parse(draft.metadataText || '{}') as Record<string, unknown>,
      })
    },
    onSuccess: (entry) => {
      setSelectedEntryId(entry.id)
      queryClient.invalidateQueries({ queryKey: ['play-lorebook-entries', currentWorkspace] })
      stories.forEach((story) => {
        queryClient.invalidateQueries({ queryKey: ['play-story-lorebook-entries', currentWorkspace, story.id] })
      })
    },
  })

  const mountMutation = useMutation({
    mutationFn: ({ storyId, entryId }: { storyId: number; entryId: number }) => {
      if (!currentWorkspace) throw new Error('workspace missing')
      return mountLorebookEntry(currentWorkspace, storyId, entryId)
    },
    onSuccess: (_entry, variables) => {
      queryClient.invalidateQueries({ queryKey: ['play-story-lorebook-entries', currentWorkspace, variables.storyId] })
    },
  })

  const thumbnailMutation = useMutation({
    mutationFn: (thumbnailUrl: string) => {
      if (!currentWorkspace || !selectedEntry) throw new Error('entry missing')
      const nextMetadata = parseMetadataObject(setMetadataThumbnail(JSON.stringify(selectedEntry.metadata ?? {}), thumbnailUrl))
      return updateLorebookEntry(currentWorkspace, selectedEntry.id, { metadata: nextMetadata })
    },
    onSuccess: (entry) => {
      const nextDraft = draftFromEntry(entry)
      setSelectedEntryId(entry.id)
      setDraft(nextDraft)
      setThumbnailInput(getThumbnailUrl(entry.metadata))
      setThumbnailDialogOpen(false)
      queryClient.invalidateQueries({ queryKey: ['play-lorebook-entries', currentWorkspace] })
      stories.forEach((story) => {
        queryClient.invalidateQueries({ queryKey: ['play-story-lorebook-entries', currentWorkspace, story.id] })
      })
    },
  })

  const unmountMutation = useMutation({
    mutationFn: ({ storyId, mountId }: { storyId: number; mountId: number }) => {
      if (!currentWorkspace) throw new Error('workspace missing')
      return unmountLorebookEntry(currentWorkspace, storyId, mountId)
    },
    onSuccess: (_result, variables) => {
      queryClient.invalidateQueries({ queryKey: ['play-story-lorebook-entries', currentWorkspace, variables.storyId] })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: () => {
      if (!currentWorkspace || !selectedEntry) throw new Error('entry missing')
      return deleteLorebookEntry(currentWorkspace, selectedEntry.id)
    },
    onSuccess: () => {
      setDeleteDialogOpen(false)
      setSelectedEntryId(null)
      setDraft(emptyDraft)
      setTagInput('')
      queryClient.invalidateQueries({ queryKey: ['play-lorebook-entries', currentWorkspace] })
      stories.forEach((story) => {
        queryClient.invalidateQueries({ queryKey: ['play-story-lorebook-entries', currentWorkspace, story.id] })
      })
    },
  })

  return (
          <div className="min-w-0 px-5 py-8 xl:px-7">
            <section className="relative mb-6 overflow-hidden rounded-2xl bg-white px-6 py-6 shadow-sm">
              <div className="relative z-10">
                <h1 className="text-3xl font-bold text-slate-950">世界书</h1>
                <p className="mt-2 text-sm text-slate-500">维护地点、历史、规则、组织与可被故事挂载的设定条目</p>
              </div>
              <div className="absolute inset-y-0 right-0 hidden w-[34%] overflow-hidden md:block">
                <div className="absolute bottom-0 right-0 h-full w-full bg-gradient-to-l from-violet-100 via-indigo-50 to-transparent" />
                <div className="absolute bottom-0 right-8 h-24 w-64 rounded-t-full bg-indigo-300/50" />
                <div className="absolute right-28 top-5 h-14 w-14 rounded-full bg-amber-100" />
                <div className="absolute bottom-6 right-28 h-0 w-0 border-b-[52px] border-l-[18px] border-r-[18px] border-b-indigo-700 border-l-transparent border-r-transparent" />
                <div className="absolute bottom-4 right-23 h-7 w-20 rounded-b-full bg-indigo-700" />
              </div>
            </section>

            <div className="grid gap-5 2xl:grid-cols-[420px_minmax(0,1fr)_360px]">
              <section className="min-w-0 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                <div className="flex items-center justify-between gap-3">
                  <h2 className="text-lg font-bold text-slate-950">条目</h2>
                  <button
                    type="button"
                    onClick={() => createMutation.mutate()}
                    disabled={!currentWorkspace || createMutation.isPending}
                    className="flex h-10 items-center gap-2 rounded-lg bg-violet-600 px-4 text-sm font-semibold text-white shadow-lg shadow-violet-200 transition hover:bg-violet-700 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {createMutation.isPending ? <Loader2 size={16} className="animate-spin" /> : <FilePlus2 size={16} />}
                    新建条目
                  </button>
                </div>

                <label className="mt-4 flex h-10 items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-500 focus-within:border-violet-300 focus-within:ring-4 focus-within:ring-violet-100">
                  <Search size={16} />
                  <input
                    value={search}
                    onChange={(event) => setSearch(event.target.value)}
                    placeholder="搜索条目名称或标签..."
                    className="min-w-0 flex-1 bg-transparent text-slate-900 outline-none placeholder:text-slate-400"
                  />
                </label>

                <div className="mt-4 flex flex-wrap gap-2">
                  {tagFilters.map((tag) => (
                    <button
                      key={tag}
                      type="button"
                      onClick={() => setTagFilter(tag)}
                      className={`h-8 rounded-lg border px-3 text-xs font-semibold transition ${
                        tagFilter === tag
                          ? 'border-violet-400 bg-violet-50 text-violet-700'
                          : 'border-slate-200 bg-white text-slate-600 hover:border-violet-200 hover:text-violet-700'
                      }`}
                    >
                      {tag}
                    </button>
                  ))}
                </div>

                <div className="mt-5 max-h-[680px] space-y-3 overflow-y-auto pr-1">
                  {entriesQuery.isLoading ? (
                    <div className="rounded-xl border border-slate-200 px-4 py-6 text-center text-sm text-slate-500">加载中</div>
                  ) : filteredEntries.length ? filteredEntries.map((entry) => {
                    const selected = entry.id === selectedEntryId
                    const mounted = mountedIds.has(entry.id)
                    return (
                      <button
                        key={entry.id}
                        type="button"
                        onClick={() => setSelectedEntryId(entry.id)}
                        className={`w-full rounded-xl border p-3 text-left transition ${
                          selected
                            ? 'border-violet-500 bg-violet-50/50 shadow-sm shadow-violet-100'
                            : 'border-slate-200 bg-white hover:border-violet-200 hover:bg-violet-50/30'
                        }`}
                      >
                        <div className="flex gap-3">
                          <EntryVisual entry={entry} />
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center justify-between gap-2">
                              <h3 className="truncate text-sm font-bold text-slate-950">{entry.name}</h3>
                              {mounted ? (
                                <span className="shrink-0 rounded-full bg-emerald-100 px-2 py-1 text-[11px] font-bold text-emerald-700">已挂载</span>
                              ) : null}
                            </div>
                            <p className="mt-1 line-clamp-2 min-h-10 text-xs leading-5 text-slate-500">{entry.description || entry.content || '暂无内容'}</p>
                            <div className="mt-2 flex flex-wrap gap-1.5">
                              {entry.tags.slice(0, 3).map((tag) => (
                                <span key={tag} className="rounded-md bg-violet-100 px-2 py-0.5 text-[11px] font-semibold text-violet-700">{tag}</span>
                              ))}
                            </div>
                            <p className="mt-2 text-xs text-slate-400">{metadataVersion(entry)} · {formatDate(entry.updatedAt)}</p>
                          </div>
                        </div>
                      </button>
                    )
                  }) : (
                    <div className="rounded-xl border border-slate-200 px-4 py-6 text-center text-sm text-slate-500">暂无条目</div>
                  )}
                </div>
              </section>

              <section className="min-w-0 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <h2 className="text-lg font-bold text-slate-950">{selectedEntry ? '编辑条目' : '新建条目'}</h2>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => setDeleteDialogOpen(true)}
                      disabled={!selectedEntry || deleteMutation.isPending}
                      className="flex h-10 items-center gap-2 rounded-lg border border-rose-200 bg-white px-4 text-sm font-semibold text-rose-600 transition hover:bg-rose-50 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      <Trash2 size={16} />
                      删除
                    </button>
                    <button
                      type="button"
                      onClick={() => saveMutation.mutate()}
                      disabled={!selectedEntry || !draft.name.trim() || Boolean(metadataError) || saveMutation.isPending}
                      className="flex h-10 items-center gap-2 rounded-lg bg-violet-600 px-4 text-sm font-semibold text-white shadow-lg shadow-violet-200 transition hover:bg-violet-700 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {saveMutation.isPending ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
                      保存
                    </button>
                  </div>
                </div>

                <div className="mt-5 grid gap-4">
                  <label className="grid gap-2 text-sm font-semibold text-slate-700">
                    条目名
                    <input
                      value={draft.name}
                      onChange={(event) => setDraft((current) => ({ ...current, name: event.target.value }))}
                      className="h-10 rounded-lg border border-slate-200 px-3 text-sm font-medium text-slate-900 outline-none transition focus:border-violet-300 focus:ring-4 focus:ring-violet-100"
                    />
                  </label>
                  <label className="grid gap-2 text-sm font-semibold text-slate-700">
                    短描述
                    <input
                      value={draft.description}
                      onChange={(event) => setDraft((current) => ({ ...current, description: event.target.value }))}
                      className="h-10 rounded-lg border border-slate-200 px-3 text-sm text-slate-900 outline-none transition focus:border-violet-300 focus:ring-4 focus:ring-violet-100"
                    />
                  </label>

                  <section className="rounded-xl border border-slate-200 bg-slate-50/60 p-4">
                    <div className="flex items-center justify-between gap-4">
                      <div className="flex min-w-0 items-center gap-3">
                        <div className={`relative h-16 w-16 shrink-0 overflow-hidden rounded-xl bg-gradient-to-br ${fallbackThumbnailClass}`}>
                          {draftThumbnailUrl ? (
                            <img src={draftThumbnailUrl} alt="" className="h-full w-full object-cover" />
                          ) : (
                            <div className="flex h-full w-full items-center justify-center text-slate-400">
                              <ImagePlus size={22} />
                            </div>
                          )}
                        </div>
                        <div className="min-w-0">
                          <h3 className="text-sm font-bold text-slate-900">缩略图</h3>
                          <p className="mt-1 truncate text-xs text-slate-500">{draftThumbnailUrl ? '已设置 thumbnailUrl' : '未设置缩略图'}</p>
                        </div>
                      </div>
                      <button
                        type="button"
                        onClick={() => {
                          setThumbnailInput(draftThumbnailUrl)
                          setThumbnailDialogOpen(true)
                        }}
                        disabled={!selectedEntry}
                        className="flex h-10 shrink-0 items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700 transition hover:border-violet-200 hover:text-violet-700 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        <ImagePlus size={16} />
                        编辑
                      </button>
                    </div>
                  </section>

                  <div>
                    <div className="mb-2 flex items-center justify-between">
                      <label className="text-sm font-semibold text-slate-700">世界书正文</label>
                      <div className="flex items-center gap-1 rounded-lg border border-slate-200 bg-slate-50 p-1">
                        {[
                          { key: 'heading', icon: Type, label: '标题' },
                          { key: 'bold', icon: Bold, label: '加粗' },
                          { key: 'italic', icon: Italic, label: '斜体' },
                          { key: 'list', icon: List, label: '列表' },
                        ].map((item) => (
                          <button
                            key={item.key}
                            type="button"
                            title={item.label}
                            onClick={() => {
                              setPreview(false)
                              setDraft((current) => ({ ...current, content: insertMarkdown(current.content, item.key) }))
                              textareaRef.current?.focus()
                            }}
                            className="flex h-8 w-8 items-center justify-center rounded-md text-slate-600 transition hover:bg-white hover:text-violet-700"
                          >
                            <item.icon size={15} />
                          </button>
                        ))}
                        <button
                          type="button"
                          title={preview ? '编辑' : '预览'}
                          onClick={() => setPreview((value) => !value)}
                          className={`ml-1 flex h-8 items-center gap-1 rounded-md px-2 text-xs font-semibold transition ${
                            preview ? 'bg-violet-100 text-violet-700' : 'text-slate-600 hover:bg-white hover:text-violet-700'
                          }`}
                        >
                          <Eye size={14} />
                          {preview ? '编辑' : '预览'}
                        </button>
                      </div>
                    </div>
                    {preview ? (
                      <MarkdownPreview value={draft.content} />
                    ) : (
                      <textarea
                        ref={textareaRef}
                        value={draft.content}
                        onChange={(event) => setDraft((current) => ({ ...current, content: event.target.value }))}
                        className="min-h-[360px] w-full resize-y rounded-lg border border-slate-200 px-4 py-3 text-sm leading-7 text-slate-800 outline-none transition focus:border-violet-300 focus:ring-4 focus:ring-violet-100"
                      />
                    )}
                  </div>

                  <section className="grid gap-2">
                    <label className="text-sm font-semibold text-slate-700">标签</label>
                    <div className="rounded-xl border border-slate-200 bg-white px-3 py-2 transition focus-within:border-violet-300 focus-within:ring-4 focus-within:ring-violet-100">
                      <div className="flex min-h-9 flex-wrap items-center gap-2">
                        {draft.tags.map((tag) => (
                          <span
                            key={tag}
                            className="inline-flex h-7 items-center gap-1 rounded-lg bg-violet-100 px-2 text-xs font-semibold text-violet-700"
                          >
                            {tag}
                            <button
                              type="button"
                              aria-label={`删除标签 ${tag}`}
                              onClick={() => removeDraftTag(tag)}
                              className="flex h-4 w-4 items-center justify-center rounded text-violet-500 transition hover:bg-violet-200 hover:text-violet-800"
                            >
                              <X size={12} />
                            </button>
                          </span>
                        ))}
                        <input
                          value={tagInput}
                          onChange={(event) => {
                            const value = event.target.value
                            if (/[,\s，、]$/.test(value)) {
                              value.split(/[,\s，、]+/).forEach(addDraftTag)
                              setTagInput('')
                              return
                            }
                            setTagInput(value)
                          }}
                          onKeyDown={(event) => {
                            if (event.key === 'Enter' || event.key === ',') {
                              event.preventDefault()
                              addDraftTag(tagInput)
                              setTagInput('')
                            }
                            if (event.key === 'Backspace' && !tagInput && draft.tags.length) {
                              removeDraftTag(draft.tags[draft.tags.length - 1])
                            }
                          }}
                          onBlur={() => {
                            addDraftTag(tagInput)
                            setTagInput('')
                          }}
                          placeholder={draft.tags.length ? '继续添加标签...' : '输入标签后回车添加...'}
                          className="h-7 min-w-32 flex-1 bg-transparent text-sm text-slate-900 outline-none placeholder:text-slate-400"
                        />
                      </div>
                    </div>
                  </section>

                  <details className="rounded-xl border border-slate-200 bg-slate-50/60 px-4 py-3">
                    <summary className="cursor-pointer text-sm font-bold text-slate-800">高级 metadata_json</summary>
                    <textarea
                      value={draft.metadataText}
                      onChange={(event) => setDraft((current) => ({ ...current, metadataText: event.target.value }))}
                      className="mt-3 min-h-32 w-full resize-y rounded-lg border border-slate-200 bg-white px-3 py-2 font-mono text-xs leading-6 text-slate-800 outline-none transition focus:border-violet-300 focus:ring-4 focus:ring-violet-100"
                    />
                    {metadataError ? <p className="mt-2 text-xs font-semibold text-rose-600">{metadataError}</p> : null}
                  </details>

                  {selectedEntry ? (
                    <div className="grid gap-3 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm sm:grid-cols-3">
                      <div>
                        <p className="text-slate-400">版本</p>
                        <p className="mt-1 font-semibold text-slate-800">{metadataVersion(selectedEntry)}</p>
                      </div>
                      <div>
                        <p className="text-slate-400">创建时间</p>
                        <p className="mt-1 font-semibold text-slate-800">{formatDate(selectedEntry.createdAt)}</p>
                      </div>
                      <div>
                        <p className="text-slate-400">更新时间</p>
                        <p className="mt-1 font-semibold text-slate-800">{formatDate(selectedEntry.updatedAt)}</p>
                      </div>
                    </div>
                  ) : null}
                </div>
              </section>

              <aside className="min-w-0 space-y-5">
                <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                  <div className="mb-4 flex items-center justify-between gap-3">
                    <h2 className="text-lg font-bold text-slate-950">故事挂载</h2>
                    <button
                      type="button"
                      onClick={() => setMountDialogOpen(true)}
                      disabled={!selectedEntry || !stories.length}
                      className="flex h-9 items-center gap-2 rounded-lg border border-violet-200 bg-violet-50 px-3 text-sm font-semibold text-violet-700 transition hover:border-violet-300 hover:bg-violet-100 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      <Plus size={15} />
                      添加挂载
                    </button>
                  </div>
                  <div className="mt-4 space-y-3">
                    {selectedEntryMounts.length ? selectedEntryMounts.map(({ story, entry }) => (
                      <article key={`${story.id}-${entry.mountId ?? entry.id}`} className="flex items-center gap-3 rounded-xl border border-slate-200 p-3">
                        <EntryVisual entry={entry} />
                        <div className="min-w-0 flex-1">
                          <h3 className="truncate text-sm font-bold text-slate-950">{story.title}</h3>
                          <p className="mt-1 truncate text-xs text-slate-500">{story.summary || story.description || '暂无故事描述'}</p>
                        </div>
                        <button
                          type="button"
                          aria-label={`移除 ${story.title}`}
                          onClick={() => entry.mountId ? unmountMutation.mutate({ storyId: story.id, mountId: entry.mountId }) : undefined}
                          disabled={!entry.mountId || unmountMutation.isPending}
                          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-slate-400 transition hover:bg-rose-50 hover:text-rose-600 disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          <Trash2 size={16} />
                        </button>
                      </article>
                    )) : (
                      <div className="rounded-xl border border-slate-200 px-4 py-6 text-center text-sm text-slate-500">当前条目暂无故事挂载</div>
                    )}
                  </div>
                </section>
              </aside>
            </div>

            {mountDialogOpen ? (
              <ModalShell title="添加故事挂载" onClose={() => setMountDialogOpen(false)}>
                <div className="border-b border-slate-200 bg-slate-50/70 px-6 py-4">
                  <p className="text-sm text-slate-500">
                    {selectedEntry ? `将「${selectedEntry.name}」添加到故事。` : '请先选择一个世界书条目。'}
                  </p>
                </div>
                <div className="max-h-[520px] overflow-y-auto px-5 py-5">
                  <div className="rounded-2xl border border-slate-200 bg-white">
                    {stories.length ? stories.map((story) => {
                      const alreadyMountedInStory = selectedEntryMounts.some((mount) => mount.story.id === story.id)
                      return (
                        <article
                          key={story.id}
                          className="grid gap-3 border-b border-slate-100 px-4 py-4 last:border-b-0 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center"
                        >
                          <div className="min-w-0">
                            <div className="flex flex-wrap items-center gap-2">
                              <h3 className="truncate text-sm font-bold text-slate-950">{story.title}</h3>
                              {alreadyMountedInStory ? (
                                <span className="rounded-md bg-emerald-100 px-2 py-0.5 text-[11px] font-bold text-emerald-700">已挂载</span>
                              ) : null}
                            </div>
                            <p className="mt-1 line-clamp-2 text-xs leading-5 text-slate-500">{story.summary || story.description || '暂无故事描述'}</p>
                          </div>
                          <button
                            type="button"
                            onClick={() => {
                              if (selectedEntry) mountMutation.mutate({ storyId: story.id, entryId: selectedEntry.id })
                            }}
                            disabled={!selectedEntry || alreadyMountedInStory || mountMutation.isPending}
                            className="flex h-10 items-center justify-center gap-2 rounded-lg bg-violet-600 px-4 text-sm font-semibold text-white shadow-lg shadow-violet-100 transition hover:bg-violet-700 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-500 disabled:shadow-none"
                          >
                            {mountMutation.isPending ? <Loader2 size={16} className="animate-spin" /> : alreadyMountedInStory ? <Check size={16} /> : <Plus size={16} />}
                            {alreadyMountedInStory ? '已添加' : '添加'}
                          </button>
                        </article>
                      )
                    }) : (
                      <div className="px-4 py-10 text-center text-sm text-slate-500">暂无故事</div>
                    )}
                  </div>
                </div>
                <footer className="flex items-center justify-between border-t border-slate-200 bg-slate-50 px-6 py-4 text-xs text-slate-500">
                  <span>添加后右侧会显示当前条目的故事挂载。</span>
                  <button
                    type="button"
                    onClick={() => setMountDialogOpen(false)}
                    className="h-9 rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700 transition hover:border-violet-200 hover:text-violet-700"
                  >
                    完成
                  </button>
                </footer>
              </ModalShell>
            ) : null}

            {deleteDialogOpen ? (
              <ModalShell title="删除世界书条目" onClose={() => setDeleteDialogOpen(false)}>
                <div className="px-6 py-5">
                  <div className="rounded-2xl border border-rose-100 bg-rose-50 px-4 py-4">
                    <h3 className="text-sm font-bold text-rose-700">确认删除「{selectedEntry?.name ?? '当前条目'}」？</h3>
                    <p className="mt-2 text-sm leading-6 text-rose-700/80">
                      删除后会同时移除它在所有故事里的挂载关系。这个操作不会删除其它世界书条目。
                    </p>
                  </div>
                </div>
                <footer className="flex items-center justify-end gap-2 border-t border-slate-200 bg-slate-50 px-6 py-4">
                  <button
                    type="button"
                    onClick={() => setDeleteDialogOpen(false)}
                    className="h-10 rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700 transition hover:border-violet-200 hover:text-violet-700"
                  >
                    取消
                  </button>
                  <button
                    type="button"
                    onClick={() => deleteMutation.mutate()}
                    disabled={!selectedEntry || deleteMutation.isPending}
                    className="flex h-10 items-center gap-2 rounded-lg bg-rose-600 px-4 text-sm font-semibold text-white shadow-lg shadow-rose-100 transition hover:bg-rose-700 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {deleteMutation.isPending ? <Loader2 size={16} className="animate-spin" /> : <Trash2 size={16} />}
                    删除
                  </button>
                </footer>
              </ModalShell>
            ) : null}

            {thumbnailDialogOpen ? (
              <ModalShell title="编辑缩略图" onClose={() => setThumbnailDialogOpen(false)}>
                <div className="grid gap-5 px-6 py-5 md:grid-cols-[220px_minmax(0,1fr)]">
                  <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                    <div className={`relative aspect-square overflow-hidden rounded-xl bg-gradient-to-br ${fallbackThumbnailClass}`}>
                      {thumbnailInput ? (
                        <img src={thumbnailInput} alt="" className="h-full w-full object-cover" />
                      ) : (
                        <div className="flex h-full w-full items-center justify-center text-slate-400">
                          <ImagePlus size={34} />
                        </div>
                      )}
                    </div>
                    <p className="mt-3 text-xs leading-5 text-slate-500">缩略图保存到 metadata_json.ui.thumbnailUrl，可使用图片 URL 或上传本地图片。</p>
                  </div>
                  <div className="space-y-4">
                    <label className="grid gap-2 text-sm font-semibold text-slate-700">
                      图片 URL
                      <input
                        value={thumbnailInput}
                        onChange={(event) => setThumbnailInput(event.target.value)}
                        placeholder="https://... 或 data:image/..."
                        className="h-10 rounded-lg border border-slate-200 px-3 text-sm text-slate-900 outline-none transition focus:border-violet-300 focus:ring-4 focus:ring-violet-100"
                      />
                    </label>

                    <label className="flex min-h-28 cursor-pointer flex-col items-center justify-center rounded-2xl border border-dashed border-violet-200 bg-violet-50/60 px-4 py-5 text-center transition hover:border-violet-300 hover:bg-violet-50">
                      <UploadCloud size={24} className="text-violet-600" />
                      <span className="mt-2 text-sm font-bold text-slate-900">上传图片</span>
                      <span className="mt-1 text-xs text-slate-500">会转为 data URL 写入 metadata</span>
                      <input
                        type="file"
                        accept="image/*"
                        className="hidden"
                        onChange={async (event) => {
                          const file = event.target.files?.[0]
                          if (!file) return
                          setThumbnailInput(await readFileAsDataUrl(file))
                          event.target.value = ''
                        }}
                      />
                    </label>
                  </div>
                </div>
                <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 bg-slate-50 px-6 py-4">
                  <button
                    type="button"
                    onClick={() => thumbnailMutation.mutate('')}
                    disabled={!selectedEntry || thumbnailMutation.isPending}
                    className="flex h-10 items-center gap-2 rounded-lg border border-rose-200 bg-white px-4 text-sm font-semibold text-rose-600 transition hover:bg-rose-50 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <Trash2 size={16} />
                    删除缩略图
                  </button>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => setThumbnailDialogOpen(false)}
                      className="h-10 rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700 transition hover:border-violet-200 hover:text-violet-700"
                    >
                      取消
                    </button>
                    <button
                      type="button"
                      onClick={() => thumbnailMutation.mutate(thumbnailInput.trim())}
                      disabled={!selectedEntry || thumbnailMutation.isPending}
                      className="flex h-10 items-center gap-2 rounded-lg bg-violet-600 px-4 text-sm font-semibold text-white shadow-lg shadow-violet-100 transition hover:bg-violet-700 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {thumbnailMutation.isPending ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
                      保存缩略图
                    </button>
                  </div>
                </footer>
              </ModalShell>
            ) : null}
          </div>
  )
}

export function WorldbookPage() {
  return (
    <AppShell>
      <WorldbookContent />
    </AppShell>
  )
}
