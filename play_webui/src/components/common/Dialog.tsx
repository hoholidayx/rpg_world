'use client'

import type { ReactNode } from 'react'
import { Loader2, Trash2, X } from 'lucide-react'
import { cn } from '@/lib/utils/cn'

type DialogSize = 'xl' | '3xl'

const dialogSizeClass: Record<DialogSize, string> = {
  xl: 'max-w-xl',
  '3xl': 'max-w-3xl',
}

export function Dialog({
  title,
  onClose,
  children,
  size = '3xl',
  className,
  overlayClassName,
  closeDisabled = false,
}: {
  title: string
  onClose: () => void
  children: ReactNode
  size?: DialogSize
  className?: string
  overlayClassName?: string
  closeDisabled?: boolean
}) {
  return (
    <div className={cn('fixed inset-0 flex items-center justify-center bg-slate-950/20 px-4 py-8 backdrop-blur-sm', overlayClassName ?? 'z-50')}>
      <section
        className={cn(
          'w-full overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl shadow-slate-300/70',
          dialogSizeClass[size],
          className,
        )}
      >
        <header className="flex items-center justify-between border-b border-slate-200 px-6 py-5">
          <h2 className="text-xl font-bold text-slate-950">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            disabled={closeDisabled}
            className="flex h-9 w-9 items-center justify-center rounded-lg text-slate-500 transition hover:bg-slate-100 hover:text-slate-900 disabled:cursor-not-allowed disabled:opacity-40"
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

export function ConfirmDialog({
  title,
  heading,
  body,
  pending,
  disabled,
  confirmLabel = '删除',
  cancelLabel = '取消',
  onClose,
  onConfirm,
}: {
  title: string
  heading: string
  body: ReactNode
  pending: boolean
  disabled?: boolean
  confirmLabel?: string
  cancelLabel?: string
  onClose: () => void
  onConfirm: () => void
}) {
  return (
    <Dialog title={title} onClose={onClose} size="xl" overlayClassName="z-[70]" closeDisabled={pending}>
      <div className="px-6 py-5">
        <div className="rounded-2xl border border-rose-100 bg-rose-50 px-4 py-4">
          <h3 className="text-sm font-bold text-rose-700">{heading}</h3>
          <div className="mt-2 text-sm leading-6 text-rose-700/80">{body}</div>
        </div>
      </div>
      <footer className="flex items-center justify-end gap-2 border-t border-slate-200 bg-slate-50 px-6 py-4">
        <button
          type="button"
          onClick={onClose}
          disabled={pending}
          className="h-10 rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700 transition hover:border-violet-200 hover:text-violet-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {cancelLabel}
        </button>
        <button
          type="button"
          onClick={onConfirm}
          disabled={disabled || pending}
          className="flex h-10 items-center gap-2 rounded-lg bg-rose-600 px-4 text-sm font-semibold text-white shadow-lg shadow-rose-100 transition hover:bg-rose-700 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {pending ? <Loader2 size={16} className="animate-spin" /> : <Trash2 size={16} />}
          {confirmLabel}
        </button>
      </footer>
    </Dialog>
  )
}
