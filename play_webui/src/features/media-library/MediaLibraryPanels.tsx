'use client'

import { useEffect, useRef, useState } from 'react'
import { ImagePlus, Link2, Loader2, Sparkles, Trash2, Upload, X } from 'lucide-react'
import { Dialog } from '@/components/common/Dialog'
import { MediaImageFrame } from '@/components/common/MediaImageFrame'
import { mediaLibraryContentUrl } from '@/lib/api/media'
import type { MediaLibraryItem, MediaLibraryMetadataInput, MediaLibraryScope, MediaLibraryType } from '@/types/media'
import { MEDIA_LIBRARY_TYPES } from '@/types/media'
import type { StorySummary } from '@/types/story'
import { formatBytes, formatMediaDate, MEDIA_TYPE_LABELS, parseTags } from './constants'

const fieldClass = 'mt-2 h-11 w-full rounded-xl border border-slate-200 bg-slate-50 px-3 text-sm font-semibold outline-none transition focus:border-violet-300 focus:ring-4 focus:ring-violet-100 dark:border-slate-700 dark:bg-slate-950 dark:focus:ring-violet-950'
const labelClass = 'text-xs font-black text-slate-500 dark:text-slate-300'

export function MediaImportDialog({
  open,
  stories,
  onClose,
  onAnalyze,
  onUpload,
}: {
  open: boolean
  stories: StorySummary[]
  onClose: () => void
  onAnalyze: (file: File) => Promise<{ title: string; description: string; tags: string[] }>
  onUpload: (file: File, input: MediaLibraryMetadataInput) => Promise<void>
}) {
  const inputRef = useRef<HTMLInputElement | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [mediaType, setMediaType] = useState<MediaLibraryType>('other')
  const [scope, setScope] = useState<MediaLibraryScope>('story')
  const [storyId, setStoryId] = useState<number | null>(null)
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [tagsText, setTagsText] = useState('')
  const [isDefault, setIsDefault] = useState(false)
  const [analyzing, setAnalyzing] = useState(false)
  const [saving, setSaving] = useState(false)
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')
  const [previewUrl, setPreviewUrl] = useState('')

  useEffect(() => {
    if (!open) return
    setStoryId((current) => current && stories.some((story) => story.id === current) ? current : stories[0]?.id ?? null)
  }, [open, stories])

  useEffect(() => {
    if (!file) {
      setPreviewUrl('')
      return undefined
    }
    const url = URL.createObjectURL(file)
    setPreviewUrl(url)
    return () => URL.revokeObjectURL(url)
  }, [file])

  if (!open) return null
  const tags = parseTags(tagsText)
  const canSave = Boolean(
    file && title.trim() && description.trim() && tags.length >= 1 && tags.length <= 20
    && (scope === 'workspace' || storyId !== null),
  )

  async function analyze() {
    if (!file) return
    setAnalyzing(true)
    setError('')
    setNotice('')
    try {
      const metadata = await onAnalyze(file)
      setTitle(metadata.title)
      setDescription(metadata.description)
      setTagsText(metadata.tags.join('，'))
      setNotice('智能识别完成，标题、描述与 Tags 仍可继续修改。')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '智能识别失败')
    } finally {
      setAnalyzing(false)
    }
  }

  async function save() {
    if (!file || !canSave) return
    setSaving(true)
    setError('')
    try {
      await onUpload(file, {
        mediaType,
        scope,
        storyId: scope === 'story' ? storyId : null,
        title: title.trim(),
        description: description.trim(),
        tags,
        isDefault: scope === 'story' && mediaType === 'background' && isDefault,
      })
      setFile(null)
      setMediaType('other')
      setTitle('')
      setDescription('')
      setTagsText('')
      setIsDefault(false)
      setNotice('')
      if (inputRef.current) inputRef.current.value = ''
      onClose()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '导入失败')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog title="导入单张图片" onClose={onClose} closeDisabled={saving} size="3xl" className="max-h-[90vh] overflow-y-auto dark:border-slate-700 dark:bg-slate-900" overlayClassName="z-[70]">
      <div className="grid gap-5 p-6 md:grid-cols-2">
        <div className="space-y-4">
          <label className={labelClass}>图片<input ref={inputRef} type="file" accept="image/png,image/jpeg,image/webp" onChange={(event) => { setFile(event.target.files?.[0] ?? null); setNotice(''); setError('') }} className={`${fieldClass} block py-2`} /></label>
          {file && previewUrl ? <div className="overflow-hidden rounded-xl border border-slate-200 dark:border-slate-700"><MediaImageFrame src={previewUrl} alt={file.name} className="aspect-video" /><p className="truncate px-3 py-2 text-xs font-bold text-slate-500">{file.name} · {formatBytes(file.size)}</p></div> : <div className="flex aspect-video items-center justify-center rounded-xl border border-dashed border-slate-200 text-sm font-bold text-slate-400 dark:border-slate-700"><ImagePlus className="mr-2" />PNG / JPEG / WebP · 最多 32 MiB</div>}
          <button type="button" onClick={() => void analyze()} disabled={!file || analyzing || saving} className="inline-flex h-10 w-full items-center justify-center gap-2 rounded-xl border border-violet-200 bg-violet-50 text-sm font-black text-violet-700 disabled:opacity-50 dark:border-violet-500/30 dark:bg-violet-500/10 dark:text-violet-200"><Sparkles size={15} />{analyzing ? '识别中…' : '智能识别元数据'}</button>
          {notice ? <p className="rounded-lg bg-emerald-50 px-3 py-2 text-xs font-bold text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-200">{notice}</p> : null}
        </div>
        <div className="grid content-start gap-4">
          <label className={labelClass}>用途类型<select value={mediaType} onChange={(event) => { const value = event.target.value as MediaLibraryType; setMediaType(value); if (value !== 'background') setIsDefault(false) }} className={fieldClass}>{MEDIA_LIBRARY_TYPES.map((value) => <option key={value} value={value}>{MEDIA_TYPE_LABELS[value]}</option>)}</select></label>
          <label className={labelClass}>作用域<select value={scope} onChange={(event) => { const value = event.target.value as MediaLibraryScope; setScope(value); if (value === 'workspace') setIsDefault(false) }} className={fieldClass}><option value="story">Story 专属</option><option value="workspace">Workspace 通用</option></select></label>
          {scope === 'story' ? <label className={labelClass}>Story<select value={storyId ?? ''} onChange={(event) => setStoryId(Number(event.target.value) || null)} className={fieldClass}><option value="">选择 Story</option>{stories.map((story) => <option key={story.id} value={story.id}>{story.title}</option>)}</select></label> : null}
          <label className={labelClass}>标题<input value={title} onChange={(event) => setTitle(event.target.value)} maxLength={200} className={fieldClass} /></label>
          <label className={labelClass}>描述<textarea value={description} onChange={(event) => setDescription(event.target.value)} maxLength={4000} className={`${fieldClass} min-h-28 resize-y py-2`} /></label>
          <label className={labelClass}>Tags（1–20 个）<textarea value={tagsText} onChange={(event) => setTagsText(event.target.value)} className={`${fieldClass} min-h-20 resize-y py-2`} /><span className="mt-1 block text-right text-[11px] text-slate-400">{tags.length} / 20</span></label>
          {scope === 'story' && mediaType === 'background' ? <label className="flex items-center gap-2 text-sm font-bold text-slate-600 dark:text-slate-200"><input type="checkbox" checked={isDefault} onChange={(event) => setIsDefault(event.target.checked)} className="h-4 w-4 accent-violet-600" />设为 Story 默认背景</label> : null}
        </div>
      </div>
      {error ? <p className="mx-6 mb-4 rounded-lg bg-rose-50 px-3 py-2 text-xs font-bold text-rose-700 dark:bg-rose-500/10 dark:text-rose-200">{error}</p> : null}
      <footer className="flex justify-end gap-2 border-t border-slate-200 bg-slate-50 px-6 py-4 dark:border-slate-700 dark:bg-slate-950/60">
        <button type="button" onClick={onClose} disabled={saving} className="h-10 rounded-lg border border-slate-200 bg-white px-4 text-sm font-black text-slate-600 disabled:opacity-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200">取消</button>
        <button type="button" onClick={() => void save()} disabled={!canSave || saving} className="inline-flex h-10 items-center gap-2 rounded-lg bg-violet-600 px-4 text-sm font-black text-white disabled:bg-slate-300 dark:disabled:bg-slate-700">{saving ? <Loader2 size={15} className="animate-spin" /> : <Upload size={15} />}{saving ? '导入中…' : '导入媒体库'}</button>
      </footer>
    </Dialog>
  )
}

