'use client'

import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { FilePlus2, Loader2, Save, Search, Trash2 } from 'lucide-react'
import { ConfirmDialog } from '@/components/common/Dialog'
import { AppShell, useAppShell } from '@/features/layout/AppShell'
import {
  createLorebookEntry,
  deleteLorebookEntry,
  listLorebookEntries,
  updateLorebookEntry,
} from '@/lib/api/lorebook'
import { listStories } from '@/lib/api/stories'
import { useStorySelection } from '@/features/stories/useStorySelection'
import type { LorebookEntry, LorebookEntryInput } from '@/types/lorebook'

type EntryDraft = {
  name: string
  description: string
  content: string
  tagsText: string
  sortOrder: number
  metadataText: string
}

const EMPTY_DRAFT: EntryDraft = {
  name: '',
  description: '',
  content: '',
  tagsText: '',
  sortOrder: 0,
  metadataText: '{\n  "ui": {}\n}',
}

function entryDraft(entry: LorebookEntry | null): EntryDraft {
  if (!entry) return EMPTY_DRAFT
  return {
    name: entry.name,
    description: entry.description,
    content: entry.content,
    tagsText: entry.tags.join(', '),
    sortOrder: entry.sortOrder,
    metadataText: JSON.stringify(entry.metadata ?? {}, null, 2),
  }
}

function parseMetadata(value: string): Record<string, unknown> {
  const parsed: unknown = JSON.parse(value || '{}')
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error('metadata 必须是 JSON object')
  }
  return parsed as Record<string, unknown>
}

function nextAvailableName(base: string, names: Iterable<string>) {
  const used = new Set(Array.from(names, (name) => name.trim()))
  if (!used.has(base)) return base
  let suffix = 2
  while (used.has(`${base} ${suffix}`)) suffix += 1
  return `${base} ${suffix}`
}

