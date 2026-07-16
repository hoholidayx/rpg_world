'use client'

import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, Database, Images, Loader2, RefreshCcw, Tags, Trash2, Upload } from 'lucide-react'
import { ConfirmDialog } from '@/components/common/Dialog'
import { AppShell, useAppShell } from '@/features/layout/AppShell'
import {
  analyzeMediaLibraryImage,
  batchDeleteMediaLibraryItems,
  batchUpdateMediaLibraryItems,
  getMediaLibrary,
  getMediaLibraryFacets,
  reconcileMediaLibrary,
  updateMediaLibraryItem,
  uploadMediaLibraryItem,
} from '@/lib/api/media'
import { listStories } from '@/lib/api/stories'
import type {
  MediaLibraryItem,
  MediaLibraryMetadataInput,
  MediaLibraryOrigin,
  MediaLibraryScope,
  MediaLibrarySort,
  MediaLibraryType,
} from '@/types/media'
import { MEDIA_LIBRARY_TYPES } from '@/types/media'
import { MEDIA_TYPE_LABELS, parseTags } from './constants'
import { MediaLibraryFilters } from './MediaLibraryFilters'
import { MediaLibraryGrid } from './MediaLibraryGrid'
import { MediaDetailDrawer, MediaImportDialog } from './MediaLibraryPanels'

const PAGE_SIZE = 48
const MAX_SELECTION = 100