export function MediaDetailDrawer({
  item,
  stories,
  onClose,
  onSave,
  onDelete,
}: {
  item: MediaLibraryItem | null
  stories: StorySummary[]
  onClose: () => void
  onSave: (item: MediaLibraryItem, input: MediaLibraryMetadataInput) => Promise<void>
  onDelete: (item: MediaLibraryItem) => void
}) {
  const [scope, setScope] = useState<MediaLibraryScope>('workspace')
  const [storyId, setStoryId] = useState<number | null>(null)
  const [mediaType, setMediaType] = useState<MediaLibraryType>('other')
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [tagsText, setTagsText] = useState('')
  const [isDefault, setIsDefault] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!item) return
    setScope(item.scope)
    setStoryId(item.storyId)
    setMediaType(item.mediaType)
    setTitle(item.title)
    setDescription(item.description)
    setTagsText(item.tags.join('，'))
    setIsDefault(item.isDefault)
    setError('')
  }, [item])

  if (!item) return null
  const tags = parseTags(tagsText)
  const references = item.backgroundReferences + item.galleryReferences

  async function save() {
    if (!item) return
    setSaving(true)
    setError('')
    try {
      await onSave(item, {
        scope,
        storyId: scope === 'story' ? storyId : null,
        mediaType,
        title: title.trim(),
        description: description.trim(),
        tags,
        isDefault: scope === 'story' && mediaType === 'background' && isDefault,
      })
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '保存失败')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-[65] bg-slate-950/35 backdrop-blur-sm" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}>
      <aside className="ml-auto flex h-full w-full max-w-2xl flex-col overflow-hidden border-l border-slate-200 bg-white shadow-2xl dark:border-slate-700 dark:bg-slate-900">
        <header className="flex items-center justify-between border-b border-slate-200 px-5 py-4 dark:border-slate-700"><div><p className="text-xs font-black uppercase tracking-[0.15em] text-violet-600">资源详情</p><h2 className="mt-1 truncate text-xl font-black text-slate-950 dark:text-white">{item.title}</h2></div><button type="button" onClick={onClose} disabled={saving} className="flex h-9 w-9 items-center justify-center rounded-lg text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800"><X size={18} /></button></header>
        <div className="min-h-0 flex-1 overflow-y-auto p-5">
          <MediaImageFrame src={mediaLibraryContentUrl(item.workspaceId, item.itemId)} alt={item.title} className="aspect-video rounded-xl" loading="eager" />
          <div className="mt-4 grid grid-cols-2 gap-3 rounded-xl bg-slate-50 p-4 text-xs font-bold text-slate-500 dark:bg-slate-950 dark:text-slate-300">
            <span>来源：{item.origin === 'generated' ? '会话生成' : '离线导入'}</span><span>大小：{formatBytes(item.byteSize)}</span>
            <span>创建：{formatMediaDate(item.createdAt)}</span><span>更新：{formatMediaDate(item.updatedAt)}</span>
            <span className="col-span-2 inline-flex items-center gap-1"><Link2 size={13} />背景引用 {item.backgroundReferences} · Gallery 关联 {item.galleryReferences}</span>
          </div>
          <div className="mt-5 grid gap-4 sm:grid-cols-2">
            <label className={labelClass}>用途类型<select value={mediaType} onChange={(event) => { const value = event.target.value as MediaLibraryType; setMediaType(value); if (value !== 'background') setIsDefault(false) }} className={fieldClass}>{MEDIA_LIBRARY_TYPES.map((value) => <option key={value} value={value}>{MEDIA_TYPE_LABELS[value]}</option>)}</select></label>
            <label className={labelClass}>作用域<select value={scope} onChange={(event) => { const value = event.target.value as MediaLibraryScope; setScope(value); if (value === 'workspace') setIsDefault(false) }} className={fieldClass}><option value="story">Story 专属</option><option value="workspace">Workspace 通用</option></select></label>
            {scope === 'story' ? <label className={`${labelClass} sm:col-span-2`}>Story<select value={storyId ?? ''} onChange={(event) => setStoryId(Number(event.target.value) || null)} className={fieldClass}><option value="">选择 Story</option>{stories.map((story) => <option key={story.id} value={story.id}>{story.title}</option>)}</select></label> : null}
            <label className={`${labelClass} sm:col-span-2`}>标题<input value={title} onChange={(event) => setTitle(event.target.value)} maxLength={200} className={fieldClass} /></label>
            <label className={`${labelClass} sm:col-span-2`}>描述<textarea value={description} onChange={(event) => setDescription(event.target.value)} maxLength={4000} className={`${fieldClass} min-h-28 resize-y py-2`} /></label>
            <label className={`${labelClass} sm:col-span-2`}>Tags<textarea value={tagsText} onChange={(event) => setTagsText(event.target.value)} className={`${fieldClass} min-h-20 resize-y py-2`} /></label>
            {scope === 'story' && mediaType === 'background' ? <label className="flex items-center gap-2 text-sm font-bold text-slate-600 dark:text-slate-200"><input type="checkbox" checked={isDefault} onChange={(event) => setIsDefault(event.target.checked)} className="h-4 w-4 accent-violet-600" />Story 默认背景</label> : null}
          </div>
          {error ? <p className="mt-4 rounded-lg bg-rose-50 px-3 py-2 text-xs font-bold text-rose-700 dark:bg-rose-500/10 dark:text-rose-200">{error}</p> : null}
        </div>
        <footer className="flex items-center justify-between border-t border-slate-200 bg-slate-50 px-5 py-4 dark:border-slate-700 dark:bg-slate-950/60">
          <button type="button" onClick={() => onDelete(item)} disabled={saving} className="inline-flex h-10 items-center gap-2 rounded-lg border border-rose-200 bg-white px-4 text-sm font-black text-rose-600 disabled:opacity-50 dark:bg-slate-900"><Trash2 size={15} />删除</button>
          <button type="button" onClick={() => void save()} disabled={saving || !title.trim() || !description.trim() || !tags.length || (scope === 'story' && storyId === null)} className="inline-flex h-10 items-center gap-2 rounded-lg bg-violet-600 px-5 text-sm font-black text-white disabled:bg-slate-300 dark:disabled:bg-slate-700">{saving ? <Loader2 size={15} className="animate-spin" /> : null}{saving ? '保存中…' : '保存修改'}</button>
        </footer>
      </aside>
    </div>
  )
}
