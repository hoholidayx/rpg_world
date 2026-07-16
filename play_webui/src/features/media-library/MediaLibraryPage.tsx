'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  CheckCircle2,
  Database,
  ImagePlus,
  Images,
  Loader2,
  Pencil,
  RefreshCcw,
  Sparkles,
  Trash2,
  Upload,
} from 'lucide-react'
import { MediaImageFrame } from '@/components/common/MediaImageFrame'
import { AppShell, useAppShell } from '@/features/layout/AppShell'
import {
  analyzeMediaLibraryImage,
  deleteMediaLibraryItem,
  getMediaLibrary,
  mediaLibraryContentUrl,
  reconcileMediaLibrary,
  updateMediaLibraryItem,
  uploadMediaLibraryItem,
} from '@/lib/api/media'
import { ApiError } from '@/lib/api/errors'
import { listStories } from '@/lib/api/stories'
import type {
  MediaLibraryItem,
  MediaLibraryMetadataInput,
  MediaLibraryScope,
} from '@/types/media'

type ScopeFilter = 'all' | MediaLibraryScope
const IMAGE_ANALYSIS_UNSUPPORTED = 'MEDIA_IMAGE_ANALYSIS_UNSUPPORTED'

function parseTags(value: string) {
  return [...new Set(value.split(/[,，\n]/).map((tag) => tag.trim()).filter(Boolean))]
}

function formatBytes(value: number) {
  if (value < 1024 * 1024) return `${Math.max(1, Math.round(value / 1024))} KB`
  return `${(value / 1024 / 1024).toFixed(1)} MB`
}

