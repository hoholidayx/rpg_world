import { type KeyboardEvent, type ReactNode, useEffect, useId, useRef, useState } from 'react'
import { Check, ChevronDown, Plane, Square } from 'lucide-react'
import { CommandPaletteDialog } from '@/components/input/CommandPaletteDialog'
import { cn } from '@/lib/utils/cn'
import type { ContextUsageSnapshot } from '@/types/contextUsage'
import { SessionContextUsageIndicator } from './SessionContextUsageIndicator'
import type { NarrativeStyle, NarrativeStyleId, SessionInputMode } from './sessionRoomTypes'

const inputModes: Array<{ id: SessionInputMode; label: string }> = [
  { id: 'ic', label: 'IC' },
  { id: 'ooc', label: 'OOC' },
  { id: 'gm', label: 'GM' },
]

type SelectOption<TValue extends string> = {
  id: TValue
  label: string
}

function PopupSingleSelect<TValue extends string>({
  label,
  value,
  options,
  onChange,
  side = 'bottom',
  align = 'left',
  icon,
}: {
  label: string
  value: TValue
  options: Array<SelectOption<TValue>>
  onChange: (value: TValue) => void
  side?: 'top' | 'bottom'
  align?: 'left' | 'right'
  icon?: ReactNode
}) {
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement | null>(null)
  const triggerRef = useRef<HTMLButtonElement | null>(null)
  const optionRefs = useRef<Array<HTMLButtonElement | null>>([])
  const menuId = useId()
  const selectedIndex = Math.max(
    0,
    options.findIndex((option) => option.id === value),
  )
  const selected = options[selectedIndex]

  useEffect(() => {
    if (!open) return
    const handlePointerDown = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false)
    }
    const handleKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key === 'Escape') {
        setOpen(false)
        requestAnimationFrame(() => triggerRef.current?.focus())
      }
    }
    document.addEventListener('pointerdown', handlePointerDown)
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('pointerdown', handlePointerDown)
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [open])

  useEffect(() => {
    if (open) optionRefs.current[selectedIndex]?.focus()
  }, [open, selectedIndex])

  const selectOptionAt = (index: number) => {
    const nextIndex = (index + options.length) % options.length
    onChange(options[nextIndex].id)
    optionRefs.current[nextIndex]?.focus()
  }

  const handleOptionKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    let nextIndex: number | null = null
    if (event.key === 'ArrowDown' || event.key === 'ArrowRight') nextIndex = selectedIndex + 1
    if (event.key === 'ArrowUp' || event.key === 'ArrowLeft') nextIndex = selectedIndex - 1
    if (event.key === 'Home') nextIndex = 0
    if (event.key === 'End') nextIndex = options.length - 1
    if (nextIndex === null) return

    event.preventDefault()
    selectOptionAt(nextIndex)
  }

  return (
    <div ref={rootRef} className="relative">
      <button
        ref={triggerRef}
        type="button"
        aria-controls={open ? menuId : undefined}
        aria-expanded={open}
        aria-haspopup="true"
        onClick={() => setOpen((current) => !current)}
        className={cn(
          'inline-flex h-9 min-w-32 max-w-full items-center justify-between gap-3 rounded-lg border border-slate-200 bg-white px-3 text-left text-xs font-black text-slate-700 shadow-sm transition hover:border-violet-200 hover:bg-violet-50 hover:text-violet-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:shadow-black/30 dark:hover:border-violet-500/60 dark:hover:bg-violet-500/10 dark:hover:text-violet-100',
          open ? 'border-violet-200 bg-violet-50 text-violet-700 ring-4 ring-violet-100 dark:border-violet-500/60 dark:bg-violet-500/10 dark:text-violet-100 dark:ring-violet-500/20' : '',
        )}
      >
        <span className="flex min-w-0 items-center gap-2">
          {icon ? <span className="shrink-0 text-slate-400 dark:text-slate-300">{icon}</span> : null}
          <span className="font-semibold text-slate-400 dark:text-slate-400">{label}</span>
          <strong className="truncate text-slate-900 dark:text-slate-100">{selected?.label ?? '-'}</strong>
        </span>
        <ChevronDown size={15} className={cn('shrink-0 transition', open ? 'rotate-180' : '')} />
      </button>

      {open ? (
        <div
          role="radiogroup"
          id={menuId}
          aria-label={label}
          className={cn(
            'absolute z-40 w-44 overflow-hidden rounded-lg border border-slate-200 bg-white p-1 shadow-2xl shadow-slate-900/15 dark:border-slate-700 dark:bg-slate-950 dark:shadow-black/50',
            side === 'top' ? 'bottom-[calc(100%+8px)]' : 'top-[calc(100%+8px)]',
            align === 'right' ? 'right-0' : 'left-0',
          )}
        >
          {options.map((option, index) => {
            const active = option.id === value
            return (
              <button
                key={option.id}
                type="button"
                role="radio"
                aria-checked={active}
                tabIndex={active ? 0 : -1}
                ref={(element) => {
                  optionRefs.current[index] = element
                }}
                onClick={() => {
                  onChange(option.id)
                  setOpen(false)
                }}
                onKeyDown={handleOptionKeyDown}
                className={cn(
                  'grid h-9 w-full grid-cols-[18px_minmax(0,1fr)] items-center gap-2 rounded-md px-2 text-left text-xs font-black transition',
                  active
                    ? 'bg-violet-50 text-violet-700 dark:bg-violet-500/15 dark:text-violet-100'
                    : 'text-slate-500 hover:bg-slate-50 hover:text-slate-900 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-slate-50',
                )}
              >
                <span className="flex h-4 w-4 items-center justify-center">
                  {active ? <Check size={14} /> : null}
                </span>
                <span className="truncate">{option.label}</span>
              </button>
            )
          })}
        </div>
      ) : null}
    </div>
  )
}