function MediaLibraryContent() {
  const { currentWorkspace } = useAppShell()
  const queryClient = useQueryClient()
  const [hydrated, setHydrated] = useState(false)
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [mediaType, setMediaType] = useState<MediaLibraryType | 'all'>('all')
  const [scope, setScope] = useState<MediaLibraryScope | 'all'>('all')
  const [storyId, setStoryId] = useState<number | null>(null)
  const [origin, setOrigin] = useState<MediaLibraryOrigin | 'all'>('all')
  const [sort, setSort] = useState<MediaLibrarySort>('updated_desc')
  const [selectedTags, setSelectedTags] = useState<string[]>([])
  const [page, setPage] = useState(1)
  const [importOpen, setImportOpen] = useState(false)
  const [detailItem, setDetailItem] = useState<MediaLibraryItem | null>(null)
  const [selectedItems, setSelectedItems] = useState<Map<string, MediaLibraryItem>>(new Map())
  const [deleteTargets, setDeleteTargets] = useState<Map<string, MediaLibraryItem> | null>(null)
  const [batchType, setBatchType] = useState<MediaLibraryType | ''>('')
  const [batchAddTags, setBatchAddTags] = useState('')
  const [batchRemoveTags, setBatchRemoveTags] = useState('')
  const [message, setMessage] = useState('')

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const requestedType = params.get('mediaType')
    const requestedScope = params.get('scope')
    const requestedOrigin = params.get('origin')
    const requestedSort = params.get('sort')
    const requestedStory = Number(params.get('storyId'))
    const requestedPage = Number(params.get('page'))
    const requestedSearch = params.get('q') ?? ''
    setSearch(requestedSearch)
    setDebouncedSearch(requestedSearch)
    if (MEDIA_LIBRARY_TYPES.includes(requestedType as MediaLibraryType)) setMediaType(requestedType as MediaLibraryType)
    if (requestedScope === 'story' || requestedScope === 'workspace') setScope(requestedScope)
    if (requestedOrigin === 'generated' || requestedOrigin === 'upload') setOrigin(requestedOrigin)
    if (['updated_desc', 'created_desc', 'title_asc', 'size_desc'].includes(requestedSort ?? '')) setSort(requestedSort as MediaLibrarySort)
    if (Number.isFinite(requestedStory) && requestedStory > 0) setStoryId(requestedStory)
    if (Number.isFinite(requestedPage) && requestedPage > 0) setPage(requestedPage)
    setSelectedTags((params.get('tags') ?? '').split(',').map((tag) => tag.trim()).filter(Boolean))
    setHydrated(true)
  }, [])

  useEffect(() => {
    const timer = window.setTimeout(() => {
      if (debouncedSearch !== search) {
        setDebouncedSearch(search.trim())
        setPage(1)
        setSelectedItems(new Map())
      }
    }, 300)
    return () => window.clearTimeout(timer)
  }, [debouncedSearch, search])

  useEffect(() => {
    if (!hydrated) return
    const params = new URLSearchParams()
    if (debouncedSearch) params.set('q', debouncedSearch)
    if (mediaType !== 'all') params.set('mediaType', mediaType)
    if (scope !== 'all') params.set('scope', scope)
    if (storyId !== null) params.set('storyId', String(storyId))
    if (origin !== 'all') params.set('origin', origin)
    if (selectedTags.length) params.set('tags', selectedTags.join(','))
    if (sort !== 'updated_desc') params.set('sort', sort)
    if (page !== 1) params.set('page', String(page))
    const query = params.toString()
    window.history.replaceState(null, '', `${window.location.pathname}${query ? `?${query}` : ''}`)
  }, [debouncedSearch, hydrated, mediaType, origin, page, scope, selectedTags, sort, storyId])

  useEffect(() => {
    setSelectedItems(new Map())
    setDetailItem(null)
  }, [currentWorkspace])

  const storiesQuery = useQuery({
    queryKey: ['play-stories', currentWorkspace],
    queryFn: () => listStories(currentWorkspace ?? ''),
    enabled: Boolean(currentWorkspace),
  })
  const stories = useMemo(() => storiesQuery.data ?? [], [storiesQuery.data])
  useEffect(() => {
    if (storyId !== null && stories.length && !stories.some((story) => story.id === storyId)) {
      setStoryId(null)
      setPage(1)
    }
  }, [stories, storyId])

  const libraryOptions = useMemo(() => ({
    q: debouncedSearch || undefined,
    mediaTypes: mediaType === 'all' ? undefined : [mediaType],
    tags: selectedTags.length ? selectedTags : undefined,
    scope: scope === 'all' ? undefined : scope,
    storyId: storyId ?? undefined,
    origins: origin === 'all' ? undefined : [origin],
    sort,
    page,
    pageSize: PAGE_SIZE,
  }), [debouncedSearch, mediaType, origin, page, scope, selectedTags, sort, storyId])
  const libraryQuery = useQuery({
    queryKey: ['play-media-library', currentWorkspace, libraryOptions],
    queryFn: () => getMediaLibrary(currentWorkspace ?? '', libraryOptions),
    enabled: Boolean(currentWorkspace),
    retry: false,
  })
  const facetsQuery = useQuery({
    queryKey: ['play-media-library-facets', currentWorkspace],
    queryFn: () => getMediaLibraryFacets(currentWorkspace ?? ''),
    enabled: Boolean(currentWorkspace),
    retry: false,
  })
  useEffect(() => {
    if (!libraryQuery.data) return
    const pageCount = Math.max(1, Math.ceil(libraryQuery.data.total / PAGE_SIZE))
    if (page > pageCount) setPage(pageCount)
  }, [libraryQuery.data, page])

  async function invalidateLibrary() {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['play-media-library'] }),
      queryClient.invalidateQueries({ queryKey: ['play-media-library-facets'] }),
      queryClient.invalidateQueries({ queryKey: ['play-session-media-story-library'] }),
      queryClient.invalidateQueries({ queryKey: ['play-session-media-gallery'] }),
      queryClient.invalidateQueries({ queryKey: ['play-session-media-background'] }),
    ])
  }

  const reconcileMutation = useMutation({
    mutationFn: () => {
      if (!currentWorkspace) throw new Error('请先选择 Workspace')
      return reconcileMediaLibrary(currentWorkspace)
    },
    onSuccess: (result) => {
      setMessage(result.removedBlobs ? `同步完成，清理 ${result.removedAssets} 个失效 Asset` : '同步完成，未发现异常索引')
      void invalidateLibrary()
    },
  })
  const batchUpdateMutation = useMutation({
    mutationFn: () => {
      if (!currentWorkspace) throw new Error('请先选择 Workspace')
      return batchUpdateMediaLibraryItems(currentWorkspace, {
        itemIds: [...selectedItems.keys()],
        mediaType: batchType || undefined,
        addTags: parseTags(batchAddTags),
        removeTags: parseTags(batchRemoveTags),
      })
    },
    onSuccess: (result) => {
      setMessage(result.failed.length ? `已更新 ${result.succeededItemIds.length} 项，${result.failed.length} 项失败` : `已更新 ${result.succeededItemIds.length} 项资源`)
      const failedIds = new Set(result.failed.map((failure) => failure.itemId))
      setSelectedItems((current) => new Map([...current].filter(([itemId]) => failedIds.has(itemId))))
      setBatchType('')
      setBatchAddTags('')
      setBatchRemoveTags('')
      void invalidateLibrary()
    },
  })
  const deleteMutation = useMutation({
    mutationFn: (targets: Map<string, MediaLibraryItem>) => {
      if (!currentWorkspace) throw new Error('请先选择 Workspace')
      return batchDeleteMediaLibraryItems(currentWorkspace, [...targets.keys()])
    },
    onSuccess: (result) => {
      const failedIds = new Set(result.failed.map((failure) => failure.itemId))
      setMessage(result.failed.length ? `已删除 ${result.succeededItemIds.length} 项，${result.failed.length} 项因引用保护未删除` : `已删除 ${result.succeededItemIds.length} 项资源`)
      setSelectedItems((current) => new Map([...current].filter(([itemId]) => failedIds.has(itemId))))
      if (detailItem && result.succeededItemIds.includes(detailItem.itemId)) setDetailItem(null)
      setDeleteTargets(null)
      void invalidateLibrary()
    },
  })

  function changeFilter(action: () => void) {
    action()
    setPage(1)
    setSelectedItems(new Map())
  }

  function toggleSelection(item: MediaLibraryItem) {
    setSelectedItems((current) => {
      const next = new Map(current)
      if (next.has(item.itemId)) next.delete(item.itemId)
      else if (next.size < MAX_SELECTION) next.set(item.itemId, item)
      else setMessage(`一次最多选择 ${MAX_SELECTION} 项`)
      return next
    })
  }

  const deleteSummary = useMemo(() => {
    const items = [...(deleteTargets?.values() ?? [])]
    return {
      count: items.length,
      backgrounds: items.reduce((sum, item) => sum + item.backgroundReferences, 0),
      galleries: items.reduce((sum, item) => sum + item.galleryReferences, 0),
    }
  }, [deleteTargets])
  const batchHasAction = Boolean(batchType || parseTags(batchAddTags).length || parseTags(batchRemoveTags).length)

  return (
    <div className="min-w-0 px-5 py-8 xl:px-7">
      <header className="mb-6 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="mb-2 flex items-center gap-2 text-xs font-black uppercase tracking-[0.18em] text-violet-600"><Images size={15} /> rpg_media workspace</p>
          <h1 className="text-3xl font-black text-slate-950 dark:text-white">媒体库</h1>
          <p className="mt-2 max-w-3xl text-sm font-semibold leading-6 text-slate-500 dark:text-slate-300">用用途类型承载稳定业务语义，用 Tags 描述角色、地点、风格与场景。原图继续以内容哈希去重存储。</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button type="button" onClick={() => void libraryQuery.refetch()} disabled={libraryQuery.isFetching} className="inline-flex h-10 items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 text-sm font-black text-slate-600 disabled:opacity-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"><RefreshCcw size={15} className={libraryQuery.isFetching ? 'animate-spin' : ''} />刷新</button>
          <button type="button" onClick={() => reconcileMutation.mutate()} disabled={!currentWorkspace || reconcileMutation.isPending} title="只清理源文件缺失的数据库索引" className="inline-flex h-10 items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 text-sm font-black text-slate-600 disabled:opacity-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200">{reconcileMutation.isPending ? <Loader2 size={15} className="animate-spin" /> : <Database size={15} />}同步素材</button>
          <button type="button" onClick={() => setImportOpen(true)} disabled={!currentWorkspace} className="inline-flex h-10 items-center gap-2 rounded-lg bg-violet-600 px-4 text-sm font-black text-white shadow-lg shadow-violet-200 disabled:opacity-50 dark:shadow-violet-950/40"><Upload size={15} />导入图片</button>
        </div>
      </header>

      {message ? <div className="mb-4 flex items-center gap-2 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm font-bold text-emerald-700 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-200"><CheckCircle2 size={16} />{message}<button type="button" onClick={() => setMessage('')} className="ml-auto text-xs">关闭</button></div> : null}
      {reconcileMutation.isError ? <p className="mb-4 rounded-xl bg-rose-50 px-4 py-3 text-sm font-bold text-rose-700">{reconcileMutation.error instanceof Error ? reconcileMutation.error.message : '同步失败'}</p> : null}

      <MediaLibraryFilters
        search={search}
        onSearchChange={setSearch}
        mediaType={mediaType}
        onMediaTypeChange={(value) => changeFilter(() => setMediaType(value))}
        scope={scope}
        onScopeChange={(value) => changeFilter(() => { setScope(value); if (value === 'workspace') setStoryId(null) })}
        storyId={storyId}
        onStoryIdChange={(value) => changeFilter(() => { setStoryId(value); if (value !== null) setScope('story') })}
        origin={origin}
        onOriginChange={(value) => changeFilter(() => setOrigin(value))}
        sort={sort}
        onSortChange={(value) => changeFilter(() => setSort(value))}
        selectedTags={selectedTags}
        onAddTag={(tag) => changeFilter(() => setSelectedTags((current) => [...current, tag]))}
        onRemoveTag={(tag) => changeFilter(() => setSelectedTags((current) => current.filter((value) => value !== tag)))}
        onClear={() => changeFilter(() => { setSearch(''); setDebouncedSearch(''); setMediaType('all'); setScope('all'); setStoryId(null); setOrigin('all'); setSelectedTags([]); setSort('updated_desc') })}
        stories={stories}
        facets={facetsQuery.data}
      />

      {selectedItems.size ? (
        <section className="my-4 rounded-2xl border border-violet-200 bg-violet-50 p-4 dark:border-violet-500/30 dark:bg-violet-500/10">
          <div className="flex flex-col gap-3 xl:flex-row xl:items-end">
            <div className="shrink-0"><p className="text-sm font-black text-violet-900 dark:text-violet-100">已选择 {selectedItems.size} / {MAX_SELECTION} 项</p><button type="button" onClick={() => setSelectedItems(new Map())} className="mt-1 text-xs font-bold text-violet-600 dark:text-violet-300">取消选择</button></div>
            <label className="text-xs font-black text-violet-700 dark:text-violet-200">批量用途<select value={batchType} onChange={(event) => setBatchType(event.target.value as MediaLibraryType | '')} className="mt-1 h-10 w-full rounded-lg border border-violet-200 bg-white px-3 text-sm font-bold text-slate-700 dark:border-violet-500/30 dark:bg-slate-900 dark:text-slate-100"><option value="">保持不变</option>{MEDIA_LIBRARY_TYPES.map((value) => <option key={value} value={value}>{MEDIA_TYPE_LABELS[value]}</option>)}</select></label>
            <label className="min-w-48 flex-1 text-xs font-black text-violet-700 dark:text-violet-200">追加 Tags<input value={batchAddTags} onChange={(event) => setBatchAddTags(event.target.value)} placeholder="逗号分隔" className="mt-1 h-10 w-full rounded-lg border border-violet-200 bg-white px-3 text-sm font-semibold dark:border-violet-500/30 dark:bg-slate-900" /></label>
            <label className="min-w-48 flex-1 text-xs font-black text-violet-700 dark:text-violet-200">移除 Tags<input value={batchRemoveTags} onChange={(event) => setBatchRemoveTags(event.target.value)} placeholder="逗号分隔" className="mt-1 h-10 w-full rounded-lg border border-violet-200 bg-white px-3 text-sm font-semibold dark:border-violet-500/30 dark:bg-slate-900" /></label>
            <button type="button" onClick={() => batchUpdateMutation.mutate()} disabled={!batchHasAction || batchUpdateMutation.isPending} className="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-violet-600 px-4 text-sm font-black text-white disabled:opacity-40">{batchUpdateMutation.isPending ? <Loader2 size={15} className="animate-spin" /> : <Tags size={15} />}应用整理</button>
            <button type="button" onClick={() => setDeleteTargets(new Map(selectedItems))} className="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-rose-200 bg-white px-4 text-sm font-black text-rose-600 dark:bg-slate-900"><Trash2 size={15} />批量删除</button>
          </div>
          {batchUpdateMutation.isError ? <p className="mt-3 text-xs font-bold text-rose-600">{batchUpdateMutation.error instanceof Error ? batchUpdateMutation.error.message : '批量更新失败'}</p> : null}
        </section>
      ) : <div className="h-4" />}

      <MediaLibraryGrid
        items={libraryQuery.data?.items ?? []}
        total={libraryQuery.data?.total ?? 0}
        page={libraryQuery.data?.page ?? page}
        pageSize={libraryQuery.data?.pageSize ?? PAGE_SIZE}
        loading={libraryQuery.isLoading}
        error={libraryQuery.isError ? (libraryQuery.error instanceof Error ? libraryQuery.error.message : '加载失败') : null}
        selectedIds={new Set(selectedItems.keys())}
        onToggle={toggleSelection}
        onOpen={setDetailItem}
        onPageChange={setPage}
      />

      <MediaImportDialog
        open={importOpen}
        stories={stories}
        onClose={() => setImportOpen(false)}
        onAnalyze={(file) => {
          if (!currentWorkspace) return Promise.reject(new Error('请先选择 Workspace'))
          return analyzeMediaLibraryImage(currentWorkspace, file)
        }}
        onUpload={async (file, input) => {
          if (!currentWorkspace) throw new Error('请先选择 Workspace')
          await uploadMediaLibraryItem(currentWorkspace, file, input)
          setMessage('图片已导入媒体库')
          await invalidateLibrary()
        }}
      />
      <MediaDetailDrawer
        item={detailItem}
        stories={stories}
        onClose={() => setDetailItem(null)}
        onSave={async (item, input: MediaLibraryMetadataInput) => {
          if (!currentWorkspace) throw new Error('请先选择 Workspace')
          const updated = await updateMediaLibraryItem(currentWorkspace, item.itemId, input)
          setDetailItem(updated)
          setSelectedItems((current) => {
            if (!current.has(item.itemId)) return current
            const next = new Map(current)
            next.set(item.itemId, updated)
            return next
          })
          setMessage('素材信息已更新')
          await invalidateLibrary()
        }}
        onDelete={(item) => setDeleteTargets(new Map([[item.itemId, item]]))}
      />

      {deleteTargets ? (
        <ConfirmDialog
          title={deleteSummary.count > 1 ? '批量删除资源' : '删除资源'}
          heading={`将永久删除 ${deleteSummary.count} 项资源`}
          body={<><p>删除会移除对应 Asset；最后一个 Asset 引用消失时还会回收 Blob 文件。</p>{deleteSummary.galleries ? <p className="mt-2">其中关联 {deleteSummary.galleries} 个 Session Gallery 项，将一并移除。</p> : null}{deleteSummary.backgrounds ? <p className="mt-2 font-black">有 {deleteSummary.backgrounds} 个背景引用，相关资源会受到保护并返回失败。</p> : null}{deleteMutation.isError ? <p className="mt-2 font-black">{deleteMutation.error instanceof Error ? deleteMutation.error.message : '删除失败'}</p> : null}</>}
          pending={deleteMutation.isPending}
          onClose={() => setDeleteTargets(null)}
          onConfirm={() => deleteMutation.mutate(deleteTargets)}
        />
      ) : null}
    </div>
  )
}

export function MediaLibraryPage() {
  return <AppShell><MediaLibraryContent /></AppShell>
}