function MediaLibraryContent() {
  const { currentWorkspace } = useAppShell()
  const queryClient = useQueryClient()
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const [scopeFilter, setScopeFilter] = useState<ScopeFilter>('all')
  const [storyFilter, setStoryFilter] = useState<number | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [scope, setScope] = useState<MediaLibraryScope>('story')
  const [storyId, setStoryId] = useState<number | null>(null)
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [tagsText, setTagsText] = useState('')
  const [isDefault, setIsDefault] = useState(false)
  const [editing, setEditing] = useState<MediaLibraryItem | null>(null)
  const [editTitle, setEditTitle] = useState('')
  const [editDescription, setEditDescription] = useState('')
  const [editTags, setEditTags] = useState('')
  const [editDefault, setEditDefault] = useState(false)
  const [message, setMessage] = useState('')
  const [analysisNotice, setAnalysisNotice] = useState('')

  const storiesQuery = useQuery({
    queryKey: ['play-stories', currentWorkspace],
    queryFn: () => listStories(currentWorkspace ?? ''),
    enabled: Boolean(currentWorkspace),
  })
  const stories = useMemo(() => storiesQuery.data ?? [], [storiesQuery.data])

  useEffect(() => {
    const requested = Number(new URLSearchParams(window.location.search).get('storyId'))
    if (Number.isFinite(requested) && requested > 0) {
      setStoryFilter(requested)
      setStoryId(requested)
      setScopeFilter('story')
    }
  }, [])

  useEffect(() => {
    if (!stories.length) return
    if (storyId === null || !stories.some((story) => story.id === storyId)) {
      setStoryId(stories[0].id)
    }
    if (storyFilter !== null && !stories.some((story) => story.id === storyFilter)) {
      setStoryFilter(null)
    }
  }, [stories, storyFilter, storyId])

  const libraryKey = ['play-media-library', currentWorkspace, scopeFilter, storyFilter] as const
  const libraryQuery = useQuery({
    queryKey: libraryKey,
    queryFn: () => getMediaLibrary(currentWorkspace ?? '', {
      scope: scopeFilter === 'all' ? undefined : scopeFilter,
      storyId: scopeFilter === 'story' && storyFilter !== null ? storyFilter : undefined,
    }),
    enabled: Boolean(currentWorkspace),
    retry: false,
  })

  const invalidateLibrary = () => Promise.all([
    queryClient.invalidateQueries({ queryKey: ['play-media-library'] }),
    queryClient.invalidateQueries({ queryKey: ['play-session-media-story-library'] }),
    queryClient.invalidateQueries({ queryKey: ['play-session-media-gallery'] }),
    queryClient.invalidateQueries({ queryKey: ['play-session-media-background'] }),
  ])

  const analyzeMutation = useMutation({
    mutationFn: (image: File) => {
      if (!currentWorkspace) throw new Error('请先选择 Workspace')
      return analyzeMediaLibraryImage(currentWorkspace, image)
    },
    onMutate: () => setAnalysisNotice(''),
    onSuccess: (metadata) => {
      setTitle(metadata.title)
      setDescription(metadata.description)
      setTagsText(metadata.tags.join('，'))
      setAnalysisNotice('智能识别完成，已覆盖标题、描述与 Tags；你可以继续修改。')
    },
  })

  const uploadMutation = useMutation({
    mutationFn: ({ image, manifest }: { image: File; manifest: MediaLibraryMetadataInput }) => {
      if (!currentWorkspace) throw new Error('请先选择 Workspace')
      return uploadMediaLibraryItem(currentWorkspace, image, manifest)
    },
    onSuccess: () => {
      setFile(null)
      setTitle('')
      setDescription('')
      setTagsText('')
      setIsDefault(false)
      setAnalysisNotice('')
      analyzeMutation.reset()
      if (fileInputRef.current) fileInputRef.current.value = ''
      setMessage('图片已导入媒体库')
      void invalidateLibrary()
    },
  })

  const updateMutation = useMutation({
    mutationFn: (item: MediaLibraryItem) => {
      if (!currentWorkspace) throw new Error('请先选择 Workspace')
      return updateMediaLibraryItem(currentWorkspace, item.itemId, {
        title: editTitle.trim(),
        description: editDescription.trim(),
        tags: parseTags(editTags),
        isDefault: item.scope === 'story' && editDefault,
      })
    },
    onSuccess: () => {
      setEditing(null)
      setMessage('素材信息已更新')
      void invalidateLibrary()
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (item: MediaLibraryItem) => {
      if (!currentWorkspace) throw new Error('请先选择 Workspace')
      return deleteMediaLibraryItem(currentWorkspace, item.itemId)
    },
    onSuccess: () => {
      setMessage('素材已删除')
      void invalidateLibrary()
    },
  })

  const reconcileMutation = useMutation({
    mutationFn: (workspaceId: string) => reconcileMediaLibrary(workspaceId),
    onMutate: () => setMessage(''),
    onSuccess: (result) => {
      setMessage(
        result.removedBlobs === 0
          ? '同步完成，未发现异常索引'
          : `同步完成：扫描 ${result.scannedBlobs} 个 Blob，清理 ${result.removedAssets} 个 Asset，清除 ${result.clearedBackgrounds} 个会话背景`,
      )
      void invalidateLibrary()
    },
  })

  const tags = parseTags(tagsText)
  const canUpload = Boolean(
    file
    && title.trim()
    && description.trim()
    && tags.length >= 1
    && tags.length <= 20
    && (scope === 'workspace_fallback' || storyId !== null),
  )

  function submitUpload() {
    if (!file || !canUpload) return
    uploadMutation.mutate({
      image: file,
      manifest: {
        scope,
        storyId: scope === 'story' ? storyId : null,
        title: title.trim(),
        description: description.trim(),
        tags,
        isDefault: scope === 'story' && isDefault,
      },
    })
  }

  function selectFile(nextFile: File | null) {
    setFile(nextFile)
    setAnalysisNotice('')
    analyzeMutation.reset()
  }

  function beginEdit(item: MediaLibraryItem) {
    setEditing(item)
    setEditTitle(item.title)
    setEditDescription(item.description)
    setEditTags(item.tags.join('，'))
    setEditDefault(item.isDefault)
  }

  const storyNames = new Map(stories.map((story) => [story.id, story.title]))
  const items = libraryQuery.data?.items ?? []
  const analysisUnsupported = analyzeMutation.error instanceof ApiError
    && analyzeMutation.error.errorCode === IMAGE_ANALYSIS_UNSUPPORTED

  return (
    <div className="min-w-0 px-5 py-8 xl:px-7">
      <header className="mb-6 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="mb-2 flex items-center gap-2 text-xs font-black uppercase tracking-[0.18em] text-violet-600">
            <Images size={15} /> rpg_media library
          </p>
          <h1 className="text-3xl font-black text-slate-950 dark:text-white">媒体库</h1>
          <p className="mt-2 max-w-3xl text-sm font-semibold leading-6 text-slate-500 dark:text-slate-300">
            统一管理会话生成与单张导入的环境背景。文件写入 Workspace 的 assets/images，数据库只保存 Blob 索引和素材语义。
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button type="button" onClick={() => void libraryQuery.refetch()} disabled={libraryQuery.isFetching || reconcileMutation.isPending} className="inline-flex h-10 w-fit items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 text-sm font-black text-slate-600 shadow-sm disabled:opacity-60 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200">
            <RefreshCcw size={15} className={libraryQuery.isFetching ? 'animate-spin' : ''} />刷新
          </button>
          <button
            type="button"
            title="扫描整个 Workspace，只清理源文件缺失的数据库索引；不会导入或删除未索引文件。"
            disabled={!currentWorkspace || reconcileMutation.isPending}
            onClick={() => currentWorkspace && reconcileMutation.mutate(currentWorkspace)}
            className="inline-flex h-10 w-fit items-center gap-2 rounded-lg bg-violet-600 px-4 text-sm font-black text-white shadow-sm disabled:opacity-60"
          >
            {reconcileMutation.isPending ? <Loader2 size={15} className="animate-spin" /> : <Database size={15} />}
            {reconcileMutation.isPending ? '同步中…' : '同步素材'}
          </button>
        </div>
      </header>

      {message ? <div className="mb-4 flex items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm font-bold text-emerald-700"><CheckCircle2 size={16} />{message}</div> : null}
      {reconcileMutation.isError ? <div className="mb-4 rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-bold text-rose-700">同步失败：{reconcileMutation.error instanceof Error ? reconcileMutation.error.message : 'Media Service 暂不可用'}</div> : null}

      <div className="grid gap-5 2xl:grid-cols-[390px_minmax(0,1fr)] 2xl:items-start">
        <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900 2xl:sticky 2xl:top-24">
          <div className="mb-5 flex items-center gap-3">
            <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-violet-100 text-violet-700"><ImagePlus size={20} /></span>
            <div><h2 className="font-black text-slate-950 dark:text-white">导入单张素材</h2><p className="text-xs font-semibold text-slate-400">PNG / JPEG / WebP · 最多 32 MiB</p></div>
          </div>
          <div className="grid gap-4">
            <label className="text-xs font-black text-slate-500">图片<input ref={fileInputRef} type="file" accept="image/png,image/jpeg,image/webp" onChange={(event) => selectFile(event.target.files?.[0] ?? null)} className="mt-2 block w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm font-semibold dark:border-slate-700 dark:bg-slate-950" /></label>
            <button type="button" onClick={() => file && analyzeMutation.mutate(file)} disabled={!currentWorkspace || !file || analyzeMutation.isPending || uploadMutation.isPending} className="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-violet-200 bg-violet-50 text-sm font-black text-violet-700 transition hover:bg-violet-100 disabled:border-slate-200 disabled:bg-slate-100 disabled:text-slate-400 dark:border-violet-700 dark:bg-violet-950/40 dark:text-violet-200 dark:disabled:border-slate-700 dark:disabled:bg-slate-800 dark:disabled:text-slate-500"><Sparkles size={15} />{analyzeMutation.isPending ? '识别中…' : '智能识别'}</button>
            {analysisNotice ? <p className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs font-bold leading-5 text-emerald-700 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-200">{analysisNotice}</p> : null}
            {analysisUnsupported ? <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-bold leading-5 text-amber-700 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-200">当前配置的 LLM 不支持图片识别，请手动填写标题、描述与 Tags 后继续导入。</p> : null}
            {analyzeMutation.isError && !analysisUnsupported ? <p className="text-xs font-bold text-rose-600">智能识别失败：{analyzeMutation.error instanceof Error ? analyzeMutation.error.message : 'Media Service 暂不可用'}</p> : null}
            <label className="text-xs font-black text-slate-500">作用域<select value={scope} onChange={(event) => { const value = event.target.value as MediaLibraryScope; setScope(value); if (value === 'workspace_fallback') setIsDefault(false) }} className="mt-2 h-11 w-full rounded-lg border border-slate-200 bg-slate-50 px-3 text-sm font-bold dark:border-slate-700 dark:bg-slate-950"><option value="story">Story 专属</option><option value="workspace_fallback">Workspace 通用兜底</option></select></label>
            {scope === 'story' ? <label className="text-xs font-black text-slate-500">Story<select value={storyId ?? ''} onChange={(event) => setStoryId(Number(event.target.value) || null)} className="mt-2 h-11 w-full rounded-lg border border-slate-200 bg-slate-50 px-3 text-sm font-bold dark:border-slate-700 dark:bg-slate-950"><option value="">选择 Story</option>{stories.map((story) => <option key={story.id} value={story.id}>{story.title}</option>)}</select></label> : null}
            <label className="text-xs font-black text-slate-500">标题<input value={title} onChange={(event) => setTitle(event.target.value)} maxLength={200} className="mt-2 h-11 w-full rounded-lg border border-slate-200 bg-slate-50 px-3 text-sm font-semibold dark:border-slate-700 dark:bg-slate-950" /></label>
            <label className="text-xs font-black text-slate-500">描述<textarea value={description} onChange={(event) => setDescription(event.target.value)} maxLength={4000} className="mt-2 min-h-24 w-full resize-y rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm font-semibold leading-6 dark:border-slate-700 dark:bg-slate-950" /></label>
            <label className="text-xs font-black text-slate-500">Tags（1–20 个，逗号或换行分隔）<textarea value={tagsText} onChange={(event) => setTagsText(event.target.value)} className="mt-2 min-h-20 w-full resize-y rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm font-semibold dark:border-slate-700 dark:bg-slate-950" /><span className="mt-1 block text-right text-[11px] text-slate-400">{tags.length} / 20</span></label>
            {scope === 'story' ? <label className="flex items-center gap-2 text-sm font-bold text-slate-600 dark:text-slate-200"><input type="checkbox" checked={isDefault} onChange={(event) => setIsDefault(event.target.checked)} className="h-4 w-4 accent-violet-600" />设为该 Story 默认背景</label> : null}
            <button type="button" onClick={submitUpload} disabled={!canUpload || uploadMutation.isPending} className="inline-flex h-11 items-center justify-center gap-2 rounded-lg bg-violet-600 text-sm font-black text-white shadow-lg shadow-violet-200 disabled:bg-slate-300 dark:shadow-violet-950/40"><Upload size={16} />{uploadMutation.isPending ? '导入中...' : '导入媒体库'}</button>
            {uploadMutation.isError ? <p className="text-xs font-bold text-rose-600">{uploadMutation.error instanceof Error ? uploadMutation.error.message : '导入失败'}</p> : null}
          </div>
        </section>

        <section className="min-w-0 rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
          <div className="mb-5 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div><h2 className="font-black text-slate-950 dark:text-white">全部图片资产</h2><p className="mt-1 text-xs font-semibold text-slate-400">{items.length} 项 · Workspace {currentWorkspace ?? '未选择'}</p></div>
            <div className="flex flex-wrap gap-2">
              <select value={scopeFilter} onChange={(event) => { const value = event.target.value as ScopeFilter; setScopeFilter(value); if (value !== 'story') setStoryFilter(null) }} className="h-9 rounded-lg border border-slate-200 bg-white px-3 text-xs font-black dark:border-slate-700 dark:bg-slate-950"><option value="all">全部作用域</option><option value="story">Story 专属</option><option value="workspace_fallback">Workspace 兜底</option></select>
              {scopeFilter === 'story' ? <select value={storyFilter ?? ''} onChange={(event) => setStoryFilter(Number(event.target.value) || null)} className="h-9 rounded-lg border border-slate-200 bg-white px-3 text-xs font-black dark:border-slate-700 dark:bg-slate-950"><option value="">全部 Story</option>{stories.map((story) => <option key={story.id} value={story.id}>{story.title}</option>)}</select> : null}
            </div>
          </div>
          {libraryQuery.isError ? <p className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-4 text-sm font-bold text-rose-700">Media Service 暂不可用：{libraryQuery.error instanceof Error ? libraryQuery.error.message : '加载失败'}</p> : null}
          {libraryQuery.isLoading ? <div className="flex min-h-52 items-center justify-center text-slate-400"><Loader2 className="animate-spin" /></div> : null}
          {!libraryQuery.isLoading && !libraryQuery.isError && !items.length ? <div className="flex min-h-52 flex-col items-center justify-center rounded-lg border border-dashed border-slate-200 text-center text-sm font-bold text-slate-400"><Images size={32} className="mb-3" />当前筛选下还没有素材</div> : null}
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {items.map((item) => <article key={item.itemId} className="overflow-hidden rounded-xl border border-slate-200 bg-slate-50 dark:border-slate-700 dark:bg-slate-950"><MediaImageFrame src={mediaLibraryContentUrl(item.workspaceId, item.itemId)} alt={item.title} className="aspect-video">{item.isDefault ? <span className="absolute left-2 top-2 rounded-full bg-violet-600 px-2 py-1 text-[10px] font-black text-white">Story 默认</span> : null}<span className="absolute right-2 top-2 rounded-full bg-slate-950/75 px-2 py-1 text-[10px] font-black text-white">{item.origin === 'generated' ? '会话生成' : '离线导入'}</span></MediaImageFrame><div className="p-4"><div className="flex items-start justify-between gap-2"><div className="min-w-0"><h3 className="truncate text-sm font-black text-slate-950 dark:text-white">{item.title}</h3><p className="mt-1 text-[11px] font-bold text-slate-400">{item.scope === 'story' ? storyNames.get(item.storyId ?? -1) ?? `Story #${item.storyId}` : 'Workspace 通用兜底'} · {formatBytes(item.byteSize)}</p></div></div><p className="mt-3 line-clamp-3 min-h-[3.75rem] text-xs font-semibold leading-5 text-slate-500 dark:text-slate-300">{item.description}</p><div className="mt-3 flex flex-wrap gap-1">{item.tags.map((tag) => <span key={tag} className="rounded-full bg-white px-2 py-1 text-[10px] font-bold text-slate-500 dark:bg-slate-800 dark:text-slate-300">{tag}</span>)}</div><div className="mt-4 flex gap-2"><button type="button" onClick={() => beginEdit(item)} className="inline-flex h-8 flex-1 items-center justify-center gap-1 rounded-lg border border-slate-200 bg-white text-xs font-black text-slate-600 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"><Pencil size={12} />编辑</button><button type="button" disabled={deleteMutation.isPending} onClick={() => { const suffix = item.origin === 'generated' ? '这也会将它从原 Session 的图片素材中移除。' : ''; if (window.confirm(`删除素材“${item.title}”？${suffix}`)) deleteMutation.mutate(item) }} className="inline-flex h-8 items-center justify-center gap-1 rounded-lg border border-rose-200 bg-white px-3 text-xs font-black text-rose-600 disabled:opacity-50 dark:bg-slate-900"><Trash2 size={12} />删除</button></div></div></article>)}
          </div>
          {deleteMutation.isError ? <p className="mt-4 text-xs font-bold text-rose-600">{deleteMutation.error instanceof Error ? deleteMutation.error.message : '删除失败'}</p> : null}
        </section>
      </div>

      {editing ? <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/55 p-4"><section className="w-full max-w-xl rounded-xl border border-slate-200 bg-white p-6 shadow-2xl dark:border-slate-700 dark:bg-slate-900"><h2 className="text-lg font-black text-slate-950 dark:text-white">编辑素材信息</h2><div className="mt-5 grid gap-4"><label className="text-xs font-black text-slate-500">标题<input value={editTitle} onChange={(event) => setEditTitle(event.target.value)} className="mt-2 h-11 w-full rounded-lg border border-slate-200 bg-slate-50 px-3 text-sm font-semibold dark:border-slate-700 dark:bg-slate-950" /></label><label className="text-xs font-black text-slate-500">描述<textarea value={editDescription} onChange={(event) => setEditDescription(event.target.value)} className="mt-2 min-h-28 w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm font-semibold dark:border-slate-700 dark:bg-slate-950" /></label><label className="text-xs font-black text-slate-500">Tags<textarea value={editTags} onChange={(event) => setEditTags(event.target.value)} className="mt-2 min-h-20 w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm font-semibold dark:border-slate-700 dark:bg-slate-950" /></label>{editing.scope === 'story' ? <label className="flex items-center gap-2 text-sm font-bold text-slate-600"><input type="checkbox" checked={editDefault} onChange={(event) => setEditDefault(event.target.checked)} />Story 默认背景</label> : null}</div>{updateMutation.isError ? <p className="mt-3 text-xs font-bold text-rose-600">{updateMutation.error instanceof Error ? updateMutation.error.message : '更新失败'}</p> : null}<div className="mt-6 flex justify-end gap-2"><button type="button" onClick={() => setEditing(null)} className="h-10 rounded-lg border border-slate-200 px-4 text-sm font-black text-slate-600">取消</button><button type="button" disabled={!editTitle.trim() || !editDescription.trim() || !parseTags(editTags).length || updateMutation.isPending} onClick={() => updateMutation.mutate(editing)} className="h-10 rounded-lg bg-violet-600 px-4 text-sm font-black text-white disabled:bg-slate-300">保存</button></div></section></div> : null}
    </div>
  )
}

export function MediaLibraryPage() {
  return <AppShell><MediaLibraryContent /></AppShell>
}
