'use client'

import { useEffect, useId } from 'react'
import { GitBranch, Loader2, X } from 'lucide-react'

export function SessionDerivationDialog({
  open,
  sourceSessionId,
  sourceTitle,
  turnId,
  title,
  pending,
  error,
  onTitleChange,
  onClose,
  onSubmit,
}: {
  open: boolean
  sourceSessionId: string
  sourceTitle: string
  turnId: number | null
  title: string
  pending: boolean
  error: string | null
  onTitleChange: (value: string) => void
  onClose: () => void
  onSubmit: () => void
}) {
  const titleId = useId()

  useEffect(() => {
    if (!open || pending) return
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [onClose, open, pending])

  if (!open || turnId === null) return null

  const sourceLabel = sourceTitle.trim() || sourceSessionId

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center px-4 py-8">
      <button
        type="button"
        onClick={onClose}
        disabled={pending}
        className="absolute inset-0 bg-slate-950/30 backdrop-blur-sm disabled:cursor-wait dark:bg-slate-950/65"
        aria-label="关闭创建会话分支窗口"
      />
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="relative w-full max-w-xl overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl shadow-slate-300/70 dark:border-slate-700 dark:bg-slate-950 dark:shadow-black/50"
      >
        <header className="flex items-center justify-between border-b border-slate-200 px-6 py-5 dark:border-slate-800">
          <h2 id={titleId} className="text-xl font-bold text-slate-950 dark:text-slate-100">创建会话分支</h2>
          <button
            type="button"
            onClick={onClose}
            disabled={pending}
            className="flex h-9 w-9 items-center justify-center rounded-lg text-slate-500 transition hover:bg-slate-100 hover:text-slate-900 disabled:cursor-not-allowed disabled:opacity-40 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-slate-50"
            aria-label="关闭"
          >
            <X size={18} />
          </button>
        </header>
        <form
          onSubmit={(event) => {
            event.preventDefault()
            onSubmit()
          }}
        >
          <div className="space-y-5 px-6 py-5">
            <section className="rounded-xl border border-violet-200 bg-violet-50 px-4 py-4 text-violet-950 dark:border-violet-500/40 dark:bg-violet-500/10 dark:text-violet-100">
              <div className="flex items-center gap-2 text-sm font-black">
                <GitBranch size={17} />
                从 Turn {turnId} 创建分支
              </div>
              <p className="mt-2 text-sm font-semibold leading-6 text-violet-800/80 dark:text-violet-200/80">
                将复制“{sourceLabel}”从 Turn 1 到 Turn {turnId} 的已提交聊天记录；该 Turn 之后的内容不会进入新会话。
              </p>
            </section>

            <p className="text-sm font-semibold leading-6 text-slate-500 dark:text-slate-300">
              后台会重建状态表、搜集完整 Story Memory，并按当前配置执行 Summary。新会话完成这些准备后才会变为可用，终态将在通知中心显示。
            </p>

            <label className="block">
              <span className="mb-2 block text-xs font-black uppercase tracking-wide text-slate-500 dark:text-slate-400">
                新会话标题
              </span>
              <input
                autoFocus
                value={title}
                onChange={(event) => onTitleChange(event.target.value)}
                disabled={pending}
                placeholder={`${sourceLabel} - 分支`}
                className="h-11 w-full rounded-lg border border-slate-200 bg-slate-50 px-3 text-sm font-semibold text-slate-900 outline-none transition placeholder:text-slate-400 focus:border-violet-300 focus:ring-4 focus:ring-violet-100 disabled:cursor-not-allowed disabled:opacity-60 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 dark:placeholder:text-slate-500 dark:focus:border-violet-500 dark:focus:ring-violet-500/20"
              />
              <span className="mt-2 block text-xs font-semibold text-slate-400 dark:text-slate-500">
                可选；留空时由后端使用默认分支标题。
              </span>
            </label>

            {error ? (
              <p role="alert" className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm font-semibold leading-6 text-rose-700 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-200">
                创建失败：{error}
              </p>
            ) : null}
          </div>

          <footer className="flex items-center justify-end gap-2 border-t border-slate-200 bg-slate-50 px-6 py-4 dark:border-slate-800 dark:bg-slate-900">
            <button
              type="button"
              onClick={onClose}
              disabled={pending}
              className="h-10 rounded-lg border border-slate-200 bg-white px-4 text-sm font-black text-slate-700 transition hover:border-violet-200 hover:text-violet-700 disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-300 dark:hover:border-violet-500/60 dark:hover:text-violet-200"
            >
              取消
            </button>
            <button
              type="submit"
              disabled={pending}
              className="inline-flex h-10 items-center gap-2 rounded-lg bg-violet-600 px-4 text-sm font-black text-white shadow-lg shadow-violet-100 transition hover:bg-violet-700 disabled:cursor-not-allowed disabled:opacity-60 dark:shadow-violet-950/40"
            >
              {pending ? <Loader2 size={16} className="animate-spin" /> : <GitBranch size={16} />}
              {pending ? '正在提交' : '创建分支'}
            </button>
          </footer>
        </form>
      </section>
    </div>
  )
}
