'use client'

import { useCallback, useEffect, useId, useRef, useState } from 'react'
import type { ReactNode } from 'react'
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

const DRAWER_TRANSITION_MS = 200

export function SideDrawer({
  open,
  side,
  eyebrow,
  title,
  description,
  meta,
  footer,
  onClose,
  children,
  panelClassName,
  contentClassName,
  overlayClassName = 'z-[60]',
  suspended = false,
}: {
  open: boolean
  side: 'left' | 'right'
  eyebrow: string
  title: string
  description?: string
  meta?: ReactNode
  footer?: ReactNode
  onClose: () => void
  children: ReactNode
  panelClassName?: string
  contentClassName?: string
  overlayClassName?: string
  suspended?: boolean
}) {
  const titleId = useId()
  const descriptionId = useId()
  const panelRef = useRef<HTMLDivElement>(null)
  const closeRef = useRef<HTMLButtonElement>(null)
  const onCloseRef = useRef(onClose)
  const returnTargetRef = useRef<HTMLElement | null>(null)
  const openFrameRef = useRef<number | null>(null)
  const closeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [mounted, setMounted] = useState(open)
  const [visible, setVisible] = useState(false)
  onCloseRef.current = onClose

  const restoreFocus = useCallback(() => {
    const target = returnTargetRef.current
    returnTargetRef.current = null
    window.requestAnimationFrame(() => {
      if (target?.isConnected) target.focus()
    })
  }, [])

  useEffect(() => {
    if (openFrameRef.current !== null) {
      window.cancelAnimationFrame(openFrameRef.current)
      openFrameRef.current = null
    }
    if (closeTimerRef.current) {
      clearTimeout(closeTimerRef.current)
      closeTimerRef.current = null
    }

    if (open) {
      if (!returnTargetRef.current && document.activeElement instanceof HTMLElement) {
        returnTargetRef.current = document.activeElement
      }
      setMounted(true)
      setVisible(false)
      openFrameRef.current = window.requestAnimationFrame(() => {
        openFrameRef.current = window.requestAnimationFrame(() => {
          openFrameRef.current = null
          setVisible(true)
          closeRef.current?.focus()
        })
      })
      return
    }

    if (!mounted) return
    setVisible(false)
    closeTimerRef.current = setTimeout(() => {
      closeTimerRef.current = null
      setMounted(false)
      restoreFocus()
    }, DRAWER_TRANSITION_MS)
  }, [mounted, open, restoreFocus])

  useEffect(() => {
    if (!open || suspended) return

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
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [open, suspended])

  useEffect(() => {
    if (!open || suspended || panelRef.current?.contains(document.activeElement)) return
    closeRef.current?.focus()
  }, [open, suspended])

  useEffect(() => {
    return () => {
      if (openFrameRef.current !== null) window.cancelAnimationFrame(openFrameRef.current)
      if (closeTimerRef.current) clearTimeout(closeTimerRef.current)
      restoreFocus()
    }
  }, [restoreFocus])

  if (!mounted) return null

  return (
    <div className={cn('fixed inset-0', overlayClassName)} role="presentation">
      <div
        className={cn(
          'absolute inset-0 bg-slate-950/25 backdrop-blur-[2px] transition-opacity duration-200 ease-out motion-reduce:transition-none dark:bg-slate-950/65',
          visible ? 'opacity-100' : 'opacity-0',
        )}
        onMouseDown={(event) => {
          if (visible && !suspended && event.currentTarget === event.target) onClose()
        }}
        aria-hidden="true"
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descriptionId : undefined}
        tabIndex={-1}
        className={cn(
          'fixed bottom-3 top-3 flex w-[calc(100%-24px)] max-w-[520px] flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl shadow-slate-950/25 outline-none transition-[transform,opacity] duration-200 ease-out motion-reduce:transition-none dark:border-slate-700 dark:bg-slate-950 dark:shadow-black/60 lg:bottom-[18px] lg:top-[18px]',
          side === 'left' ? 'left-3' : 'right-3',
          visible
            ? 'translate-x-0 scale-100 opacity-100'
            : side === 'left'
              ? '-translate-x-4 scale-[0.985] opacity-0'
              : 'translate-x-4 scale-[0.985] opacity-0',
          panelClassName,
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
              <p id={descriptionId} className="mt-1 text-xs font-semibold leading-5 text-slate-500 dark:text-slate-300">
                {description}
              </p>
            ) : null}
            {meta ? <div className="mt-2">{meta}</div> : null}
          </div>
          <button
            ref={closeRef}
            type="button"
            onClick={onClose}
            disabled={suspended}
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-500 transition hover:border-violet-200 hover:bg-violet-50 hover:text-violet-700 disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-300 dark:hover:border-violet-500/60 dark:hover:bg-violet-500/10 dark:hover:text-violet-200"
            aria-label={`关闭${title}`}
          >
            <X size={17} />
          </button>
        </header>
        <div className={cn('min-h-0 flex-1 overflow-y-auto overscroll-contain px-5 py-5', contentClassName)}>
          {children}
        </div>
        {footer ? (
          <footer className="shrink-0 border-t border-slate-200 bg-slate-50 px-5 py-4 dark:border-slate-800 dark:bg-slate-900/80">
            {footer}
          </footer>
        ) : null}
      </div>
    </div>
  )
}
