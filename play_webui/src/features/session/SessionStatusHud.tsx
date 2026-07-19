'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ChevronRight, Layers3, MapPinned, MoreHorizontal, TableProperties, X } from 'lucide-react'
import { cn } from '@/lib/utils/cn'
import type { StatusTable } from '@/types/statusTables'

type HudTable = {
  table: StatusTable
  scene: boolean
  primary: boolean
}

const HUD_ITEM_HEIGHT = 58
const HUD_ITEM_GAP = 8
const HUD_HOVER_CLOSE_DELAY_MS = 180

function sortedTables(tables: StatusTable[]) {
  return [...tables].sort((first, second) => (
    first.sortOrder - second.sortOrder || first.id - second.id
  ))
}

function firstRowValue(table: StatusTable) {
  return table.rows.find((row) => row.value.trim())
}

function rowValue(table: StatusTable, keys: string[]) {
  const normalized = new Set(keys.map((key) => key.toLocaleLowerCase()))
  return table.rows.find((row) => normalized.has(row.key.trim().toLocaleLowerCase()))?.value.trim() ?? ''
}

function hudSummary(item: HudTable) {
  if (item.scene) {
    const location = rowValue(item.table, ['location', '位置', '地点', '场所'])
    const time = rowValue(item.table, ['time', '时间', '时刻'])
    if (location || time) return [location, time].filter(Boolean).join(' · ')
  }
  const row = firstRowValue(item.table)
  return row ? `${row.key} · ${row.value}` : '暂无状态值'
}

function HudLauncher({
  item,
  expanded,
  onOpen,
  onHoverEnd,
}: {
  item: HudTable
  expanded: boolean
  onOpen: (element: HTMLButtonElement) => void
  onHoverEnd: () => void
}) {
  return (
    <button
      type="button"
      onClick={(event) => onOpen(event.currentTarget)}
      onMouseEnter={(event) => onOpen(event.currentTarget)}
      onMouseLeave={onHoverEnd}
      onFocus={(event) => onOpen(event.currentTarget)}
      className={cn(
        'pointer-events-auto grid h-[58px] w-48 grid-cols-[34px_minmax(0,1fr)_14px] items-center gap-2 rounded-xl border bg-white/92 px-2.5 text-left shadow-lg backdrop-blur-md transition hover:translate-x-1 dark:bg-slate-950/90',
        item.primary
          ? 'border-teal-300 shadow-teal-950/10 dark:border-teal-500/50'
          : item.scene
            ? 'border-teal-200 dark:border-teal-500/30'
            : 'border-violet-200 dark:border-violet-500/30',
      )}
      aria-haspopup="dialog"
      aria-expanded={expanded}
      title={`${item.table.name} · ${hudSummary(item)}`}
    >
      <span className={cn(
        'flex h-8 w-8 items-center justify-center rounded-lg',
        item.scene
          ? 'bg-teal-100 text-teal-700 dark:bg-teal-500/15 dark:text-teal-200'
          : 'bg-violet-100 text-violet-700 dark:bg-violet-500/15 dark:text-violet-200',
      )}>
        {item.scene ? <MapPinned size={15} /> : <TableProperties size={15} />}
      </span>
      <span className="min-w-0">
        <strong className="block truncate text-xs font-black text-slate-950 dark:text-slate-100">{item.table.name}</strong>
        <span className="mt-0.5 block truncate text-[10px] font-bold text-slate-500 dark:text-slate-300">{hudSummary(item)}</span>
      </span>
      <ChevronRight size={14} className="text-slate-400" />
    </button>
  )
}

