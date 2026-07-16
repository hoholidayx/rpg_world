import { Search, SlidersHorizontal, X } from 'lucide-react'
import type {
  MediaLibraryFacets,
  MediaLibraryOrigin,
  MediaLibraryScope,
  MediaLibrarySort,
  MediaLibraryType,
} from '@/types/media'
import type { StorySummary } from '@/types/story'
import { MEDIA_LIBRARY_TYPES } from '@/types/media'
import { MEDIA_TYPE_LABELS } from './constants'

export function MediaLibraryFilters({
  search,
  onSearchChange,
  mediaType,
  onMediaTypeChange,
  scope,
  onScopeChange,
  storyId,
  onStoryIdChange,
  origin,
  onOriginChange,
  sort,
  onSortChange,
  selectedTags,
  onAddTag,
  onRemoveTag,
  onClear,
  stories,
  facets,
}: {
  search: string
  onSearchChange: (value: string) => void
  mediaType: MediaLibraryType | 'all'
  onMediaTypeChange: (value: MediaLibraryType | 'all') => void
  scope: MediaLibraryScope | 'all'
  onScopeChange: (value: MediaLibraryScope | 'all') => void
  storyId: number | null
  onStoryIdChange: (value: number | null) => void
  origin: MediaLibraryOrigin | 'all'
  onOriginChange: (value: MediaLibraryOrigin | 'all') => void
  sort: MediaLibrarySort
  onSortChange: (value: MediaLibrarySort) => void
  selectedTags: string[]
  onAddTag: (value: string) => void
  onRemoveTag: (value: string) => void
  onClear: () => void
  stories: StorySummary[]
  facets?: MediaLibraryFacets
}) {
  const hasFilters = Boolean(
    search || mediaType !== 'all' || scope !== 'all' || storyId !== null
    || origin !== 'all' || selectedTags.length,
  )
  const availableTags = (facets?.tags ?? []).filter(
    (facet) => !selectedTags.some((tag) => tag.toLocaleLowerCase() === facet.value.toLocaleLowerCase()),
  )

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div className="flex items-center gap-2 text-xs font-black uppercase tracking-[0.16em] text-slate-400">
        <SlidersHorizontal size={14} /> 资源筛选
      </div>
      <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-[minmax(260px,1.5fr)_repeat(4,minmax(130px,0.7fr))]">
        <label className="relative block">
          <Search size={16} className="pointer-events-none absolute left-3 top-3 text-slate-400" />
          <input
            value={search}
            onChange={(event) => onSearchChange(event.target.value)}
            placeholder="搜索标题、描述或 Tags"
            className="h-10 w-full rounded-xl border border-slate-200 bg-slate-50 pl-9 pr-3 text-sm font-semibold outline-none transition focus:border-violet-300 focus:ring-4 focus:ring-violet-100 dark:border-slate-700 dark:bg-slate-950 dark:focus:ring-violet-950"
          />
        </label>
        <select value={mediaType} onChange={(event) => onMediaTypeChange(event.target.value as MediaLibraryType | 'all')} className="h-10 rounded-xl border border-slate-200 bg-white px-3 text-xs font-black dark:border-slate-700 dark:bg-slate-950">
          <option value="all">全部用途</option>
          {MEDIA_LIBRARY_TYPES.map((value) => (
            <option key={value} value={value}>{MEDIA_TYPE_LABELS[value]}{facetCount(facets?.mediaTypes, value)}</option>
          ))}
        </select>
        <select value={scope} onChange={(event) => onScopeChange(event.target.value as MediaLibraryScope | 'all')} className="h-10 rounded-xl border border-slate-200 bg-white px-3 text-xs font-black dark:border-slate-700 dark:bg-slate-950">
          <option value="all">全部作用域</option>
          <option value="story">Story 专属{facetCount(facets?.scopes, 'story')}</option>
          <option value="workspace">Workspace 通用{facetCount(facets?.scopes, 'workspace')}</option>
        </select>
        <select value={origin} onChange={(event) => onOriginChange(event.target.value as MediaLibraryOrigin | 'all')} className="h-10 rounded-xl border border-slate-200 bg-white px-3 text-xs font-black dark:border-slate-700 dark:bg-slate-950">
          <option value="all">全部来源</option>
          <option value="upload">离线导入{facetCount(facets?.origins, 'upload')}</option>
          <option value="generated">会话生成{facetCount(facets?.origins, 'generated')}</option>
        </select>
        <select value={sort} onChange={(event) => onSortChange(event.target.value as MediaLibrarySort)} className="h-10 rounded-xl border border-slate-200 bg-white px-3 text-xs font-black dark:border-slate-700 dark:bg-slate-950">
          <option value="updated_desc">最近更新</option>
          <option value="created_desc">最近创建</option>
          <option value="title_asc">标题 A–Z</option>
          <option value="size_desc">文件大小</option>
        </select>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <select
          value=""
          onChange={(event) => { if (event.target.value) onAddTag(event.target.value) }}
          className="h-9 rounded-lg border border-slate-200 bg-white px-3 text-xs font-bold text-slate-600 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-300"
        >
          <option value="">按 Tag 筛选…</option>
          {availableTags.map((tag) => <option key={tag.value} value={tag.value}>{tag.value}（{tag.count}）</option>)}
        </select>
        {selectedTags.map((tag) => (
          <button key={tag} type="button" onClick={() => onRemoveTag(tag)} className="inline-flex h-8 items-center gap-1 rounded-full bg-violet-100 px-3 text-xs font-black text-violet-700 dark:bg-violet-500/15 dark:text-violet-200">
            #{tag}<X size={12} />
          </button>
        ))}
        <select value={storyId ?? ''} onChange={(event) => onStoryIdChange(Number(event.target.value) || null)} disabled={scope === 'workspace'} className="h-9 rounded-lg border border-slate-200 bg-white px-3 text-xs font-bold disabled:opacity-40 dark:border-slate-700 dark:bg-slate-950">
          <option value="">全部 Story</option>
          {stories.map((story) => <option key={story.id} value={story.id}>{story.title}</option>)}
        </select>
        {hasFilters ? <button type="button" onClick={onClear} className="ml-auto h-8 rounded-lg px-3 text-xs font-black text-slate-500 transition hover:bg-slate-100 hover:text-slate-800 dark:hover:bg-slate-800 dark:hover:text-white">清除筛选</button> : null}
      </div>
    </section>
  )
}

function facetCount(values: Array<{ value: string; count: number }> | undefined, value: string) {
  const count = values?.find((item) => item.value === value)?.count
  return count === undefined ? '' : `（${count}）`
}
