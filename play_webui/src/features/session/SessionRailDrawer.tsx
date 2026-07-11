import { useEffect, useId, useRef } from 'react'
import { X } from 'lucide-react'
import { cn } from '@/lib/utils/cn'

const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',')

export function SessionRailDrawer({
  open,
  side,
  eyebrow,
  title,
  description,
  meta,
  onClose,
  children,
}: {
  open: boolean
  side: 'left' | 'right'
  eyebrow: string
  title: string
  description?: string
  meta?: React.ReactNode
  onClose: () => void
  children: React.ReactNode
}) {
  const titleId = useId()
  const panelRef = useRef<HTMLDivElement>(null)
  const closeRef = useRef<HTMLButtonElement>(null)
  const onCloseRef = useRef(onClose)
  onCloseRef.current = onClose

  useEffect(() => {
    if (!open) return
    const returnTarget = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null
    const frame = window.requestAnimationFrame(() => closeRef.current?.focus())

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        onCloseRef.current()
        return
      }
      if (event.key !== 'Tab' || !panelRef.current) return
      const focusable = Array.from(
        panelRef.current.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
      ).filter((element) => element.offsetParent !== null)
      if (!focusable.length) {
        event.preventDefault()
        panelRef.current.focus()
        return
      }
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => {
      window.cancelAnimationFrame(frame)
      document.removeEventListener('keydown', handleKeyDown)
      window.requestAnimationFrame(() => {
        if (returnTarget?.isConnected) returnTarget.focus()
      })
    }
  }, [open])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-[70]" role="presentation">
      <div
        className="absolute inset-0 bg-slate-950/25 backdrop-blur-[2px] dark:bg-slate-950/65"
        onMouseDown={(event) => {
          if (event.currentTarget === event.target) onClose()
        }}
        aria-hidden="true"
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className={cn(
          'fixed bottom-3 top-3 flex w-[calc(100%-24px)] max-w-[520px] flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl shadow-slate-950/25 outline-none dark:border-slate-700 dark:bg-slate-950 dark:shadow-black/60 lg:bottom-[18px] lg:top-[18px]',
          side === 'left'
            ? 'left-3 lg:left-[calc(var(--session-left-rail-width)+22px)]'
            : 'right-3 lg:right-[calc(var(--session-right-rail-width)+22px)]',
        )}
      >
        <header className="flex shrink-0 items-start justify-between gap-4 border-b border-slate-200 bg-slate-50 px-5 py-4 dark:border-slate-800 dark:bg-slate-900/80">
          <div className="min-w-0">
            <span className="block text-[10px] font-black uppercase tracking-[0.12em] text-violet-700 dark:text-violet-300">
              {eyebrow}
            </span>
            <h2 id={titleId} className="mt-1 truncate text-lg font-black text-slate-950 dark:text-slate-100">
              {title}
            </h2>
            {description ? (
              <p className="mt-1 text-xs font-semibold leading-5 text-slate-500 dark:text-slate-300">
                {description}
              </p>
            ) : null}
            {meta ? <div className="mt-2">{meta}</div> : null}
          </div>
          <button
            ref={closeRef}
            type="button"
            onClick={onClose}
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-500 transition hover:border-violet-200 hover:bg-violet-50 hover:text-violet-700 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-300 dark:hover:border-violet-500/60 dark:hover:bg-violet-500/10 dark:hover:text-violet-200"
            aria-label={`关闭${title}`}
          >
            <X size={17} />
          </button>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-5 py-5">
          {children}
        </div>
      </div>
    </div>
  )
}