function TablePopover({
  item,
  top,
  onClose,
  onHoverStart,
  onHoverEnd,
}: {
  item: HudTable
  top: number
  onClose: () => void
  onHoverStart: () => void
  onHoverEnd: () => void
}) {
  return (
    <section
      role="dialog"
      aria-label={`${item.table.name}状态详情`}
      style={{ top }}
      onMouseEnter={onHoverStart}
      onMouseLeave={onHoverEnd}
      className="pointer-events-auto fixed bottom-auto left-[216px] z-[59] flex max-h-[min(520px,calc(100vh-180px))] w-[min(440px,calc(100vw-240px))] flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white/98 shadow-2xl shadow-slate-950/20 backdrop-blur-xl dark:border-slate-700 dark:bg-slate-950/98 dark:shadow-black/60 max-md:!bottom-28 max-md:!left-3 max-md:!right-3 max-md:!top-auto max-md:max-h-[60vh] max-md:w-auto"
    >
      <header className="flex shrink-0 items-start justify-between gap-3 border-b border-slate-200 bg-slate-50 px-4 py-3 dark:border-slate-800 dark:bg-slate-900">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="truncate text-sm font-black text-slate-950 dark:text-slate-100">{item.table.name}</h3>
            <span className={cn(
              'rounded-full px-2 py-0.5 text-[10px] font-black',
              item.scene
                ? 'bg-teal-100 text-teal-700 dark:bg-teal-500/15 dark:text-teal-200'
                : 'bg-violet-100 text-violet-700 dark:bg-violet-500/15 dark:text-violet-200',
            )}>
              {item.primary ? '主场景' : item.scene ? '场景表' : 'HUD 固定'}
            </span>
          </div>
          {item.table.description ? <p className="mt-1 line-clamp-2 text-xs font-semibold leading-5 text-slate-500 dark:text-slate-300">{item.table.description}</p> : null}
        </div>
        <button type="button" onClick={onClose} className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-slate-500 hover:bg-slate-200 dark:text-slate-300 dark:hover:bg-slate-800" aria-label="关闭状态详情">
          <X size={15} />
        </button>
      </header>
      <div className="min-h-0 overflow-y-auto">
        {item.table.rows.length ? (
          <dl className="divide-y divide-slate-100 dark:divide-slate-800">
            {item.table.rows.map((row) => (
              <div key={`${item.table.id}-${row.key}`} className="grid gap-1 px-4 py-3 text-xs leading-5 sm:grid-cols-[110px_minmax(0,1fr)] sm:gap-4">
                <dt className="font-bold text-slate-400">{row.key}</dt>
                <dd className="min-w-0 whitespace-pre-wrap break-words font-semibold text-slate-700 dark:text-slate-200">{row.value || '—'}</dd>
              </div>
            ))}
          </dl>
        ) : <p className="px-4 py-8 text-center text-sm font-semibold text-slate-400">暂无字段</p>}
      </div>
    </section>
  )
}

