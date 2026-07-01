'use client'

import { Check, Loader2, Plus } from 'lucide-react'
import { Dialog } from './Dialog'

type MountableStory = {
  id: number
  title: string
  summary?: string | null
}

export function StoryMountDialog<TStory extends MountableStory>({
  title = '添加故事挂载',
  description,
  stories,
  mountedStoryIds,
  pending,
  disabled,
  emptyText = '暂无故事',
  footerNote,
  onClose,
  onMount,
}: {
  title?: string
  description: string
  stories: TStory[]
  mountedStoryIds: ReadonlySet<number>
  pending: boolean
  disabled?: boolean
  emptyText?: string
  footerNote: string
  onClose: () => void
  onMount: (storyId: number) => void
}) {
  return (
    <Dialog title={title} onClose={onClose}>
      <div className="border-b border-slate-200 bg-slate-50/70 px-6 py-4">
        <p className="text-sm text-slate-500">{description}</p>
      </div>
      <div className="max-h-[520px] overflow-y-auto px-5 py-5">
        <div className="rounded-2xl border border-slate-200 bg-white">
          {stories.length ? stories.map((story) => {
            const alreadyMountedInStory = mountedStoryIds.has(story.id)
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
                  onClick={() => onMount(story.id)}
                  disabled={disabled || alreadyMountedInStory || pending}
                  className="flex h-10 items-center justify-center gap-2 rounded-lg bg-violet-600 px-4 text-sm font-semibold text-white shadow-lg shadow-violet-100 transition hover:bg-violet-700 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-500 disabled:shadow-none"
                >
                  {pending ? <Loader2 size={16} className="animate-spin" /> : alreadyMountedInStory ? <Check size={16} /> : <Plus size={16} />}
                  {alreadyMountedInStory ? '已添加' : '添加'}
                </button>
              </article>
            )
          }) : (
            <div className="px-4 py-10 text-center text-sm text-slate-500">{emptyText}</div>
          )}
        </div>
      </div>
      <footer className="flex items-center justify-between border-t border-slate-200 bg-slate-50 px-6 py-4 text-xs text-slate-500">
        <span>{footerNote}</span>
        <button
          type="button"
          onClick={onClose}
          className="h-9 rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700 transition hover:border-violet-200 hover:text-violet-700"
        >
          完成
        </button>
      </footer>
    </Dialog>
  )
}
