'use client'

import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { FilePlus2, Loader2, Plus, Save, Search, Trash2 } from 'lucide-react'
import { ConfirmDialog, Dialog } from '@/components/common/Dialog'
import { AppShell, useAppShell } from '@/features/layout/AppShell'
import {
  createCharacter,
  createCharacterDetail,
  deleteCharacter,
  deleteCharacterDetail,
  listCharacters,
  updateCharacter,
  updateCharacterDetail,
} from '@/lib/api/characters'
import { listStories } from '@/lib/api/stories'
import { useStorySelection } from '@/features/stories/useStorySelection'
import type {
  CharacterCard,
  CharacterDetail,
  CharacterDetailInput,
  CharacterInput,
} from '@/types/characters'

type CharacterDraft = {
  name: string
  personality: string
  content: string
  sortOrder: number
  metadataText: string
}

type DetailDraft = {
  name: string
  content: string
  tagsText: string
  sortOrder: number
}

const EMPTY_CHARACTER: CharacterDraft = {
  name: '',
  personality: '',
  content: '',
  sortOrder: 0,
  metadataText: '{\n  "ui": {}\n}',
}

const EMPTY_DETAIL: DetailDraft = {
  name: '',
  content: '',
  tagsText: '',
  sortOrder: 0,
}

function characterDraft(character: CharacterCard | null): CharacterDraft {
  if (!character) return EMPTY_CHARACTER
  return {
    name: character.name,
    personality: character.personality,
    content: character.content,
    sortOrder: character.sortOrder,
    metadataText: JSON.stringify(character.metadata ?? {}, null, 2),
  }
}

function detailDraft(detail: CharacterDetail | null): DetailDraft {
  if (!detail) return EMPTY_DETAIL
  return {
    name: detail.name,
    content: detail.content,
    tagsText: detail.tags.join(', '),
    sortOrder: detail.sortOrder,
  }
}

function parseMetadata(value: string): Record<string, unknown> {
  const parsed: unknown = JSON.parse(value || '{}')
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error('metadata 必须是 JSON object')
  }
  return parsed as Record<string, unknown>
}