export function SessionStatusHud({
  sceneTables,
  pinnedTables,
  panelOpen,
  onOpenStatusPanel,
}: {
  sceneTables: StatusTable[]
  pinnedTables: StatusTable[]
  panelOpen: boolean
  onOpenStatusPanel: (tableId?: number) => void
}) {
  const rootRef = useRef<HTMLDivElement>(null)
  const listRef = useRef<HTMLDivElement>(null)
  const hoverCloseTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [availableSlots, setAvailableSlots] = useState(5)
  const [activeTableId, setActiveTableId] = useState<number | null>(null)
  const [popoverTop, setPopoverTop] = useState(96)
  const [pickerOpen, setPickerOpen] = useState(false)
  const [pickerTop, setPickerTop] = useState(96)

  const items = useMemo<HudTable[]>(() => [
    ...sortedTables(sceneTables).map((table, index) => ({ table, scene: true, primary: index === 0 })),
    ...sortedTables(pinnedTables).map((table) => ({ table, scene: false, primary: false })),
  ], [pinnedTables, sceneTables])

  useEffect(() => {
    const element = listRef.current
    if (!element) return
    const update = () => {
      const height = element.getBoundingClientRect().height
      setAvailableSlots(Math.max(1, Math.floor((height + HUD_ITEM_GAP) / (HUD_ITEM_HEIGHT + HUD_ITEM_GAP))))
    }
    update()
    const observer = new ResizeObserver(update)
    observer.observe(element)
    return () => observer.disconnect()
  }, [items.length, panelOpen])

  const cancelHoverClose = useCallback(() => {
    if (!hoverCloseTimerRef.current) return
    clearTimeout(hoverCloseTimerRef.current)
    hoverCloseTimerRef.current = null
  }, [])

  const closeFloatingLayers = useCallback(() => {
    cancelHoverClose()
    setActiveTableId(null)
    setPickerOpen(false)
  }, [cancelHoverClose])

  const scheduleHoverClose = useCallback(() => {
    cancelHoverClose()
    hoverCloseTimerRef.current = setTimeout(() => {
      hoverCloseTimerRef.current = null
      if (rootRef.current?.contains(document.activeElement)) return
      setActiveTableId(null)
      setPickerOpen(false)
    }, HUD_HOVER_CLOSE_DELAY_MS)
  }, [cancelHoverClose])

  useEffect(() => {
    if (panelOpen) closeFloatingLayers()
  }, [closeFloatingLayers, panelOpen])

  useEffect(() => {
    if (activeTableId !== null && !items.some((item) => item.table.id === activeTableId)) {
      setActiveTableId(null)
    }
  }, [activeTableId, items])

  useEffect(() => {
    const handlePointerDown = (event: PointerEvent) => {
      if (rootRef.current?.contains(event.target as Node)) return
      closeFloatingLayers()
    }
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') closeFloatingLayers()
    }
    document.addEventListener('pointerdown', handlePointerDown)
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('pointerdown', handlePointerDown)
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [closeFloatingLayers])

  useEffect(() => () => cancelHoverClose(), [cancelHoverClose])

  if (!items.length || panelOpen) return null

  const visibleCount = items.length > availableSlots
    ? Math.max(1, availableSlots - 1)
    : items.length
  const visibleItems = items.slice(0, visibleCount)
  const hiddenItems = items.slice(visibleCount)
  const activeItem = items.find((item) => item.table.id === activeTableId) ?? null

  const openTable = (item: HudTable, element?: HTMLElement) => {
    cancelHoverClose()
    if (element) {
      const rect = element.getBoundingClientRect()
      setPopoverTop(Math.max(88, Math.min(rect.top, window.innerHeight - 440)))
    }
    setPickerOpen(false)
    setActiveTableId(item.table.id)
  }

  const openPicker = (element?: HTMLElement) => {
    cancelHoverClose()
    if (element) {
      const rect = element.getBoundingClientRect()
      setPickerTop(Math.max(88, Math.min(rect.top, window.innerHeight - 340)))
    }
    setActiveTableId(null)
    setPickerOpen(true)
  }

  const pickerItems = hiddenItems.length ? hiddenItems : items

  return (
    <div
      ref={rootRef}
      className="fixed inset-0 z-[55] pointer-events-none"
      aria-label="悬浮状态 HUD"
      onFocusCapture={cancelHoverClose}
      onBlurCapture={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) scheduleHoverClose()
      }}
    >
      <div ref={listRef} className="fixed bottom-36 left-4 top-24 hidden flex-col gap-2 md:flex">
        {visibleItems.map((item) => (
          <HudLauncher
            key={`${item.scene ? 'scene' : 'normal'}-${item.table.id}`}
            item={item}
            expanded={activeTableId === item.table.id}
            onOpen={(element) => openTable(item, element)}
            onHoverEnd={scheduleHoverClose}
          />
        ))}
        {hiddenItems.length ? (
          <button
            type="button"
            onClick={(event) => openPicker(event.currentTarget)}
            onMouseEnter={(event) => openPicker(event.currentTarget)}
            onMouseLeave={scheduleHoverClose}
            onFocus={(event) => openPicker(event.currentTarget)}
            className="pointer-events-auto flex h-[58px] w-48 items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white/92 text-xs font-black text-slate-600 shadow-lg backdrop-blur-md transition hover:translate-x-1 hover:border-violet-300 hover:text-violet-700 dark:border-slate-700 dark:bg-slate-950/90 dark:text-slate-300"
            aria-label={`查看另外 ${hiddenItems.length} 张状态表`}
            aria-haspopup="dialog"
            aria-expanded={pickerOpen}
          >
            <MoreHorizontal size={17} /> +{hiddenItems.length} 张状态表
          </button>
        ) : null}
      </div>

      <button
        type="button"
        onClick={(event) => openPicker(event.currentTarget)}
        className="pointer-events-auto fixed bottom-28 left-4 flex h-12 items-center gap-2 rounded-full border border-violet-200 bg-white/95 px-4 text-sm font-black text-violet-700 shadow-xl backdrop-blur-md dark:border-violet-500/40 dark:bg-slate-950/95 dark:text-violet-200 md:hidden"
        aria-label={`打开状态 HUD，共 ${items.length} 张表`}
      >
        <Layers3 size={17} /> 状态 · {items.length}
      </button>

      {pickerOpen ? (
        <section
          role="dialog"
          aria-label="选择状态表"
          style={{ top: pickerTop }}
          onMouseEnter={cancelHoverClose}
          onMouseLeave={scheduleHoverClose}
          className="pointer-events-auto fixed left-[216px] z-[58] w-80 overflow-hidden rounded-2xl border border-slate-200 bg-white/98 shadow-2xl backdrop-blur-xl dark:border-slate-700 dark:bg-slate-950/98 max-md:!bottom-24 max-md:!left-3 max-md:!right-3 max-md:!top-auto max-md:w-auto"
        >
          <header className="flex items-center justify-between border-b border-slate-200 bg-slate-50 px-4 py-3 dark:border-slate-800 dark:bg-slate-900">
            <div>
              <h3 className="text-sm font-black text-slate-950 dark:text-slate-100">{hiddenItems.length ? '更多状态表' : '状态 HUD'}</h3>
              <p className="mt-0.5 text-[11px] font-semibold text-slate-400">悬停展开列表 · 点击查看全部字段</p>
            </div>
            <button type="button" onClick={() => setPickerOpen(false)} className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-500 hover:bg-slate-200 dark:text-slate-300 dark:hover:bg-slate-800" aria-label="关闭状态表选择器"><X size={15} /></button>
          </header>
          <div className="max-h-64 overflow-y-auto p-2">
            {pickerItems.map((item) => (
              <button
                key={`${item.scene ? 'scene' : 'normal'}-${item.table.id}`}
                type="button"
                onClick={(event) => openTable(item, event.currentTarget)}
                className="grid w-full grid-cols-[32px_minmax(0,1fr)_14px] items-center gap-2 rounded-xl px-2 py-2.5 text-left transition hover:bg-violet-50 dark:hover:bg-violet-500/10"
              >
                <span className={cn('flex h-8 w-8 items-center justify-center rounded-lg', item.scene ? 'bg-teal-100 text-teal-700 dark:bg-teal-500/15 dark:text-teal-200' : 'bg-violet-100 text-violet-700 dark:bg-violet-500/15 dark:text-violet-200')}>
                  {item.scene ? <MapPinned size={14} /> : <TableProperties size={14} />}
                </span>
                <span className="min-w-0">
                  <strong className="block truncate text-xs font-black text-slate-900 dark:text-slate-100">{item.table.name}</strong>
                  <span className="mt-0.5 block truncate text-[10px] font-semibold text-slate-400">{hudSummary(item)}</span>
                </span>
                <ChevronRight size={14} className="text-slate-400" />
              </button>
            ))}
          </div>
          <footer className="border-t border-slate-200 p-2 dark:border-slate-800">
            <button
              type="button"
              onClick={() => {
                closeFloatingLayers()
                onOpenStatusPanel()
              }}
              className="flex h-10 w-full items-center justify-center gap-2 rounded-xl bg-slate-950 text-xs font-black text-white dark:bg-violet-600"
            >
              <Layers3 size={15} /> 查看与管理全部状态表
            </button>
          </footer>
        </section>
      ) : null}

      {activeItem ? (
        <TablePopover
          item={activeItem}
          top={popoverTop}
          onClose={() => setActiveTableId(null)}
          onHoverStart={cancelHoverClose}
          onHoverEnd={scheduleHoverClose}
        />
      ) : null}
    </div>
  )
}