export function SessionComposer({
  sessionId,
  text,
  mode,
  narrativeStyleId,
  narrativeStyles,
  sending,
  stopping = false,
  disabled = false,
  contextUsage,
  contextUsageLoading = false,
  onTextChange,
  onModeChange,
  onNarrativeStyleChange,
  onSend,
  onStop,
}: {
  sessionId: string
  text: string
  mode: SessionInputMode
  narrativeStyleId: NarrativeStyleId
  narrativeStyles: NarrativeStyle[]
  sending: boolean
  stopping?: boolean
  disabled?: boolean
  contextUsage?: ContextUsageSnapshot | null
  contextUsageLoading?: boolean
  onTextChange: (value: string) => void
  onModeChange: (mode: SessionInputMode) => void
  onNarrativeStyleChange: (styleId: NarrativeStyleId) => void
  onSend: () => void
  onStop: () => void
}) {
  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      if (disabled) return
      if (stopping) return
      if (sending) onStop()
      else onSend()
    }
  }

  const actionDisabled = disabled || stopping
  const actionStopping = stopping
  const actionSending = sending || stopping
  const narrativeOptions: Array<SelectOption<NarrativeStyleId>> = narrativeStyles.map((style) => ({
    id: style.id,
    label: style.label,
  }))

  return (
    <section className="border-t border-slate-200 bg-white px-4 py-4 dark:border-slate-800 dark:bg-slate-950/95 sm:px-6">
      <div className="mx-auto max-w-6xl overflow-visible rounded-lg border border-slate-200 bg-white shadow-sm dark:border-slate-700 dark:bg-slate-900 dark:shadow-black/30">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-4 py-2 dark:border-slate-800">
          <PopupSingleSelect
            label="模式"
            value={mode}
            options={inputModes}
            onChange={onModeChange}
            side="bottom"
            align="left"
          />
          <CommandPaletteDialog sessionId={sessionId} />
        </div>

        <div className="grid gap-3 px-4 py-3 sm:grid-cols-[minmax(0,1fr)_128px]">
          <textarea
            value={text}
            onChange={(event) => onTextChange(event.target.value)}
            onKeyDown={handleKeyDown}
            disabled={disabled}
            className="min-h-24 resize-none border-0 bg-transparent pt-2 text-[length:var(--session-composer-font-size)] leading-[var(--session-composer-line-height)] text-slate-900 outline-none placeholder:text-slate-400 disabled:cursor-not-allowed disabled:text-slate-400 dark:text-slate-100 dark:placeholder:text-slate-500 dark:disabled:text-slate-500"
            placeholder={disabled ? '请先选择你要扮演的角色' : '输入你的行动、台词或 GM 指令...'}
          />
          <button
            type="button"
            onClick={sending ? onStop : onSend}
            disabled={actionDisabled}
            className={cn(
              'my-1 flex min-h-20 items-center justify-center gap-2 rounded-lg px-5 text-base font-black text-white shadow-lg transition sm:min-h-24',
              actionDisabled
                ? 'cursor-not-allowed bg-slate-300 shadow-none dark:bg-slate-700'
                : sending
                ? 'bg-rose-500 shadow-rose-100 hover:bg-rose-600 dark:shadow-rose-950/30'
                : 'bg-violet-600 shadow-violet-200 hover:bg-violet-700 dark:shadow-violet-950/40',
            )}
          >
            {actionSending ? <Square size={16} fill="currentColor" /> : <Plane size={17} fill="currentColor" />}
            {actionStopping ? '停止中' : sending ? '停止' : '发送'}
          </button>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3 rounded-b-lg bg-slate-50 px-4 py-2 dark:bg-slate-950/60">
          <PopupSingleSelect
            label="风格"
            value={narrativeStyleId}
            options={narrativeOptions}
            onChange={onNarrativeStyleChange}
            side="top"
            align="left"
          />
          <div className="ml-auto flex flex-wrap items-center justify-end gap-3">
            <p className="text-xs font-semibold text-slate-400 dark:text-slate-300">Enter 发送 / Shift+Enter 换行</p>
            <SessionContextUsageIndicator usage={contextUsage} loading={contextUsageLoading} />
          </div>
        </div>
      </div>
    </section>
  )
}
