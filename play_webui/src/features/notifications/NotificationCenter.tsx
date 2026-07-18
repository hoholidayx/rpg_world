'use client'

import { useEffect, useId, useMemo, useRef, useState } from 'react'
import { Bell, Copy, MoonStar, Trash2, X } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { usePlayEventStore } from '@/stores/playEventStore'
import { formatNotificationTime, toNotificationEntry } from './notificationModel'
import type { NotificationEntry } from './notificationModel'
import { useNotificationStore } from './notificationStore'

const statusStyles: Record<NotificationEntry['status'], {
  label: string
  iconClassName: string
  badgeClassName: string
}> = {
  ready: {
    label: '已完成',
    iconClassName: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-200',
    badgeClassName: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-200',
  },
  failed: {
    label: '失败',
    iconClassName: 'bg-rose-50 text-rose-700 dark:bg-rose-500/15 dark:text-rose-200',
    badgeClassName: 'bg-rose-50 text-rose-700 dark:bg-rose-500/15 dark:text-rose-200',
  },
  interrupted: {
    label: '已中断',
    iconClassName: 'bg-amber-50 text-amber-700 dark:bg-amber-500/15 dark:text-amber-200',
    badgeClassName: 'bg-amber-50 text-amber-700 dark:bg-amber-500/15 dark:text-amber-200',
  },
}

export function NotificationCenter() {
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const panelId = useId()
  const events = usePlayEventStore((state) => state.events)
  const readEventIds = useNotificationStore((state) => state.readEventIds)
  const dismissedEventIds = useNotificationStore((state) => state.dismissedEventIds)
  const markRead = useNotificationStore((state) => state.markRead)
  const dismiss = useNotificationStore((state) => state.dismiss)
  const dismissAll = useNotificationStore((state) => state.dismissAll)
  const reconcile = useNotificationStore((state) => state.reconcile)

  const retainedEventIds = useMemo(() => events.map((event) => event.eventId), [events])
  const visibleEvents = useMemo(() => {
    const dismissed = new Set(dismissedEventIds)
    return events.filter((event) => !dismissed.has(event.eventId))
  }, [dismissedEventIds, events])
  const visibleEventIds = useMemo(
    () => visibleEvents.map((event) => event.eventId),
    [visibleEvents],
  )
  const entries = useMemo(
    () => visibleEvents.map(toNotificationEntry),
    [visibleEvents],
  )
  const unreadCount = useMemo(() => {
    const read = new Set(readEventIds)
    return visibleEvents.reduce(
      (count, event) => count + (read.has(event.eventId) ? 0 : 1),
      0,
    )
  }, [readEventIds, visibleEvents])

  useEffect(() => {
    reconcile(retainedEventIds)
  }, [reconcile, retainedEventIds])

  useEffect(() => {
    if (open) markRead(visibleEventIds)
  }, [markRead, open, visibleEventIds])

  useEffect(() => {
    if (!open) return

    const handlePointerDown = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false)
    }
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
      setOpen(false)
      triggerRef.current?.focus()
    }

    document.addEventListener('pointerdown', handlePointerDown)
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('pointerdown', handlePointerDown)
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [open])

  return (
    <div ref={rootRef} className="relative shrink-0">
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setOpen((isOpen) => !isOpen)}
        className={`relative flex h-10 w-10 items-center justify-center rounded-full border text-slate-500 shadow-sm transition focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-violet-200 dark:focus-visible:ring-violet-500/30 ${
          open
            ? 'border-violet-200 bg-violet-50 text-violet-700 dark:border-violet-500/60 dark:bg-violet-500/15 dark:text-violet-200'
            : 'border-slate-200 bg-white hover:border-violet-200 hover:bg-violet-50 hover:text-violet-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:border-violet-500/60 dark:hover:bg-violet-500/10 dark:hover:text-violet-200'
        }`}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls={panelId}
        aria-label={unreadCount ? `通知，${unreadCount} 条未读` : '通知'}
        title="通知"
      >
        <Bell size={19} fill={unreadCount ? 'currentColor' : 'none'} />
        {unreadCount ? (
          <span className="absolute -right-1.5 -top-1.5 flex h-5 min-w-5 items-center justify-center rounded-full bg-rose-500 px-1 text-[10px] font-black leading-none text-white ring-2 ring-white dark:ring-slate-950">
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        ) : null}
      </button>

      {open ? (
        <section
          id={panelId}
          role="dialog"
          aria-label="通知中心"
          className="absolute right-[-3.5rem] top-full z-50 mt-3 flex max-h-[calc(100vh-96px)] w-[calc(100vw-2rem)] flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white text-left shadow-2xl shadow-slate-900/15 dark:border-slate-700 dark:bg-slate-950 dark:shadow-black/40 sm:right-0 sm:max-h-[520px] sm:w-[380px]"
        >
          <header className="flex shrink-0 items-center justify-between gap-3 border-b border-slate-200 px-4 py-3.5 dark:border-slate-800">
            <div>
              <h2 className="text-sm font-black text-slate-950 dark:text-slate-50">通知</h2>
              <p className="mt-0.5 text-xs font-medium text-slate-500 dark:text-slate-400">
                {entries.length ? `当前保留 ${entries.length} 条` : '暂无通知'}
              </p>
            </div>
            <button
              type="button"
              onClick={() => dismissAll(visibleEventIds)}
              disabled={entries.length === 0}
              className="inline-flex h-8 items-center gap-1.5 rounded-lg px-2.5 text-xs font-bold text-slate-500 transition hover:bg-slate-100 hover:text-slate-900 disabled:cursor-not-allowed disabled:opacity-40 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100"
            >
              <Trash2 size={14} />
              全部清除
            </button>
          </header>

          {entries.length ? (
            <ul className="min-h-0 overflow-y-auto divide-y divide-slate-100 dark:divide-slate-800">
              {entries.map((entry) => (
                <NotificationRow
                  key={entry.id}
                  entry={entry}
                  unread={!readEventIds.includes(entry.id)}
                  onDismiss={() => dismiss(entry.id)}
                />
              ))}
            </ul>
          ) : (
            <div className="flex min-h-48 flex-col items-center justify-center px-6 py-10 text-center">
              <span className="flex h-12 w-12 items-center justify-center rounded-full bg-slate-100 text-slate-400 dark:bg-slate-900 dark:text-slate-500">
                <Bell size={21} />
              </span>
              <p className="mt-3 text-sm font-bold text-slate-700 dark:text-slate-200">暂时没有通知</p>
              <p className="mt-1 text-xs leading-5 text-slate-500 dark:text-slate-400">
                Dream 与会话复制完成后会显示在这里。
              </p>
            </div>
          )}
        </section>
      ) : null}
    </div>
  )
}

