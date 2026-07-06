import { KeyboardEvent } from 'react'
import { Plane, Square } from 'lucide-react'
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

export function SessionComposer({
  sessionId,
  text,
  mode,
  narrativeStyleId,
  narrativeStyles,
  sending,
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
      if (sending) onStop()
      else onSend()
    }
  }

  return (
    <section className="border-t border-slate-200 bg-white px-4 py-4 dark:border-slate-800 dark:bg-slate-950/95 sm:px-6">
      <div className="mx-auto max-w-6xl overflow-visible rounded-lg border border-slate-200 bg-white shadow-sm dark:border-slate-700 dark:bg-slate-900 dark:shadow-black/30">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-4 py-2 dark:border-slate-800">
          <div className="flex rounded-lg bg-slate-100 p-1 dark:bg-slate-800" role="tablist" aria-label="输入模式">
            {inputModes.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => onModeChange(item.id)}
                className={cn(
                  'h-8 min-w-12 rounded-md px-3 text-xs font-black transition',
                  mode === item.id
                    ? 'bg-white text-violet-700 shadow-sm dark:bg-slate-950 dark:text-violet-200 dark:shadow-black/30'
                    : 'text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100',
                )}
              >
                {item.label}
              </button>
            ))}
          </div>
          <CommandPaletteDialog sessionId={sessionId} />
        </div>

        <div className="grid gap-3 px-4 py-3 sm:grid-cols-[minmax(0,1fr)_128px]">
          <textarea
            value={text}
            onChange={(event) => onTextChange(event.target.value)}
            onKeyDown={handleKeyDown}
            disabled={disabled}
            className="min-h-24 resize-none border-0 bg-transparent pt-2 text-base leading-7 text-slate-900 outline-none placeholder:text-slate-400 disabled:cursor-not-allowed disabled:text-slate-400 dark:text-slate-100 dark:placeholder:text-slate-500 dark:disabled:text-slate-500"
            placeholder={disabled ? '请先选择你要扮演的角色' : '输入你的行动、台词或 GM 指令...'}
          />
          <button
            type="button"
            onClick={sending ? onStop : onSend}
            disabled={disabled}
            className={cn(
              'my-1 flex min-h-20 items-center justify-center gap-2 rounded-lg px-5 text-base font-black text-white shadow-lg transition sm:min-h-24',
              disabled ? 'cursor-not-allowed bg-slate-300 shadow-none dark:bg-slate-700' :
              sending
                ? 'bg-rose-500 shadow-rose-100 hover:bg-rose-600 dark:shadow-rose-950/30'
                : 'bg-violet-600 shadow-violet-200 hover:bg-violet-700 dark:shadow-violet-950/40',
            )}
          >
            {sending ? <Square size={16} fill="currentColor" /> : <Plane size={17} fill="currentColor" />}
            {sending ? '停止' : '发送'}
          </button>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3 rounded-b-lg bg-slate-50 px-4 py-2 dark:bg-slate-950/60">
          <div className="flex flex-wrap items-center gap-2" role="radiogroup" aria-label="叙事风格">
            <span className="text-xs font-black text-slate-400 dark:text-slate-300">叙事风格</span>
            {narrativeStyles.map((style) => (
              <label
                key={style.id}
                className={cn(
                  'inline-flex h-8 items-center gap-2 rounded-full border px-3 text-xs font-black transition',
                  narrativeStyleId === style.id
                    ? 'border-violet-200 bg-violet-50 text-violet-700 dark:border-violet-500/50 dark:bg-violet-500/15 dark:text-violet-100'
                    : 'border-slate-200 bg-white text-slate-500 hover:border-violet-200 hover:text-violet-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-400 dark:hover:border-violet-500/60 dark:hover:text-violet-200',
                )}
              >
                <input
                  type="radio"
                  name="narrativeStyle"
                  value={style.id}
                  checked={narrativeStyleId === style.id}
                  onChange={() => onNarrativeStyleChange(style.id)}
                  className="sr-only"
                />
                {style.label}
              </label>
            ))}
          </div>
          <div className="ml-auto flex flex-wrap items-center justify-end gap-3">
            <p className="text-xs font-semibold text-slate-400 dark:text-slate-300">Enter 发送 / Shift+Enter 换行</p>
            <SessionContextUsageIndicator usage={contextUsage} loading={contextUsageLoading} />
          </div>
        </div>
      </div>
    </section>
  )
}
