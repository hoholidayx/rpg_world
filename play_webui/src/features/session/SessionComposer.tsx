import { type KeyboardEvent, type ReactNode, useEffect, useId, useRef, useState } from 'react'
import { AlertTriangle, Check, ChevronDown, Cpu, Plane, Square } from 'lucide-react'
import { CommandPaletteDialog } from '@/components/input/CommandPaletteDialog'
import { cn } from '@/lib/utils/cn'
import type { ContextUsageSnapshot } from '@/types/contextUsage'
import type { MainLLMProviderCatalog, MainLLMSelection } from '@/types/mainLLM'
import { SessionContextUsageIndicator } from './SessionContextUsageIndicator'
import { isSlashCommandInput } from './contextWindowGate'
import type { NarrativeStyle, NarrativeStyleId, SessionInputMode } from './sessionRoomTypes'

const inputModes: Array<{ id: SessionInputMode; label: string }> = [
  { id: 'ic', label: 'IC' },
  { id: 'ooc', label: 'OOC' },
  { id: 'gm', label: 'GM' },
]

const INHERIT_MAIN_LLM_OPTION = '__inherit_main_llm__'

function formatContextWindow(value: number | null | undefined) {
  if (!value || value <= 0) return '窗口未知'
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(value % 1_000_000 ? 1 : 0)}M context`
  if (value >= 1_000) return `${(value / 1_000).toFixed(value % 1_000 ? 1 : 0)}K context`
  return `${value} context`
}

function mainLLMSourceLabel(source: MainLLMSelection['effectiveSource'] | undefined) {
  if (source === 'session') return '会话覆盖'
  if (source === 'story') return '故事默认'
  return '系统默认'
}

type SelectOption<TValue extends string> = {
  id: TValue
  label: string
  description?: string
}

function PopupSingleSelect<TValue extends string>({
  label,
  value,
  options,
  onChange,
  side = 'bottom',
  align = 'left',
  icon,
  disabled = false,
  statusMessage,
}: {
  label: string
  value: TValue
  options: Array<SelectOption<TValue>>
  onChange: (value: TValue) => void
  side?: 'top' | 'bottom'
  align?: 'left' | 'right'
  icon?: ReactNode
  disabled?: boolean
  statusMessage?: string | null
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
  const detailedMenu = options.some((option) => option.description) || Boolean(statusMessage)

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
        disabled={disabled}
        onClick={() => setOpen((current) => !current)}
        className={cn(
          'inline-flex h-9 min-w-32 max-w-full items-center justify-between gap-3 rounded-lg border border-slate-200 bg-white px-3 text-left text-xs font-black text-slate-700 shadow-sm transition hover:border-violet-200 hover:bg-violet-50 hover:text-violet-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:shadow-black/30 dark:hover:border-violet-500/60 dark:hover:bg-violet-500/10 dark:hover:text-violet-100',
          open ? 'border-violet-200 bg-violet-50 text-violet-700 ring-4 ring-violet-100 dark:border-violet-500/60 dark:bg-violet-500/10 dark:text-violet-100 dark:ring-violet-500/20' : '',
          disabled ? 'cursor-not-allowed opacity-60' : '',
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
            'absolute z-40 overflow-hidden rounded-lg border border-slate-200 bg-white p-1 shadow-2xl shadow-slate-900/15 dark:border-slate-700 dark:bg-slate-950 dark:shadow-black/50',
            detailedMenu ? 'w-72' : 'w-44',
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
                  'grid min-h-9 w-full grid-cols-[18px_minmax(0,1fr)] items-center gap-2 rounded-md px-2 py-2 text-left text-xs font-black transition',
                  active
                    ? 'bg-violet-50 text-violet-700 dark:bg-violet-500/15 dark:text-violet-100'
                    : 'text-slate-500 hover:bg-slate-50 hover:text-slate-900 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-slate-50',
                )}
              >
                <span className="flex h-4 w-4 items-center justify-center">
                  {active ? <Check size={14} /> : null}
                </span>
                <span className="min-w-0">
                  <span className="block truncate">{option.label}</span>
                  {option.description ? (
                    <span className="mt-0.5 block truncate text-[11px] font-semibold text-slate-400 dark:text-slate-400">
                      {option.description}
                    </span>
                  ) : null}
                </span>
              </button>
            )
          })}
          {statusMessage ? (
            <p className="mx-1 mt-1 border-t border-slate-200 px-2 py-2 text-[11px] font-semibold leading-5 text-slate-500 dark:border-slate-700 dark:text-slate-300">
              {statusMessage}
            </p>
          ) : null}
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
  contextPreviewUsage,
  lastTurnUsage,
  contextInputBlocked = false,
  contextInputBlockThresholdRatio,
  contextUsageLoading = false,
  mainLLMCatalog,
  mainLLMSelection,
  mainLLMLoading = false,
  mainLLMUpdating = false,
  mainLLMError,
  onTextChange,
  onModeChange,
  onNarrativeStyleChange,
  onMainLLMChange,
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
  contextPreviewUsage?: ContextUsageSnapshot | null
  lastTurnUsage?: ContextUsageSnapshot | null
  contextInputBlocked?: boolean
  contextInputBlockThresholdRatio: number
  contextUsageLoading?: boolean
  mainLLMCatalog?: MainLLMProviderCatalog
  mainLLMSelection?: MainLLMSelection
  mainLLMLoading?: boolean
  mainLLMUpdating?: boolean
  mainLLMError?: string | null
  onTextChange: (value: string) => void
  onModeChange: (mode: SessionInputMode) => void
  onNarrativeStyleChange: (styleId: NarrativeStyleId) => void
  onMainLLMChange: (providerKey: string | null) => void
  onSend: () => void
  onStop: () => void
}) {
  const textareaRef = useRef<HTMLTextAreaElement | null>(null)
  const commandInput = isSlashCommandInput(text)
  const contextRejectsCurrentInput = contextInputBlocked && !commandInput
  const handleCommandSelect = (command: string) => {
    onTextChange(command)
    requestAnimationFrame(() => {
      textareaRef.current?.focus()
      textareaRef.current?.setSelectionRange(command.length, command.length)
    })
  }
  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      if (disabled || contextRejectsCurrentInput) return
      if (stopping) return
      if (sending) onStop()
      else onSend()
    }
  }

  const actionDisabled = disabled || stopping || (!sending && contextRejectsCurrentInput)
  const actionStopping = stopping
  const actionSending = sending || stopping
  const narrativeOptions: Array<SelectOption<NarrativeStyleId>> = narrativeStyles.map((style) => ({
    id: style.id,
    label: style.label,
  }))
  const catalogByKey = new Map(
    (mainLLMCatalog?.options ?? []).map((option) => [option.providerKey, option]),
  )
  const sessionProviderKey = mainLLMSelection?.sessionProviderKey ?? null
  const sessionProviderValid = Boolean(sessionProviderKey && catalogByKey.has(sessionProviderKey))
  const inheritedProviderKey = (
    mainLLMSelection?.storyProviderKey && catalogByKey.has(mainLLMSelection.storyProviderKey)
      ? mainLLMSelection.storyProviderKey
      : mainLLMCatalog?.configDefaultProviderKey
  )
  const inheritedProvider = inheritedProviderKey ? catalogByKey.get(inheritedProviderKey) : undefined
  const mainLLMValue = sessionProviderValid && sessionProviderKey
    ? sessionProviderKey
    : INHERIT_MAIN_LLM_OPTION
  const mainLLMOptions: Array<SelectOption<string>> = [
    {
      id: INHERIT_MAIN_LLM_OPTION,
      label: `继承 · ${inheritedProvider?.model ?? '故事/系统默认'}`,
      description: inheritedProvider
        ? `${inheritedProvider.backend} · ${formatContextWindow(inheritedProvider.contextWindow)}`
        : '清除当前会话覆盖',
    },
    ...(mainLLMCatalog?.options ?? []).map((option) => ({
      id: option.providerKey,
      label: option.model,
      description: `${option.backend} · ${formatContextWindow(option.contextWindow)}`,
    })),
  ]
  const invalidOverrides = mainLLMSelection?.invalidOverrides ?? []
  const mainLLMStatus = mainLLMError
    ?? (invalidOverrides.length
      ? `失效覆盖已忽略：${invalidOverrides.map((item) => `${item.source}:${item.providerKey}`).join('、')}`
      : mainLLMSelection
        ? `当前来源：${mainLLMSourceLabel(mainLLMSelection.effectiveSource)}`
        : null)

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
          <CommandPaletteDialog
            sessionId={sessionId}
            disabled={disabled}
            onSelectCommand={handleCommandSelect}
          />
        </div>

        <div className="grid gap-3 px-4 py-3 sm:grid-cols-[minmax(0,1fr)_128px]">
          <textarea
            ref={textareaRef}
            value={text}
            onChange={(event) => onTextChange(event.target.value)}
            onKeyDown={handleKeyDown}
            disabled={disabled}
            className="min-h-24 resize-none border-0 bg-transparent pt-2 text-[length:var(--session-composer-font-size)] leading-[var(--session-composer-line-height)] text-slate-900 outline-none placeholder:text-slate-400 disabled:cursor-not-allowed disabled:text-slate-400 dark:text-slate-100 dark:placeholder:text-slate-500 dark:disabled:text-slate-500"
            placeholder={
              disabled
                ? '请先选择你要扮演的角色'
                : contextInputBlocked
                  ? 'Context 已达到阈值；当前仅允许输入 / 命令'
                  : '输入你的行动、台词或 GM 指令...'
            }
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

        {contextInputBlocked ? (
          <div className="mx-4 mb-3 flex items-start gap-2 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs font-semibold leading-5 text-rose-700 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-200">
            <AlertTriangle size={15} className="mt-0.5 shrink-0" />
            <span>
              下一轮主 Agent Context 已达到 {Math.round(contextInputBlockThresholdRatio * 100)}% 输入阈值。
              普通正文暂不可发送；请手动输入 <code className="font-mono font-black">/compact [压缩轮数] [保留轮数]</code>，
              或切换到更大上下文窗口的 LLM。当前草稿不会被自动清空。
            </span>
          </div>
        ) : null}

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
            <PopupSingleSelect
              label="LLM"
              value={mainLLMValue}
              options={mainLLMOptions}
              onChange={(value) => onMainLLMChange(value === INHERIT_MAIN_LLM_OPTION ? null : value)}
              side="top"
              align="right"
              icon={<Cpu size={14} />}
              disabled={mainLLMLoading || mainLLMUpdating || !mainLLMSelection || !mainLLMCatalog}
              statusMessage={mainLLMUpdating ? '正在切换；当前生成不会被取消。' : mainLLMStatus}
            />
            <SessionContextUsageIndicator
              contextPreviewUsage={contextPreviewUsage}
              lastTurnUsage={lastTurnUsage}
              thresholdRatio={contextInputBlockThresholdRatio}
              previewModel={mainLLMSelection?.effective.model}
              loading={contextUsageLoading}
            />
          </div>
        </div>
      </div>
    </section>
  )
}
