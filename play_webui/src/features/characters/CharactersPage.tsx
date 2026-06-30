'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Bold,
  Check,
  Eye,
  FilePlus2,
  GripVertical,
  ImagePlus,
  Italic,
  List,
  Loader2,
  Plus,
  Save,
  Search,
  Trash2,
  Type,
  UploadCloud,
  UserRound,
  X,
} from 'lucide-react'
import { AppShell, useAppShell } from '@/features/layout/AppShell'
import {
  createCharacter,
  createCharacterDetail,
  deleteCharacter,
  deleteCharacterDetail,
  listCharacters,
  listStories,
  listStoryCharacters,
  mountCharacter,
  unmountCharacter,
  updateCharacter,
  updateCharacterDetail,
} from '@/lib/api/characters'
import type { CharacterCard, CharacterDetail, CharacterDetailInput, CharacterInput, StorySummary } from '@/types/characters'

type Draft = CharacterInput & {
  metadataText: string
}

type DetailDraft = CharacterDetailInput & {
  tagInput: string
}

const emptyDraft: Draft = {
  name: '',
  personality: '',
  content: '',
  metadata: {},
  metadataText: '{\n  "ui": {}\n}',
}

const emptyDetailDraft: DetailDraft = {
  name: '',
  content: '',
  tags: [],
  sortOrder: 0,
  tagInput: '',
}

function formatDate(value?: string | null) {
  if (!value) return '暂无'
  return value.replace('T', ' ').slice(0, 16)
}

function parseMetadataObject(metadataText: string) {
  try {
    const parsed = JSON.parse(metadataText || '{}')
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed as Record<string, unknown> : {}
  } catch {
    return {}
  }
}

function setMetadataAvatar(metadataText: string, avatarUrl: string) {
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
  if (avatarUrl) {
    ui.avatarUrl = avatarUrl
  } else {
    delete ui.avatarUrl
  }
  metadata.ui = ui
  return JSON.stringify(metadata, null, 2)
}

function readFileAsDataUrl(file: File) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result || ''))
    reader.onerror = () => reject(reader.error)
    reader.readAsDataURL(file)
  })
}

function draftFromCharacter(character: CharacterCard | null): Draft {
  if (!character) return emptyDraft
  return {
    name: character.name,
    personality: character.personality,
    content: character.content,
    metadata: character.metadata,
    metadataText: JSON.stringify(character.metadata ?? {}, null, 2),
  }
}

function detailDraftFromDetail(detail: CharacterDetail | null): DetailDraft {
  if (!detail) return emptyDetailDraft
  return {
    name: detail.name,
    content: detail.content,
    tags: detail.tags,
    sortOrder: detail.sortOrder,
    tagInput: '',
  }
}

function metadataVersion(character: CharacterCard | null) {
  const ui = character?.metadata?.ui
  if (ui && typeof ui === 'object' && 'displayVersion' in ui) {
    const value = (ui as { displayVersion?: unknown }).displayVersion
    if (typeof value === 'string' && value) return value
  }
  return `v${character?.version ?? 1}`
}

function getUiString(metadata: Record<string, unknown> | undefined, key: string) {
  const ui = metadata?.ui
  if (ui && typeof ui === 'object' && key in ui) {
    const value = (ui as Record<string, unknown>)[key]
    if (typeof value === 'string' && value) return value
  }
  return ''
}

