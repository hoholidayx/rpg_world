import { ChevronLeft, ChevronRight, Images, Link2, Loader2 } from 'lucide-react'
import { MediaImageFrame } from '@/components/common/MediaImageFrame'
import { mediaLibraryContentUrl } from '@/lib/api/media'
import type { MediaLibraryItem } from '@/types/media'
import { formatBytes, MEDIA_TYPE_LABELS } from './constants'

export function MediaLibraryGrid({
  items,
  total,
  page,
  pageSize,
  loading,
  error,
  selectedIds,
  onToggle,
  onOpen,
  onPageChange,
}: {
  items: MediaLibraryItem[]
  total: number
  page: number
  pageSize: number
  loading: boolean
  error: string | null
  selectedIds: Set<string>
  onToggle: (item: MediaLibraryItem) => void
  onOpen: (item: MediaLibraryItem) => void
  onPageChange: (page: number) => void
}) {
  const pageCount = Math.max(1, Math.ceil(total / pageSize))
  return (
    <section className="min-w-0 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div className="mb-5 flex items-center justify-between gap-3">
        <div>
          <h2 className="font-black text-slate-950 dark:text-white">图片资产</h2>
          <p className="mt-1 text-xs font-semibold text-slate-400">共 {total} 项 · 第 {page} / {pageCount} 页</p>
        </div>
      </div>
      {error ? <p className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-4 text-sm font-bold text-rose-700 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-200">Media Service 暂不可用：{error}</p> : null}
      {loading ? <div className="flex min-h-72 items-center justify-center text-slate-400"><Loader2 className="animate-spin" /></div> : null}
      {!loading && !error && !items.length ? (
        <div className="flex min-h-72 flex-col items-center justify-center rounded-xl border border-dashed border-slate-200 text-center text-sm font-bold text-slate-400 dark:border-slate-700">
          <Images size={34} className="mb-3" />当前筛选下还没有素材
        </div>
      ) : null}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
        {items.map((item) => {
          const selected = selectedIds.has(item.itemId)
          const references = item.backgroundReferences + item.galleryReferences
          return (
            <article
              key={item.itemId}
              role="button"
              tabIndex={0}
              onClick={() => onOpen(item)}
              onKeyDown={(event) => { if (event.key === 'Enter') onOpen(item) }}
              className={`group cursor-pointer overflow-hidden rounded-xl border bg-slate-50 text-left transition hover:-translate-y-0.5 hover:shadow-lg dark:bg-slate-950 ${selected ? 'border-violet-500 ring-2 ring-violet-200 dark:ring-violet-500/30' : 'border-slate-200 dark:border-slate-700'}`}
            >
              <MediaImageFrame src={mediaLibraryContentUrl(item.workspaceId, item.itemId)} alt={item.title} className="aspect-video">
                <label className="absolute left-2 top-2 z-10 flex h-7 w-7 cursor-pointer items-center justify-center rounded-lg bg-slate-950/75 text-white backdrop-blur">
                  <input
                    type="checkbox"
                    checked={selected}
                    onClick={(event) => event.stopPropagation()}
                    onChange={() => onToggle(item)}
                    className="h-4 w-4 accent-violet-600"
                    aria-label={`选择 ${item.title}`}
                  />
                </label>
                <span className="absolute right-2 top-2 rounded-full bg-slate-950/75 px-2 py-1 text-[10px] font-black text-white backdrop-blur">{MEDIA_TYPE_LABELS[item.mediaType]}</span>
                {item.isDefault ? <span className="absolute bottom-2 left-2 rounded-full bg-violet-600 px-2 py-1 text-[10px] font-black text-white">Story 默认背景</span> : null}
              </MediaImageFrame>
              <div className="p-4">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <h3 className="truncate text-sm font-black text-slate-950 dark:text-white">{item.title}</h3>
                    <p className="mt-1 text-[11px] font-bold text-slate-400">{item.scope === 'story' ? `Story #${item.storyId}` : 'Workspace 通用'} · {formatBytes(item.byteSize)}</p>
                  </div>
                  {references ? <span title={`${references} 个使用关联`} className="inline-flex shrink-0 items-center gap-1 rounded-full bg-amber-50 px-2 py-1 text-[10px] font-black text-amber-700 dark:bg-amber-500/10 dark:text-amber-200"><Link2 size={10} />{references}</span> : null}
                </div>
                <p className="mt-3 line-clamp-2 min-h-10 text-xs font-semibold leading-5 text-slate-500 dark:text-slate-300">{item.description}</p>
                <div className="mt-3 flex min-h-6 flex-wrap gap-1">
                  {item.tags.slice(0, 4).map((tag) => <span key={tag} className="rounded-full bg-white px-2 py-1 text-[10px] font-bold text-slate-500 dark:bg-slate-800 dark:text-slate-300">#{tag}</span>)}
                  {item.tags.length > 4 ? <span className="px-1 py-1 text-[10px] font-black text-slate-400">+{item.tags.length - 4}</span> : null}
                </div>
              </div>
            </article>
          )
        })}
      </div>
      {!loading && !error && total > pageSize ? (
        <footer className="mt-6 flex items-center justify-center gap-3 border-t border-slate-100 pt-5 dark:border-slate-800">
          <button type="button" disabled={page <= 1} onClick={() => onPageChange(page - 1)} className="inline-flex h-9 items-center gap-1 rounded-lg border border-slate-200 px-3 text-xs font-black text-slate-600 disabled:opacity-40 dark:border-slate-700 dark:text-slate-200"><ChevronLeft size={14} />上一页</button>
          <span className="text-xs font-black text-slate-400">{page} / {pageCount}</span>
          <button type="button" disabled={page >= pageCount} onClick={() => onPageChange(page + 1)} className="inline-flex h-9 items-center gap-1 rounded-lg border border-slate-200 px-3 text-xs font-black text-slate-600 disabled:opacity-40 dark:border-slate-700 dark:text-slate-200">下一页<ChevronRight size={14} /></button>
        </footer>
      ) : null}
    </section>
  )
}