function parseTags(value: string) {
  return Array.from(new Set(
    value.split(/[,，、\n]+/).map((item) => item.trim().replace(/^#/, '')).filter(Boolean),
  ))
}

function WorldbookContent() {
  const { currentWorkspace } = useAppShell()
  const queryClient = useQueryClient()
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [search, setSearch] = useState('')
  const [draft, setDraft] = useState<EntryDraft>(EMPTY_DRAFT)
  const [formError, setFormError] = useState<string | null>(null)
  const [deleteOpen, setDeleteOpen] = useState(false)

  const storiesQuery = useQuery({
    queryKey: ['play-stories', currentWorkspace],
    queryFn: () => listStories(currentWorkspace ?? ''),
    enabled: Boolean(currentWorkspace),
  })
  const stories = storiesQuery.data ?? []
  const [storyId, setStoryId] = useStorySelection(stories)

  const entriesQuery = useQuery({
    queryKey: ['play-story-lorebook', currentWorkspace, storyId],
    queryFn: () => listLorebookEntries(currentWorkspace ?? '', storyId ?? 0),
    enabled: Boolean(currentWorkspace && storyId),
  })
  const entries = entriesQuery.data ?? []
  const selected = entries.find((entry) => entry.id === selectedId) ?? null

  useEffect(() => {
    setSelectedId(null)
    setDraft(EMPTY_DRAFT)
    setFormError(null)
  }, [storyId])

  useEffect(() => {
    if (!entries.length) {
      setSelectedId(null)
      return
    }
    if (selectedId === null || !entries.some((entry) => entry.id === selectedId)) {
      setSelectedId(entries[0].id)
    }
  }, [entries, selectedId])

  useEffect(() => {
    setDraft(entryDraft(selected))
    setFormError(null)
  }, [selected])

  const filtered = useMemo(() => {
    const needle = search.trim().toLocaleLowerCase()
    if (!needle) return entries
    return entries.filter((entry) => (
      `${entry.name} ${entry.description} ${entry.content} ${entry.tags.join(' ')}`
        .toLocaleLowerCase()
        .includes(needle)
    ))
  }, [entries, search])

  function invalidate() {
    return queryClient.invalidateQueries({
      queryKey: ['play-story-lorebook', currentWorkspace, storyId],
    })
  }

  const createMutation = useMutation({
    mutationFn: () => {
      if (!currentWorkspace || !storyId) throw new Error('请先选择 Story')
      const input: LorebookEntryInput = {
        name: nextAvailableName(
          '未命名世界书条目',
          entries.map((item) => item.name),
        ),
        description: '',
        content: '',
        tags: [],
        sortOrder: entries.length ? Math.max(...entries.map((item) => item.sortOrder)) + 10 : 0,
        metadata: { ui: {} },
      }
      return createLorebookEntry(currentWorkspace, storyId, input)
    },
    onSuccess: async (entry) => {
      await invalidate()
      setSelectedId(entry.id)
    },
    onError: (reason) => setFormError(reason instanceof Error ? reason.message : '新建世界书条目失败'),
  })

  const saveMutation = useMutation({
    mutationFn: () => {
      if (!currentWorkspace || !storyId || !selected) throw new Error('未选择世界书条目')
      if (!draft.name.trim()) throw new Error('条目名称不能为空')
      return updateLorebookEntry(currentWorkspace, storyId, selected.id, {
        name: draft.name.trim(),
        description: draft.description,
        content: draft.content,
        tags: parseTags(draft.tagsText),
        sortOrder: draft.sortOrder,
        metadata: parseMetadata(draft.metadataText),
      })
    },
    onSuccess: async () => {
      setFormError(null)
      await invalidate()
    },
    onError: (reason) => setFormError(reason instanceof Error ? reason.message : '保存世界书条目失败'),
  })

  const deleteMutation = useMutation({
    mutationFn: () => {
      if (!currentWorkspace || !storyId || !selected) throw new Error('未选择世界书条目')
      return deleteLorebookEntry(currentWorkspace, storyId, selected.id)
    },
    onSuccess: async () => {
      setDeleteOpen(false)
      setSelectedId(null)
      await invalidate()
    },
    onError: (reason) => setFormError(reason instanceof Error ? reason.message : '删除世界书条目失败'),
  })

  return (
    <div className="min-w-0 px-5 py-8 xl:px-7">
      <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-slate-950">Story 世界书</h1>
          <p className="mt-2 text-sm text-slate-500">世界书条目直接归属 Story；大批量设定不再混入 Workspace 公共列表。</p>
        </div>
        <label className="grid min-w-72 gap-2 text-xs font-black uppercase text-slate-500">
          当前 Story
          <select
            value={storyId ?? ''}
            onChange={(event) => setStoryId(event.target.value ? Number(event.target.value) : null)}
            className="h-11 rounded-xl border border-slate-200 bg-white px-3 text-sm font-bold normal-case text-slate-900 outline-none focus:border-violet-300 focus:ring-4 focus:ring-violet-100"
          >
            {!stories.length ? <option value="">暂无 Story</option> : null}
            {stories.map((story) => <option key={story.id} value={story.id}>{story.title}</option>)}
          </select>
        </label>
      </header>

      {formError ? <p className="mb-4 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-bold text-rose-700">{formError}</p> : null}

      <div className="grid gap-5 xl:grid-cols-[380px_minmax(0,1fr)]">
        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex items-center justify-between gap-3">
            <div><h2 className="text-lg font-bold text-slate-950">条目</h2><p className="mt-1 text-xs text-slate-400">当前 Story 共 {entries.length} 条</p></div>
            <button type="button" onClick={() => createMutation.mutate()} disabled={!storyId || createMutation.isPending} className="inline-flex h-10 items-center gap-2 rounded-lg bg-violet-600 px-3 text-sm font-bold text-white disabled:opacity-50">{createMutation.isPending ? <Loader2 size={16} className="animate-spin" /> : <FilePlus2 size={16} />}新建</button>
          </div>
          <label className="mt-4 flex h-10 items-center gap-2 rounded-lg border border-slate-200 px-3 text-sm text-slate-500 focus-within:border-violet-300">
            <Search size={16} />
            <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜索名称、标签或正文…" className="min-w-0 flex-1 outline-none" />
          </label>
          <div className="mt-4 max-h-[760px] space-y-2 overflow-y-auto">
            {entriesQuery.isLoading ? <p className="py-10 text-center text-sm text-slate-400">加载中…</p> : null}
            {!entriesQuery.isLoading && !filtered.length ? <p className="py-10 text-center text-sm text-slate-400">当前 Story 暂无世界书条目</p> : null}
            {filtered.map((entry) => (
              <button key={entry.id} type="button" onClick={() => setSelectedId(entry.id)} className={`w-full rounded-xl border p-4 text-left transition ${entry.id === selectedId ? 'border-violet-400 bg-violet-50' : 'border-slate-200 hover:border-violet-200'}`}>
                <div className="flex items-start justify-between gap-3"><strong className="truncate text-sm text-slate-950">{entry.name}</strong><span className="rounded-full bg-slate-100 px-2 py-1 text-[11px] font-bold text-slate-500">#{entry.id}</span></div>
                <p className="mt-2 line-clamp-2 text-xs leading-5 text-slate-500">{entry.description || entry.content || '暂无说明'}</p>
                <div className="mt-3 flex flex-wrap gap-1">{entry.tags.slice(0, 5).map((tag) => <span key={tag} className="rounded bg-violet-50 px-2 py-1 text-[11px] font-bold text-violet-700">#{tag}</span>)}</div>
              </button>
            ))}
          </div>
        </section>

        <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div><h2 className="text-lg font-bold text-slate-950">{selected?.name ?? '世界书编辑'}</h2><p className="mt-1 text-xs text-slate-400">内容会随当前 Story 进入固定上下文。</p></div>
            <div className="flex gap-2">
              <button type="button" onClick={() => setDeleteOpen(true)} disabled={!selected} className="inline-flex h-10 items-center gap-2 rounded-lg border border-rose-200 px-3 text-sm font-bold text-rose-700 disabled:opacity-40"><Trash2 size={16} />删除</button>
              <button type="button" onClick={() => saveMutation.mutate()} disabled={!selected || saveMutation.isPending} className="inline-flex h-10 items-center gap-2 rounded-lg bg-violet-600 px-4 text-sm font-bold text-white disabled:opacity-50">{saveMutation.isPending ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}保存</button>
            </div>
          </div>
          <div className="mt-6 grid gap-5">
            <div className="grid gap-5 md:grid-cols-[minmax(0,1fr)_140px]">
              <label className="grid gap-2 text-sm font-bold text-slate-700">名称<input disabled={!selected} value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} className="h-11 rounded-lg border border-slate-200 px-3 outline-none focus:border-violet-300 disabled:bg-slate-50" /></label>
              <label className="grid gap-2 text-sm font-bold text-slate-700">排序<input disabled={!selected} type="number" value={draft.sortOrder} onChange={(event) => setDraft({ ...draft, sortOrder: Number(event.target.value) || 0 })} className="h-11 rounded-lg border border-slate-200 px-3 outline-none disabled:bg-slate-50" /></label>
            </div>
            <label className="grid gap-2 text-sm font-bold text-slate-700">简短说明<textarea disabled={!selected} value={draft.description} onChange={(event) => setDraft({ ...draft, description: event.target.value })} className="min-h-24 rounded-lg border border-slate-200 px-3 py-3 leading-6 outline-none focus:border-violet-300 disabled:bg-slate-50" /></label>
            <label className="grid gap-2 text-sm font-bold text-slate-700">标签<input disabled={!selected} value={draft.tagsText} onChange={(event) => setDraft({ ...draft, tagsText: event.target.value })} placeholder="地点, 阵营, 传闻" className="h-11 rounded-lg border border-slate-200 px-3 outline-none focus:border-violet-300 disabled:bg-slate-50" /></label>
            <label className="grid gap-2 text-sm font-bold text-slate-700">完整条目内容<textarea disabled={!selected} value={draft.content} onChange={(event) => setDraft({ ...draft, content: event.target.value })} className="min-h-[360px] rounded-lg border border-slate-200 px-3 py-3 font-mono text-sm leading-7 outline-none focus:border-violet-300 disabled:bg-slate-50" /></label>
            <label className="grid gap-2 text-sm font-bold text-slate-700">Metadata JSON<textarea disabled={!selected} value={draft.metadataText} onChange={(event) => setDraft({ ...draft, metadataText: event.target.value })} className="min-h-36 rounded-lg border border-slate-200 bg-slate-50 px-3 py-3 font-mono text-xs leading-6 outline-none focus:border-violet-300" /></label>
          </div>
        </section>
      </div>

      {deleteOpen && selected ? <ConfirmDialog title="删除 Story 世界书条目" heading={`确定删除「${selected.name}」？`} body="该条目会从当前 Story 永久删除，后续 Session 上下文不再读取它。" pending={deleteMutation.isPending} onClose={() => setDeleteOpen(false)} onConfirm={() => deleteMutation.mutate()} /> : null}
    </div>
  )
}

export function WorldbookPage() {
  return <AppShell><WorldbookContent /></AppShell>
}