function parseTags(value: string) {
  return Array.from(new Set(
    value.split(/[,，、\n]+/).map((item) => item.trim().replace(/^#/, '')).filter(Boolean),
  ))
}

function formatDate(value?: string | null) {
  if (!value) return '暂无'
  return value.replace('T', ' ').slice(0, 16)
}

function nextAvailableName(base: string, names: Iterable<string>) {
  const used = new Set(Array.from(names, (name) => name.trim()))
  if (!used.has(base)) return base
  let suffix = 2
  while (used.has(`${base} ${suffix}`)) suffix += 1
  return `${base} ${suffix}`
}

function CharactersContent() {
  const { currentWorkspace } = useAppShell()
  const queryClient = useQueryClient()
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [search, setSearch] = useState('')
  const [draft, setDraft] = useState<CharacterDraft>(EMPTY_CHARACTER)
  const [formError, setFormError] = useState<string | null>(null)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [detailOpen, setDetailOpen] = useState(false)
  const [detailDeleteTarget, setDetailDeleteTarget] = useState<CharacterDetail | null>(null)
  const [editingDetailId, setEditingDetailId] = useState<number | null>(null)
  const [detailForm, setDetailForm] = useState<DetailDraft>(EMPTY_DETAIL)

  const storiesQuery = useQuery({
    queryKey: ['play-stories', currentWorkspace],
    queryFn: () => listStories(currentWorkspace ?? ''),
    enabled: Boolean(currentWorkspace),
  })
  const stories = storiesQuery.data ?? []
  const [storyId, setStoryId] = useStorySelection(stories)

  const charactersQuery = useQuery({
    queryKey: ['play-story-characters', currentWorkspace, storyId],
    queryFn: () => listCharacters(currentWorkspace ?? '', storyId ?? 0),
    enabled: Boolean(currentWorkspace && storyId),
  })
  const characters = charactersQuery.data ?? []
  const selected = characters.find((item) => item.id === selectedId) ?? null

  useEffect(() => {
    setSelectedId(null)
    setDraft(EMPTY_CHARACTER)
    setFormError(null)
  }, [storyId])

  useEffect(() => {
    if (!characters.length) {
      setSelectedId(null)
      return
    }
    if (selectedId === null || !characters.some((item) => item.id === selectedId)) {
      setSelectedId(characters[0].id)
    }
  }, [characters, selectedId])

  useEffect(() => {
    setDraft(characterDraft(selected))
    setFormError(null)
  }, [selected])

  const filtered = useMemo(() => {
    const needle = search.trim().toLocaleLowerCase()
    if (!needle) return characters
    return characters.filter((character) => (
      `${character.name} ${character.personality} ${character.content} ${character.details.map((detail) => `${detail.name} ${detail.tags.join(' ')}`).join(' ')}`
        .toLocaleLowerCase()
        .includes(needle)
    ))
  }, [characters, search])

  function invalidate() {
    return queryClient.invalidateQueries({
      queryKey: ['play-story-characters', currentWorkspace, storyId],
    })
  }

  const createMutation = useMutation({
    mutationFn: () => {
      if (!currentWorkspace || !storyId) throw new Error('请先选择 Story')
      const input: CharacterInput = {
        name: nextAvailableName('未命名角色', characters.map((item) => item.name)),
        personality: '',
        content: '',
        sortOrder: characters.length ? Math.max(...characters.map((item) => item.sortOrder)) + 10 : 0,
        metadata: { ui: {} },
      }
      return createCharacter(currentWorkspace, storyId, input)
    },
    onSuccess: async (character) => {
      await invalidate()
      setSelectedId(character.id)
    },
    onError: (reason) => setFormError(reason instanceof Error ? reason.message : '新建角色失败'),
  })

  const saveMutation = useMutation({
    mutationFn: () => {
      if (!currentWorkspace || !storyId || !selected) throw new Error('未选择角色')
      if (!draft.name.trim()) throw new Error('角色名不能为空')
      return updateCharacter(currentWorkspace, storyId, selected.id, {
        name: draft.name.trim(),
        personality: draft.personality,
        content: draft.content,
        sortOrder: draft.sortOrder,
        metadata: parseMetadata(draft.metadataText),
      })
    },
    onSuccess: async () => {
      setFormError(null)
      await invalidate()
    },
    onError: (reason) => setFormError(reason instanceof Error ? reason.message : '保存角色失败'),
  })

  const deleteMutation = useMutation({
    mutationFn: () => {
      if (!currentWorkspace || !storyId || !selected) throw new Error('未选择角色')
      return deleteCharacter(currentWorkspace, storyId, selected.id)
    },
    onSuccess: async () => {
      setDeleteOpen(false)
      setSelectedId(null)
      await invalidate()
    },
    onError: (reason) => setFormError(reason instanceof Error ? reason.message : '删除角色失败'),
  })

  const saveDetailMutation = useMutation({
    mutationFn: () => {
      if (!currentWorkspace || !storyId || !selected) throw new Error('未选择角色')
      if (!detailForm.name.trim()) throw new Error('细节名称不能为空')
      const input: CharacterDetailInput = {
        name: detailForm.name.trim(),
        content: detailForm.content,
        tags: parseTags(detailForm.tagsText),
        sortOrder: detailForm.sortOrder,
      }
      return editingDetailId
        ? updateCharacterDetail(currentWorkspace, storyId, selected.id, editingDetailId, input)
        : createCharacterDetail(currentWorkspace, storyId, selected.id, input)
    },
    onSuccess: async () => {
      setDetailOpen(false)
      setEditingDetailId(null)
      setDetailForm(EMPTY_DETAIL)
      setFormError(null)
      await invalidate()
    },
    onError: (reason) => setFormError(reason instanceof Error ? reason.message : '保存细节失败'),
  })

  const deleteDetailMutation = useMutation({
    mutationFn: (detailId: number) => {
      if (!currentWorkspace || !storyId || !selected) throw new Error('未选择角色')
      return deleteCharacterDetail(currentWorkspace, storyId, selected.id, detailId)
    },
    onSuccess: async () => {
      setDetailDeleteTarget(null)
      await invalidate()
    },
    onError: (reason) => setFormError(reason instanceof Error ? reason.message : '删除细节失败'),
  })

  function openDetail(detail: CharacterDetail | null) {
    setEditingDetailId(detail?.id ?? null)
    setDetailForm(detailDraft(detail))
    setDetailOpen(true)
  }

  return (
    <div className="min-w-0 px-5 py-8 xl:px-7">
      <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-slate-950">Story 角色</h1>
          <p className="mt-2 text-sm text-slate-500">角色卡直接归属 Story，不再经过 Workspace 资源挂载。</p>
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

      <div className="grid gap-5 2xl:grid-cols-[360px_minmax(0,1fr)_380px]">
        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-lg font-bold text-slate-950">角色列表</h2>
            <button
              type="button"
              onClick={() => createMutation.mutate()}
              disabled={!storyId || createMutation.isPending}
              className="inline-flex h-10 items-center gap-2 rounded-lg bg-violet-600 px-3 text-sm font-bold text-white disabled:opacity-50"
            >
              {createMutation.isPending ? <Loader2 size={16} className="animate-spin" /> : <FilePlus2 size={16} />}
              新建
            </button>
          </div>
          <label className="mt-4 flex h-10 items-center gap-2 rounded-lg border border-slate-200 px-3 text-sm text-slate-500 focus-within:border-violet-300">
            <Search size={16} />
            <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜索当前 Story 的角色…" className="min-w-0 flex-1 outline-none" />
          </label>
          <div className="mt-4 max-h-[720px] space-y-2 overflow-y-auto">
            {charactersQuery.isLoading ? <p className="py-10 text-center text-sm text-slate-400">加载中…</p> : null}
            {!charactersQuery.isLoading && !filtered.length ? <p className="py-10 text-center text-sm text-slate-400">当前 Story 暂无角色</p> : null}
            {filtered.map((character) => (
              <button
                key={character.id}
                type="button"
                onClick={() => setSelectedId(character.id)}
                className={`w-full rounded-xl border p-3 text-left transition ${character.id === selectedId ? 'border-violet-400 bg-violet-50' : 'border-slate-200 hover:border-violet-200'}`}
              >
                <div className="flex items-start justify-between gap-3">
                  <strong className="truncate text-sm text-slate-950">{character.name}</strong>
                  <span className="rounded-full bg-slate-100 px-2 py-1 text-[11px] font-bold text-slate-500">#{character.id}</span>
                </div>
                <p className="mt-2 line-clamp-2 text-xs leading-5 text-slate-500">{character.personality || character.content || '暂无设定'}</p>
                <p className="mt-2 text-[11px] font-semibold text-slate-400">{character.details.length} 条细节 · {formatDate(character.updatedAt)}</p>
              </button>
            ))}
          </div>
        </section>

        <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-lg font-bold text-slate-950">{selected?.name ?? '角色编辑'}</h2>
              <p className="mt-1 text-xs text-slate-400">只影响当前 Story 与其后续 turn。</p>
            </div>
            <div className="flex gap-2">
              <button type="button" onClick={() => setDeleteOpen(true)} disabled={!selected} className="inline-flex h-10 items-center gap-2 rounded-lg border border-rose-200 px-3 text-sm font-bold text-rose-700 disabled:opacity-40"><Trash2 size={16} />删除</button>
              <button type="button" onClick={() => saveMutation.mutate()} disabled={!selected || saveMutation.isPending} className="inline-flex h-10 items-center gap-2 rounded-lg bg-violet-600 px-4 text-sm font-bold text-white disabled:opacity-50">{saveMutation.isPending ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}保存</button>
            </div>
          </div>
          <div className="mt-6 grid gap-5">
            <label className="grid gap-2 text-sm font-bold text-slate-700">角色名<input disabled={!selected} value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} className="h-11 rounded-lg border border-slate-200 px-3 outline-none focus:border-violet-300 disabled:bg-slate-50" /></label>
            <div className="grid gap-5 md:grid-cols-[minmax(0,1fr)_140px]">
              <label className="grid gap-2 text-sm font-bold text-slate-700">人格摘要<textarea disabled={!selected} value={draft.personality} onChange={(event) => setDraft({ ...draft, personality: event.target.value })} className="min-h-24 rounded-lg border border-slate-200 px-3 py-3 leading-6 outline-none focus:border-violet-300 disabled:bg-slate-50" /></label>
              <label className="grid content-start gap-2 text-sm font-bold text-slate-700">排序<input disabled={!selected} type="number" value={draft.sortOrder} onChange={(event) => setDraft({ ...draft, sortOrder: Number(event.target.value) || 0 })} className="h-11 rounded-lg border border-slate-200 px-3 outline-none disabled:bg-slate-50" /></label>
            </div>
            <label className="grid gap-2 text-sm font-bold text-slate-700">完整角色卡<textarea disabled={!selected} value={draft.content} onChange={(event) => setDraft({ ...draft, content: event.target.value })} className="min-h-64 rounded-lg border border-slate-200 px-3 py-3 font-mono text-sm leading-7 outline-none focus:border-violet-300 disabled:bg-slate-50" /></label>
            <label className="grid gap-2 text-sm font-bold text-slate-700">Metadata JSON<textarea disabled={!selected} value={draft.metadataText} onChange={(event) => setDraft({ ...draft, metadataText: event.target.value })} className="min-h-36 rounded-lg border border-slate-200 bg-slate-50 px-3 py-3 font-mono text-xs leading-6 outline-none focus:border-violet-300" /></label>
          </div>
        </section>

        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex items-center justify-between gap-3">
            <div><h2 className="text-lg font-bold text-slate-950">角色细节</h2><p className="mt-1 text-xs text-slate-400">服装、关系、经历等可拆分条目</p></div>
            <button type="button" onClick={() => openDetail(null)} disabled={!selected} className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-violet-200 px-3 text-xs font-bold text-violet-700 disabled:opacity-40"><Plus size={15} />添加</button>
          </div>
          <div className="mt-4 space-y-3">
            {selected?.details.length ? [...selected.details].sort((a, b) => a.sortOrder - b.sortOrder || a.id - b.id).map((detail) => (
              <article key={detail.id} className="rounded-xl border border-slate-200 p-4">
                <button type="button" onClick={() => openDetail(detail)} className="w-full text-left">
                  <strong className="text-sm text-slate-900">{detail.name}</strong>
                  <p className="mt-2 line-clamp-3 whitespace-pre-wrap text-xs leading-5 text-slate-500">{detail.content || '暂无正文'}</p>
                  <div className="mt-3 flex flex-wrap gap-1">{detail.tags.map((tag) => <span key={tag} className="rounded bg-violet-50 px-2 py-1 text-[11px] font-bold text-violet-700">#{tag}</span>)}</div>
                </button>
                <button type="button" onClick={() => setDetailDeleteTarget(detail)} className="mt-3 text-xs font-bold text-rose-600">删除条目</button>
              </article>
            )) : <p className="py-12 text-center text-sm text-slate-400">暂无角色细节</p>}
          </div>
        </section>
      </div>

      {detailOpen ? (
        <Dialog title={editingDetailId ? '编辑角色细节' : '新增角色细节'} onClose={() => setDetailOpen(false)}>
          <div className="grid gap-4 px-6 py-5">
            <label className="grid gap-2 text-sm font-bold">名称<input value={detailForm.name} onChange={(event) => setDetailForm({ ...detailForm, name: event.target.value })} className="h-11 rounded-lg border border-slate-200 px-3" /></label>
            <label className="grid gap-2 text-sm font-bold">正文<textarea value={detailForm.content} onChange={(event) => setDetailForm({ ...detailForm, content: event.target.value })} className="min-h-40 rounded-lg border border-slate-200 px-3 py-3 leading-7" /></label>
            <div className="grid gap-4 sm:grid-cols-[minmax(0,1fr)_140px]">
              <label className="grid gap-2 text-sm font-bold">标签<input value={detailForm.tagsText} onChange={(event) => setDetailForm({ ...detailForm, tagsText: event.target.value })} placeholder="关系, 外观, 秘密" className="h-11 rounded-lg border border-slate-200 px-3" /></label>
              <label className="grid gap-2 text-sm font-bold">排序<input type="number" value={detailForm.sortOrder} onChange={(event) => setDetailForm({ ...detailForm, sortOrder: Number(event.target.value) || 0 })} className="h-11 rounded-lg border border-slate-200 px-3" /></label>
            </div>
          </div>
          <footer className="flex justify-end gap-2 border-t border-slate-200 bg-slate-50 px-6 py-4"><button type="button" onClick={() => setDetailOpen(false)} className="h-10 rounded-lg border border-slate-200 bg-white px-4 text-sm font-bold">取消</button><button type="button" onClick={() => saveDetailMutation.mutate()} disabled={saveDetailMutation.isPending} className="inline-flex h-10 items-center gap-2 rounded-lg bg-violet-600 px-4 text-sm font-bold text-white disabled:opacity-50">{saveDetailMutation.isPending ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}保存</button></footer>
        </Dialog>
      ) : null}

      {deleteOpen && selected ? <ConfirmDialog title="删除 Story 角色" heading={`确定删除「${selected.name}」？`} body="该角色会从当前 Story 移除；引用它的玩家角色绑定将变为 invalid，关联状态表的角色外键会被置空。" pending={deleteMutation.isPending} onClose={() => setDeleteOpen(false)} onConfirm={() => deleteMutation.mutate()} /> : null}
      {detailDeleteTarget ? <ConfirmDialog title="删除角色细节" heading={`确定删除「${detailDeleteTarget.name}」？`} body="此操作只删除当前角色下的细节条目。" pending={deleteDetailMutation.isPending} onClose={() => setDetailDeleteTarget(null)} onConfirm={() => deleteDetailMutation.mutate(detailDeleteTarget.id)} /> : null}
    </div>
  )
}

export function CharactersPage() {
  return <AppShell><CharactersContent /></AppShell>
}