function NotificationRow({
  entry,
  unread,
  onDismiss,
}: {
  entry: NotificationEntry
  unread: boolean
  onDismiss: () => void
}) {
  const Icon: LucideIcon = entry.category === 'dream' ? MoonStar : Copy
  const styles = statusStyles[entry.status]

  return (
    <li className={`relative flex gap-3 px-4 py-4 transition ${
      unread ? 'bg-violet-50/60 dark:bg-violet-500/5' : 'bg-white dark:bg-slate-950'
    }`}>
      <span className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${styles.iconClassName}`}>
        <Icon size={18} />
      </span>
      <div className="min-w-0 flex-1 pr-7">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="text-sm font-bold text-slate-900 dark:text-slate-100">{entry.title}</h3>
          <span className={`inline-flex h-5 items-center rounded-full px-2 text-[10px] font-black ${styles.badgeClassName}`}>
            {styles.label}
          </span>
          {unread ? <span className="h-1.5 w-1.5 rounded-full bg-violet-500" aria-label="未读" /> : null}
        </div>
        <p className="mt-1 break-words text-xs font-medium leading-5 text-slate-500 dark:text-slate-400">
          {entry.description}
        </p>
        {entry.detail ? (
          <p className="mt-1 break-words text-xs leading-5 text-slate-600 dark:text-slate-300">
            {entry.detail}
          </p>
        ) : null}
        <time
          dateTime={entry.occurredAt}
          className="mt-2 block text-[11px] font-medium text-slate-400 dark:text-slate-500"
        >
          {formatNotificationTime(entry.occurredAt)}
        </time>
      </div>
      <button
        type="button"
        onClick={onDismiss}
        className="absolute right-3 top-3 flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 transition hover:bg-slate-100 hover:text-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-300 dark:hover:bg-slate-800 dark:hover:text-slate-100"
        aria-label={`清除通知：${entry.title}`}
        title="清除这条通知"
      >
        <X size={15} />
      </button>
    </li>
  )
}