function normalizeTag(value: string) {
  return value.trim().replace(/^#/, '')
}

function insertMarkdown(content: string, marker: string) {
  if (marker === 'heading') return `${content}${content ? '\n' : ''}## 标题`
  if (marker === 'list') return `${content}${content ? '\n' : ''}- 条目`
  if (marker === 'quote') return `${content}${content ? '\n' : ''}> 引用`
  if (marker === 'bold') return `${content}**文本**`
  if (marker === 'italic') return `${content}*文本*`
  return content
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
      <section className="w-full max-w-3xl overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl shadow-slate-300/70">
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

function CharacterVisual({ character }: { character: CharacterCard }) {
  const avatarUrl = getUiString(character.metadata, 'avatarUrl')
  return (
    <div className="relative h-16 w-16 shrink-0 overflow-hidden rounded-xl bg-gradient-to-br from-slate-700 via-slate-500 to-indigo-200">
      {avatarUrl ? (
        <img src={avatarUrl} alt="" className="h-full w-full object-cover" />
      ) : (
        <>
          <div className="absolute left-1/2 top-3 h-6 w-6 -translate-x-1/2 rounded-full bg-white/55" />
          <div className="absolute bottom-1 left-1/2 h-9 w-12 -translate-x-1/2 rounded-t-full bg-white/35" />
          <div className="absolute inset-x-0 bottom-0 h-4 bg-slate-950/15" />
        </>
      )}
    </div>
  )
}

function DetailTagEditor({
  draft,
  onChange,
}: {
  draft: DetailDraft
  onChange: (draft: DetailDraft) => void
}) {
  function addTag(value: string) {
    const tag = normalizeTag(value)
    if (!tag || draft.tags.includes(tag)) return
    onChange({ ...draft, tags: [...draft.tags, tag], tagInput: '' })
  }

  function removeTag(tag: string) {
    onChange({ ...draft, tags: draft.tags.filter((item) => item !== tag) })
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white px-3 py-2 transition focus-within:border-violet-300 focus-within:ring-4 focus-within:ring-violet-100">
      <div className="flex min-h-9 flex-wrap items-center gap-2">
        {draft.tags.map((tag) => (
          <span key={tag} className="inline-flex h-7 items-center gap-1 rounded-lg bg-violet-100 px-2 text-xs font-semibold text-violet-700">
            {tag}
            <button
              type="button"
              aria-label={`删除标签 ${tag}`}
              onClick={() => removeTag(tag)}
              className="flex h-4 w-4 items-center justify-center rounded text-violet-500 transition hover:bg-violet-200 hover:text-violet-800"
            >
              <X size={12} />
            </button>
          </span>
        ))}
        <input
          value={draft.tagInput}
          onChange={(event) => {
            const value = event.target.value
            if (/[,\s，、]$/.test(value)) {
              const nextTags = [...draft.tags]
              value.split(/[,\s，、]+/).forEach((item) => {
                const tag = normalizeTag(item)
                if (tag && !nextTags.includes(tag)) nextTags.push(tag)
              })
              onChange({ ...draft, tags: nextTags, tagInput: '' })
              return
            }
            onChange({ ...draft, tagInput: value })
          }}
          onKeyDown={(event) => {
            if (event.key === 'Enter' || event.key === ',') {
              event.preventDefault()
              addTag(draft.tagInput)
            }
            if (event.key === 'Backspace' && !draft.tagInput && draft.tags.length) {
              removeTag(draft.tags[draft.tags.length - 1])
            }
          }}
          onBlur={() => addTag(draft.tagInput)}
          placeholder={draft.tags.length ? '继续添加标签...' : '输入标签后回车添加...'}
          className="h-7 min-w-32 flex-1 bg-transparent text-sm text-slate-900 outline-none placeholder:text-slate-400"
        />
      </div>
    </div>
  )
}

function CharactersContent() {
  const { currentWorkspace } = useAppShell()
  const queryClient = useQueryClient()
  const textareaRef = useRef<HTMLTextAreaElement | null>(null)
  const [selectedCharacterId, setSelectedCharacterId] = useState<number | null>(null)
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState('全部')
  const [draft, setDraft] = useState<Draft>(emptyDraft)
  const [preview, setPreview] = useState(false)
  const [mountDialogOpen, setMountDialogOpen] = useState(false)
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [avatarDialogOpen, setAvatarDialogOpen] = useState(false)
  const [avatarInput, setAvatarInput] = useState('')
  const [detailDialogOpen, setDetailDialogOpen] = useState(false)
  const [detailDeleteTarget, setDetailDeleteTarget] = useState<CharacterDetail | null>(null)
  const [editingDetailId, setEditingDetailId] = useState<number | null>(null)
  const [detailDraft, setDetailDraft] = useState<DetailDraft>(emptyDetailDraft)

  const storiesQuery = useQuery({
    queryKey: ['play-stories', currentWorkspace],
    queryFn: () => listStories(currentWorkspace ?? ''),
    enabled: Boolean(currentWorkspace),
  })
  const charactersQuery = useQuery({
    queryKey: ['play-characters', currentWorkspace],
    queryFn: () => listCharacters(currentWorkspace ?? ''),
    enabled: Boolean(currentWorkspace),
  })
  const stories = storiesQuery.data ?? []
  const characters = charactersQuery.data ?? []
  const storyCharacterQueries = useQueries({
    queries: stories.map((story) => ({
      queryKey: ['play-story-characters', currentWorkspace, story.id],
      queryFn: () => listStoryCharacters(currentWorkspace ?? '', story.id),
      enabled: Boolean(currentWorkspace),
    })),
  })
  const storyCharacterGroups = useMemo(
    () => stories.map((story, index) => ({ story, characters: storyCharacterQueries[index]?.data ?? [] })),
    [stories, storyCharacterQueries],
  )
  const mountedIds = useMemo(() => {
    const ids = new Set<number>()
    storyCharacterGroups.forEach((group) => {
      group.characters.forEach((character) => ids.add(character.id))
    })
    return ids
  }, [storyCharacterGroups])
  const selectedCharacter = characters.find((character) => character.id === selectedCharacterId) ?? null
  const selectedCharacterMounts = useMemo(
    () => storyCharacterGroups.flatMap((group) => (
      group.characters
        .filter((character) => selectedCharacter && character.id === selectedCharacter.id && character.mountId)
        .map((character) => ({ story: group.story, character }))
    )),
    [selectedCharacter, storyCharacterGroups],
  )
  const selectedDetails = useMemo(
    () => [...(selectedCharacter?.details ?? [])].sort((first, second) => first.sortOrder - second.sortOrder || first.id - second.id),
    [selectedCharacter],
  )
  const filterOptions = useMemo(() => {
    const roles: string[] = []
    characters.forEach((character) => {
      const role = getUiString(character.metadata, 'roleLabel')
      if (role && !roles.includes(role)) roles.push(role)
    })
    return ['全部', '已挂载', '未挂载', ...roles.slice(0, 10)]
  }, [characters])

  useEffect(() => {
    if (!selectedCharacterId && characters.length) setSelectedCharacterId(characters[0].id)
    if (selectedCharacterId && characters.length && !characters.some((character) => character.id === selectedCharacterId)) {
      setSelectedCharacterId(characters[0].id)
    }
  }, [characters, selectedCharacterId])

  useEffect(() => {
    setDraft(draftFromCharacter(selectedCharacter))
    setAvatarInput(getUiString(selectedCharacter?.metadata, 'avatarUrl'))
    setPreview(false)
  }, [selectedCharacter])

  useEffect(() => {
    if (!filterOptions.includes(filter)) setFilter('全部')
  }, [filter, filterOptions])

  const filteredCharacters = characters.filter((character) => {
    const query = search.trim().toLowerCase()
    const role = getUiString(character.metadata, 'roleLabel')
    const detailText = character.details.map((detail) => `${detail.name} ${detail.content} ${detail.tags.join(' ')}`).join(' ')
    const matchesSearch = !query || `${character.name} ${character.personality} ${character.content} ${role} ${detailText}`.toLowerCase().includes(query)
    const matchesFilter =
      filter === '全部'
      || (filter === '已挂载' ? mountedIds.has(character.id) : filter === '未挂载' ? !mountedIds.has(character.id) : role === filter)
    return matchesSearch && matchesFilter
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
  const draftAvatarUrl = getUiString(draftMetadata, 'avatarUrl')

  function invalidateCharacters() {
    queryClient.invalidateQueries({ queryKey: ['play-characters', currentWorkspace] })
    stories.forEach((story) => {
      queryClient.invalidateQueries({ queryKey: ['play-story-characters', currentWorkspace, story.id] })
    })
  }

  const createMutation = useMutation({
    mutationFn: () => {
      if (!currentWorkspace) throw new Error('workspace missing')
      return createCharacter(currentWorkspace, {
        name: '未命名角色',
        personality: '',
        content: '',
        metadata: { ui: {} },
      })
    },
    onSuccess: (character) => {
      queryClient.setQueryData<CharacterCard[]>(['play-characters', currentWorkspace], (current) => {
        const existing = current ?? []
        return existing.some((item) => item.id === character.id)
          ? existing.map((item) => item.id === character.id ? character : item)
          : [character, ...existing]
      })
      setSelectedCharacterId(character.id)
      setDraft(draftFromCharacter(character))
      queryClient.invalidateQueries({ queryKey: ['play-characters', currentWorkspace] })
    },
  })

  const saveMutation = useMutation({
    mutationFn: () => {
      if (!currentWorkspace || !selectedCharacter) throw new Error('character missing')
      return updateCharacter(currentWorkspace, selectedCharacter.id, {
        name: draft.name,
        personality: draft.personality,
        content: draft.content,
        metadata: JSON.parse(draft.metadataText || '{}') as Record<string, unknown>,
      })
    },
    onSuccess: (character) => {
      setSelectedCharacterId(character.id)
      invalidateCharacters()
    },
  })

  const deleteMutation = useMutation({
    mutationFn: () => {
      if (!currentWorkspace || !selectedCharacter) throw new Error('character missing')
      return deleteCharacter(currentWorkspace, selectedCharacter.id)
    },
    onSuccess: () => {
      setDeleteDialogOpen(false)
      setSelectedCharacterId(null)
      setDraft(emptyDraft)
      invalidateCharacters()
    },
  })

  const avatarMutation = useMutation({
    mutationFn: (avatarUrl: string) => {
      if (!currentWorkspace || !selectedCharacter) throw new Error('character missing')
      const nextMetadata = parseMetadataObject(setMetadataAvatar(draft.metadataText, avatarUrl))
      return updateCharacter(currentWorkspace, selectedCharacter.id, { metadata: nextMetadata })
    },
    onSuccess: (character) => {
      setSelectedCharacterId(character.id)
      setDraft(draftFromCharacter(character))
      setAvatarInput(getUiString(character.metadata, 'avatarUrl'))
      setAvatarDialogOpen(false)
      invalidateCharacters()
    },
  })

  const mountMutation = useMutation({
    mutationFn: ({ storyId, characterId }: { storyId: number; characterId: number }) => {
      if (!currentWorkspace) throw new Error('workspace missing')
      return mountCharacter(currentWorkspace, storyId, characterId)
    },
    onSuccess: (_character, variables) => {
      queryClient.invalidateQueries({ queryKey: ['play-story-characters', currentWorkspace, variables.storyId] })
    },
  })

  const unmountMutation = useMutation({
    mutationFn: ({ storyId, mountId }: { storyId: number; mountId: number }) => {
      if (!currentWorkspace) throw new Error('workspace missing')
      return unmountCharacter(currentWorkspace, storyId, mountId)
    },
    onSuccess: (_result, variables) => {
      queryClient.invalidateQueries({ queryKey: ['play-story-characters', currentWorkspace, variables.storyId] })
      queryClient.invalidateQueries({ queryKey: ['play-characters', currentWorkspace] })
    },
  })

  const saveDetailMutation = useMutation({
    mutationFn: () => {
      if (!currentWorkspace || !selectedCharacter) throw new Error('character missing')
      const input: CharacterDetailInput = {
        name: detailDraft.name,
        content: detailDraft.content,
        tags: detailDraft.tags,
        sortOrder: detailDraft.sortOrder,
      }
      if (editingDetailId) {
        return updateCharacterDetail(currentWorkspace, selectedCharacter.id, editingDetailId, input)
      }
      return createCharacterDetail(currentWorkspace, selectedCharacter.id, input)
    },
    onSuccess: () => {
      setDetailDialogOpen(false)
      setEditingDetailId(null)
      setDetailDraft(emptyDetailDraft)
      invalidateCharacters()
    },
  })

  const deleteDetailMutation = useMutation({
    mutationFn: (detailId: number) => {
      if (!currentWorkspace || !selectedCharacter) throw new Error('character missing')
      return deleteCharacterDetail(currentWorkspace, selectedCharacter.id, detailId)
    },
    onSuccess: () => {
      setDetailDeleteTarget(null)
      invalidateCharacters()
    },
  })

  function openDetailDialog(detail: CharacterDetail | null) {
    setEditingDetailId(detail?.id ?? null)
    setDetailDraft(detailDraftFromDetail(detail))
    setDetailDialogOpen(true)
  }

  return (
    <div className="min-w-0 px-5 py-8 xl:px-7">
      <section className="mb-6">
        <h1 className="text-3xl font-bold text-slate-950">角色库</h1>
        <p className="mt-2 text-sm text-slate-500">维护可挂载到故事中的角色设定、人格与细节条目</p>
      </section>

      <div className="grid gap-5 2xl:grid-cols-[420px_minmax(0,1fr)_420px]">
        <section className="min-w-0 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-lg font-bold text-slate-950">角色</h2>
            <button
              type="button"
              onClick={() => createMutation.mutate()}
              disabled={!currentWorkspace || createMutation.isPending}
              className="flex h-10 items-center gap-2 rounded-lg bg-violet-600 px-4 text-sm font-semibold text-white shadow-lg shadow-violet-200 transition hover:bg-violet-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {createMutation.isPending ? <Loader2 size={16} className="animate-spin" /> : <FilePlus2 size={16} />}
              新建角色
            </button>
          </div>

          <label className="mt-4 flex h-10 items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-500 focus-within:border-violet-300 focus-within:ring-4 focus-within:ring-violet-100">
            <Search size={16} />
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="搜索角色名或关键词..."
              className="min-w-0 flex-1 bg-transparent text-slate-900 outline-none placeholder:text-slate-400"
            />
          </label>

          <div className="mt-4 flex flex-wrap gap-2">
            {filterOptions.map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => setFilter(option)}
                className={`h-8 rounded-lg border px-3 text-xs font-semibold transition ${
                  filter === option
                    ? 'border-violet-400 bg-violet-50 text-violet-700'
                    : 'border-slate-200 bg-white text-slate-600 hover:border-violet-200 hover:text-violet-700'
                }`}
              >
                {option}
              </button>
            ))}
          </div>

          <div className="mt-5 max-h-[720px] space-y-3 overflow-y-auto pr-1">
            {charactersQuery.isLoading ? (
              <div className="rounded-xl border border-slate-200 px-4 py-6 text-center text-sm text-slate-500">加载中</div>
            ) : filteredCharacters.length ? filteredCharacters.map((character) => {
              const selected = character.id === selectedCharacterId
              const mounted = mountedIds.has(character.id)
              const role = getUiString(character.metadata, 'roleLabel') || '角色'
              return (
                <button
                  key={character.id}
                  type="button"
                  onClick={() => setSelectedCharacterId(character.id)}
                  className={`w-full rounded-xl border p-3 text-left transition ${
                    selected
                      ? 'border-violet-500 bg-violet-50/50 shadow-sm shadow-violet-100 dark:border-violet-400/60 dark:bg-violet-500/[0.08] dark:shadow-[0_0_0_1px_rgba(167,139,250,0.10)]'
                      : 'border-slate-200 bg-white hover:border-violet-200 hover:bg-violet-50/30 dark:border-slate-700/80 dark:bg-slate-900/70 dark:hover:border-violet-400/40 dark:hover:bg-slate-900/85'
                  }`}
                >
                  <div className="flex gap-3">
                    <CharacterVisual character={character} />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center justify-between gap-2">
                        <h3 className="truncate text-sm font-bold text-slate-950">{character.name}</h3>
                        <div className="flex shrink-0 gap-1">
                          {mounted ? <span className="rounded-full bg-emerald-100 px-2 py-1 text-[11px] font-bold text-emerald-700">已挂载</span> : null}
                          <span className="rounded-full bg-slate-100 px-2 py-1 text-[11px] font-bold text-slate-600">{role}</span>
                        </div>
                      </div>
                      <p className="mt-1 line-clamp-2 text-xs leading-5 text-slate-500">{character.personality || character.content || '暂无角色摘要'}</p>
                      <div className="mt-2 flex items-center gap-2 text-[11px] font-semibold text-slate-400">
                        <span>{metadataVersion(character)}</span>
                        <span>·</span>
                        <span>{formatDate(character.updatedAt)}</span>
                      </div>
                    </div>
                  </div>
                </button>
              )
            }) : (
              <div className="rounded-xl border border-slate-200 px-4 py-8 text-center text-sm text-slate-500">暂无角色</div>
            )}
          </div>
          <p className="mt-4 text-sm text-slate-500">共 {characters.length} 个角色</p>
        </section>

        <section className="min-w-0 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          <div className="space-y-5 p-6">
            <label className="grid gap-2 text-sm font-semibold text-slate-700">
              角色名
              <input
                value={draft.name}
                onChange={(event) => setDraft((current) => ({ ...current, name: event.target.value }))}
                disabled={!selectedCharacter}
                className="h-11 rounded-lg border border-slate-200 px-3 text-sm font-medium text-slate-900 outline-none transition focus:border-violet-300 focus:ring-4 focus:ring-violet-100 disabled:bg-slate-50"
              />
            </label>

            <label className="grid gap-2 text-sm font-semibold text-slate-700">
              人格摘要 / 口吻基调
              <textarea
                value={draft.personality}
                onChange={(event) => setDraft((current) => ({ ...current, personality: event.target.value }))}
                disabled={!selectedCharacter}
                className="min-h-20 resize-y rounded-lg border border-slate-200 px-3 py-3 text-sm leading-6 text-slate-800 outline-none transition focus:border-violet-300 focus:ring-4 focus:ring-violet-100 disabled:bg-slate-50"
              />
            </label>

            <section className="rounded-xl border border-slate-200 bg-slate-50/60 p-4">
              <div className="flex items-center justify-between gap-4">
                <div className="flex min-w-0 items-center gap-3">
                  <div className="relative h-16 w-16 shrink-0 overflow-hidden rounded-xl bg-gradient-to-br from-slate-700 via-slate-500 to-indigo-200">
                    {draftAvatarUrl ? (
                      <img src={draftAvatarUrl} alt="" className="h-full w-full object-cover" />
                    ) : (
                      <div className="flex h-full w-full items-center justify-center text-slate-300">
                        <ImagePlus size={22} />
                      </div>
                    )}
                  </div>
                  <div className="min-w-0">
                    <h3 className="text-sm font-bold text-slate-900">头像</h3>
                    <p className="mt-1 truncate text-xs text-slate-500">{draftAvatarUrl ? '已设置 avatarUrl' : '未设置头像'}</p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    setAvatarInput(draftAvatarUrl)
                    setAvatarDialogOpen(true)
                  }}
                  disabled={!selectedCharacter}
                  className="flex h-10 shrink-0 items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700 transition hover:border-violet-200 hover:text-violet-700 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <ImagePlus size={16} />
                  编辑
                </button>
              </div>
            </section>

            <div>
              <div className="mb-2 flex items-center justify-between">
                <label className="text-sm font-semibold text-slate-700">角色正文</label>
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
                      disabled={!selectedCharacter}
                      className="flex h-8 w-8 items-center justify-center rounded-md text-slate-600 transition hover:bg-white hover:text-violet-700 disabled:cursor-not-allowed disabled:opacity-40"
                    >
                      <item.icon size={15} />
                    </button>
                  ))}
                  <button
                    type="button"
                    title={preview ? '编辑' : '预览'}
                    onClick={() => setPreview((value) => !value)}
                    disabled={!selectedCharacter}
                    className={`ml-1 flex h-8 items-center gap-1 rounded-md px-2 text-xs font-semibold transition disabled:cursor-not-allowed disabled:opacity-40 ${
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
                  disabled={!selectedCharacter}
                  className="min-h-[360px] w-full resize-y rounded-lg border border-slate-200 px-4 py-3 text-sm leading-7 text-slate-800 outline-none transition focus:border-violet-300 focus:ring-4 focus:ring-violet-100 disabled:bg-slate-50"
                />
              )}
            </div>

            <details className="rounded-xl border border-slate-200 bg-slate-50/60 px-4 py-3">
              <summary className="cursor-pointer text-sm font-bold text-slate-800">高级 metadata_json</summary>
              <textarea
                value={draft.metadataText}
                onChange={(event) => setDraft((current) => ({ ...current, metadataText: event.target.value }))}
                disabled={!selectedCharacter}
                className="mt-3 min-h-32 w-full resize-y rounded-lg border border-slate-200 bg-white px-3 py-2 font-mono text-xs leading-6 text-slate-800 outline-none transition focus:border-violet-300 focus:ring-4 focus:ring-violet-100 disabled:bg-slate-50"
              />
              {metadataError ? <p className="mt-2 text-xs font-semibold text-rose-600">{metadataError}</p> : null}
            </details>
          </div>

          <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 bg-slate-50 px-6 py-4">
            {selectedCharacter ? (
              <div className="flex flex-wrap gap-4 text-xs text-slate-500">
                <span>版本 <b className="text-slate-700">{metadataVersion(selectedCharacter)}</b></span>
                <span>创建 {formatDate(selectedCharacter.createdAt)}</span>
                <span>更新 {formatDate(selectedCharacter.updatedAt)}</span>
              </div>
            ) : <span className="text-sm text-slate-500">请选择角色</span>}
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setDraft(draftFromCharacter(selectedCharacter))}
                disabled={!selectedCharacter || saveMutation.isPending}
                className="h-10 rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700 transition hover:border-violet-200 hover:text-violet-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                取消
              </button>
              <button
                type="button"
                onClick={() => saveMutation.mutate()}
                disabled={!selectedCharacter || Boolean(metadataError) || !draft.name.trim() || saveMutation.isPending}
                className="flex h-10 items-center gap-2 rounded-lg bg-violet-600 px-4 text-sm font-semibold text-white shadow-lg shadow-violet-100 transition hover:bg-violet-700 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {saveMutation.isPending ? <Loader2 size={16} className="animate-spin" /> : <Check size={16} />}
                保存更改
              </button>
            </div>
          </footer>
        </section>

        <aside className="min-w-0 space-y-5">
          <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="mb-4 flex items-center justify-between gap-3">
              <h2 className="text-lg font-bold text-slate-950">故事挂载</h2>
              <button
                type="button"
                onClick={() => setMountDialogOpen(true)}
                disabled={!selectedCharacter || !stories.length}
                className="flex h-9 items-center gap-2 rounded-lg border border-violet-200 bg-violet-50 px-3 text-sm font-semibold text-violet-700 transition hover:border-violet-300 hover:bg-violet-100 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <Plus size={15} />
                添加挂载
              </button>
            </div>
            <div className="space-y-3">
              {selectedCharacterMounts.length ? selectedCharacterMounts.map(({ story, character }) => (
                <article key={`${story.id}-${character.mountId ?? character.id}`} className="flex items-center gap-3 rounded-xl border border-slate-200 p-3">
                  <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-violet-50 text-violet-600">
                    <UserRound size={20} />
                  </span>
                  <div className="min-w-0 flex-1">
                    <h3 className="truncate text-sm font-bold text-slate-950">{story.title}</h3>
                    <p className="mt-1 truncate text-xs text-slate-500">{story.summary || '暂无故事摘要'}</p>
                  </div>
                  <button
                    type="button"
                    aria-label={`移除 ${story.title}`}
                    onClick={() => character.mountId ? unmountMutation.mutate({ storyId: story.id, mountId: character.mountId }) : undefined}
                    disabled={!character.mountId || unmountMutation.isPending}
                    className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-slate-400 transition hover:bg-rose-50 hover:text-rose-600 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <Trash2 size={16} />
                  </button>
                </article>
              )) : (
                <div className="rounded-xl border border-slate-200 px-4 py-6 text-center text-sm text-slate-500">当前角色暂无故事挂载</div>
              )}
            </div>
          </section>

          <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="mb-4 flex items-center justify-between gap-3">
              <div>
                <h2 className="text-lg font-bold text-slate-950">角色细节</h2>
                <p className="mt-1 text-xs text-slate-500">Character Details</p>
              </div>
              <button
                type="button"
                onClick={() => openDetailDialog(null)}
                disabled={!selectedCharacter}
                className="flex h-9 items-center gap-2 rounded-lg bg-violet-600 px-3 text-sm font-semibold text-white shadow-lg shadow-violet-100 transition hover:bg-violet-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <Plus size={15} />
                添加细节
              </button>
            </div>
            <div className="space-y-3">
              {selectedDetails.length ? selectedDetails.map((detail) => (
                <article key={detail.id} className="rounded-xl border border-slate-200 p-4">
                  <div className="flex items-start gap-3">
                    <GripVertical size={17} className="mt-1 shrink-0 text-slate-300" />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <h3 className="truncate text-sm font-bold text-slate-950">{detail.name}</h3>
                          <p className="mt-1 line-clamp-2 text-xs leading-5 text-slate-500">{detail.content || '暂无内容'}</p>
                        </div>
                        <span className="shrink-0 text-xs font-semibold text-slate-500">排序 {detail.sortOrder}</span>
                      </div>
                      {detail.tags.length ? (
                        <div className="mt-3 flex flex-wrap gap-2">
                          {detail.tags.map((tag) => (
                            <span key={tag} className="rounded-lg bg-violet-50 px-2 py-1 text-[11px] font-semibold text-violet-700">{tag}</span>
                          ))}
                        </div>
                      ) : null}
                      <div className="mt-3 flex items-center justify-between gap-3 text-xs text-slate-400">
                        <span>v{detail.version} · {formatDate(detail.updatedAt)}</span>
                        <div className="flex gap-1">
                          <button
                            type="button"
                            onClick={() => openDetailDialog(detail)}
                            className="h-8 rounded-lg px-2 font-semibold text-slate-600 transition hover:bg-violet-50 hover:text-violet-700"
                          >
                            编辑
                          </button>
                          <button
                            type="button"
                            onClick={() => setDetailDeleteTarget(detail)}
                            disabled={deleteDetailMutation.isPending}
                            className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 transition hover:bg-rose-50 hover:text-rose-600 disabled:cursor-not-allowed disabled:opacity-50"
                            aria-label={`删除细节 ${detail.name}`}
                          >
                            <Trash2 size={15} />
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>
                </article>
              )) : (
                <div className="rounded-xl border border-slate-200 px-4 py-6 text-center text-sm text-slate-500">当前角色暂无细节</div>
              )}
            </div>
          </section>

          <button
            type="button"
            onClick={() => setDeleteDialogOpen(true)}
            disabled={!selectedCharacter}
            className="flex h-10 w-full items-center justify-center gap-2 rounded-lg border border-rose-200 bg-white text-sm font-semibold text-rose-600 transition hover:bg-rose-50 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Trash2 size={16} />
            删除角色
          </button>
        </aside>
      </div>

      {mountDialogOpen ? (
        <MountDialog
          stories={stories}
          selectedCharacter={selectedCharacter}
          selectedCharacterMounts={selectedCharacterMounts}
          mountPending={mountMutation.isPending}
          onClose={() => setMountDialogOpen(false)}
          onMount={(storyId, characterId) => mountMutation.mutate({ storyId, characterId })}
        />
      ) : null}

      {detailDialogOpen ? (
        <ModalShell title={editingDetailId ? '编辑角色细节' : '添加角色细节'} onClose={() => setDetailDialogOpen(false)}>
          <div className="space-y-4 px-6 py-5">
            <label className="grid gap-2 text-sm font-semibold text-slate-700">
              细节名
              <input
                value={detailDraft.name}
                onChange={(event) => setDetailDraft((current) => ({ ...current, name: event.target.value }))}
                className="h-10 rounded-lg border border-slate-200 px-3 text-sm text-slate-900 outline-none transition focus:border-violet-300 focus:ring-4 focus:ring-violet-100"
              />
            </label>
            <label className="grid gap-2 text-sm font-semibold text-slate-700">
              内容
              <textarea
                value={detailDraft.content}
                onChange={(event) => setDetailDraft((current) => ({ ...current, content: event.target.value }))}
                className="min-h-32 resize-y rounded-lg border border-slate-200 px-3 py-2 text-sm leading-6 text-slate-800 outline-none transition focus:border-violet-300 focus:ring-4 focus:ring-violet-100"
              />
            </label>
            <label className="grid gap-2 text-sm font-semibold text-slate-700">
              排序
              <input
                type="number"
                value={detailDraft.sortOrder}
                onChange={(event) => setDetailDraft((current) => ({ ...current, sortOrder: Number(event.target.value) || 0 }))}
                className="h-10 rounded-lg border border-slate-200 px-3 text-sm text-slate-900 outline-none transition focus:border-violet-300 focus:ring-4 focus:ring-violet-100"
              />
            </label>
            <div className="grid gap-2 text-sm font-semibold text-slate-700">
              标签
              <DetailTagEditor draft={detailDraft} onChange={setDetailDraft} />
            </div>
          </div>
          <footer className="flex items-center justify-end gap-2 border-t border-slate-200 bg-slate-50 px-6 py-4">
            <button
              type="button"
              onClick={() => setDetailDialogOpen(false)}
              className="h-10 rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700 transition hover:border-violet-200 hover:text-violet-700"
            >
              取消
            </button>
            <button
              type="button"
              onClick={() => saveDetailMutation.mutate()}
              disabled={!detailDraft.name.trim() || saveDetailMutation.isPending}
              className="flex h-10 items-center gap-2 rounded-lg bg-violet-600 px-4 text-sm font-semibold text-white shadow-lg shadow-violet-100 transition hover:bg-violet-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {saveDetailMutation.isPending ? <Loader2 size={16} className="animate-spin" /> : <Check size={16} />}
              保存
            </button>
          </footer>
        </ModalShell>
      ) : null}

      {avatarDialogOpen ? (
        <ModalShell title="编辑头像" onClose={() => setAvatarDialogOpen(false)}>
          <div className="grid gap-5 px-6 py-5 md:grid-cols-[220px_minmax(0,1fr)]">
            <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
              <div className="relative aspect-square overflow-hidden rounded-xl bg-gradient-to-br from-slate-700 via-slate-500 to-indigo-200">
                {avatarInput ? (
                  <img src={avatarInput} alt="" className="h-full w-full object-cover" />
                ) : (
                  <div className="flex h-full w-full items-center justify-center text-slate-300">
                    <ImagePlus size={34} />
                  </div>
                )}
              </div>
              <p className="mt-3 text-xs leading-5 text-slate-500">头像保存到 metadata_json.ui.avatarUrl，可使用图片 URL 或上传本地图片。</p>
            </div>
            <div className="space-y-4">
              <label className="grid gap-2 text-sm font-semibold text-slate-700">
                图片 URL
                <input
                  value={avatarInput}
                  onChange={(event) => setAvatarInput(event.target.value)}
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
                    const dataUrl = await readFileAsDataUrl(file)
                    setAvatarInput(dataUrl)
                    event.target.value = ''
                  }}
                />
              </label>
            </div>
          </div>
          <footer className="flex items-center justify-between border-t border-slate-200 bg-slate-50 px-6 py-4">
            <button
              type="button"
              onClick={() => avatarMutation.mutate('')}
              disabled={!selectedCharacter || Boolean(metadataError) || avatarMutation.isPending}
              className="h-10 rounded-lg border border-rose-200 bg-white px-4 text-sm font-semibold text-rose-600 transition hover:bg-rose-50 disabled:cursor-not-allowed disabled:opacity-50"
            >
              清除头像
            </button>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setAvatarDialogOpen(false)}
                className="h-10 rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700 transition hover:border-violet-200 hover:text-violet-700"
              >
                取消
              </button>
              <button
                type="button"
                onClick={() => avatarMutation.mutate(avatarInput.trim())}
                disabled={!selectedCharacter || Boolean(metadataError) || avatarMutation.isPending}
                className="flex h-10 items-center gap-2 rounded-lg bg-violet-600 px-4 text-sm font-semibold text-white shadow-lg shadow-violet-100 transition hover:bg-violet-700 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {avatarMutation.isPending ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
                保存头像
              </button>
            </div>
          </footer>
        </ModalShell>
      ) : null}

      {deleteDialogOpen ? (
        <ModalShell title="删除角色" onClose={() => setDeleteDialogOpen(false)}>
          <div className="px-6 py-5">
            <div className="rounded-2xl border border-rose-100 bg-rose-50 px-4 py-4">
              <h3 className="text-sm font-bold text-rose-700">确认删除「{selectedCharacter?.name ?? '当前角色'}」？</h3>
              <p className="mt-2 text-sm leading-6 text-rose-700/80">
                删除后会同时移除它在所有故事里的挂载关系和角色细节。这个操作不会删除其它角色。
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
              disabled={!selectedCharacter || deleteMutation.isPending}
              className="flex h-10 items-center gap-2 rounded-lg bg-rose-600 px-4 text-sm font-semibold text-white shadow-lg shadow-rose-100 transition hover:bg-rose-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {deleteMutation.isPending ? <Loader2 size={16} className="animate-spin" /> : <Trash2 size={16} />}
              删除
            </button>
          </footer>
        </ModalShell>
      ) : null}

      {detailDeleteTarget ? (
        <ModalShell title="删除角色细节" onClose={() => setDetailDeleteTarget(null)}>
          <div className="px-6 py-5">
            <div className="rounded-2xl border border-rose-100 bg-rose-50 px-4 py-4">
              <h3 className="text-sm font-bold text-rose-700">确认删除「{detailDeleteTarget.name}」？</h3>
              <p className="mt-2 text-sm leading-6 text-rose-700/80">
                删除后会从当前角色卡中移除该细节条目。这个操作不会删除角色本体，也不会影响其它细节。
              </p>
            </div>
          </div>
          <footer className="flex items-center justify-end gap-2 border-t border-slate-200 bg-slate-50 px-6 py-4">
            <button
              type="button"
              onClick={() => setDetailDeleteTarget(null)}
              className="h-10 rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700 transition hover:border-violet-200 hover:text-violet-700"
            >
              取消
            </button>
            <button
              type="button"
              onClick={() => deleteDetailMutation.mutate(detailDeleteTarget.id)}
              disabled={deleteDetailMutation.isPending}
              className="flex h-10 items-center gap-2 rounded-lg bg-rose-600 px-4 text-sm font-semibold text-white shadow-lg shadow-rose-100 transition hover:bg-rose-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {deleteDetailMutation.isPending ? <Loader2 size={16} className="animate-spin" /> : <Trash2 size={16} />}
              删除
            </button>
          </footer>
        </ModalShell>
      ) : null}
    </div>
  )
}

function MountDialog({
  stories,
  selectedCharacter,
  selectedCharacterMounts,
  mountPending,
  onClose,
  onMount,
}: {
  stories: StorySummary[]
  selectedCharacter: CharacterCard | null
  selectedCharacterMounts: { story: StorySummary; character: CharacterCard }[]
  mountPending: boolean
  onClose: () => void
  onMount: (storyId: number, characterId: number) => void
}) {
  return (
    <ModalShell title="添加故事挂载" onClose={onClose}>
      <div className="border-b border-slate-200 bg-slate-50/70 px-6 py-4">
        <p className="text-sm text-slate-500">
          {selectedCharacter ? `将「${selectedCharacter.name}」添加到故事。` : '请先选择一个角色。'}
        </p>
      </div>
      <div className="max-h-[520px] overflow-y-auto px-5 py-5">
        <div className="rounded-2xl border border-slate-200 bg-white">
          {stories.length ? stories.map((story) => {
            const alreadyMountedInStory = selectedCharacterMounts.some((mount) => mount.story.id === story.id)
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
                  <p className="mt-1 line-clamp-2 text-xs leading-5 text-slate-500">{story.summary || '暂无故事摘要'}</p>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    if (selectedCharacter) onMount(story.id, selectedCharacter.id)
                  }}
                  disabled={!selectedCharacter || alreadyMountedInStory || mountPending}
                  className="flex h-10 items-center justify-center gap-2 rounded-lg bg-violet-600 px-4 text-sm font-semibold text-white shadow-lg shadow-violet-100 transition hover:bg-violet-700 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-500 disabled:shadow-none"
                >
                  {mountPending ? <Loader2 size={16} className="animate-spin" /> : alreadyMountedInStory ? <Check size={16} /> : <Plus size={16} />}
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
        <span>添加后右侧会显示当前角色的故事挂载。</span>
        <button
          type="button"
          onClick={onClose}
          className="h-9 rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700 transition hover:border-violet-200 hover:text-violet-700"
        >
          完成
        </button>
      </footer>
    </ModalShell>
  )
}

export function CharactersPage() {
  return (
    <AppShell>
      <CharactersContent />
    </AppShell>
  )
}
