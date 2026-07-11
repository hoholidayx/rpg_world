'use client'

import { cn } from '@/lib/utils/cn'
import {
  NARRATIVE_OUTCOME_CODES,
  narrativeOutcomeWeightTotal,
  type NarrativeOutcomeDefinition,
  type NarrativeOutcomeWeights,
} from '@/types/narrativeOutcome'

const FALLBACK_LABELS: Record<(typeof NARRATIVE_OUTCOME_CODES)[number], string> = {
  critical_success: '大成功',
  success: '成功',
  success_with_cost: '成功但有代价',
  setback: '失败但推进',
  critical_failure: '重大失败',
}

export function NarrativeOutcomeWeightsEditor({
  value,
  definitions,
  disabled = false,
  onChange,
}: {
  value: NarrativeOutcomeWeights
  definitions?: NarrativeOutcomeDefinition[]
  disabled?: boolean
  onChange: (weights: NarrativeOutcomeWeights) => void
}) {
  const total = narrativeOutcomeWeightTotal(value)
  const labelByCode = new Map(definitions?.map((definition) => [definition.code, definition.label]))

  return (
    <div className="space-y-3">
      <div className="grid gap-2 sm:grid-cols-5">
        {NARRATIVE_OUTCOME_CODES.map((code) => {
          const valid = Number.isInteger(value[code]) && value[code] >= 0 && value[code] <= 100
          return (
            <label key={code} className="min-w-0 rounded-lg border border-slate-200 bg-slate-50 px-3 py-3 dark:border-slate-700 dark:bg-slate-900">
              <span className="block truncate text-xs font-black text-slate-600 dark:text-slate-300">
                {labelByCode.get(code) ?? FALLBACK_LABELS[code]}
              </span>
              <span className="mt-2 flex items-center gap-1.5">
                <input
                  type="number"
                  min={0}
                  max={100}
                  step={1}
                  inputMode="numeric"
                  value={value[code]}
                  disabled={disabled}
                  onChange={(event) => {
                    const next = event.target.valueAsNumber
                    onChange({
                      ...value,
                      [code]: Number.isFinite(next) ? next : 0,
                    })
                  }}
                  className={cn(
                    'h-10 min-w-0 w-full rounded-lg border bg-white px-2 text-center text-base font-black outline-none transition focus:ring-4 disabled:cursor-not-allowed disabled:opacity-60 dark:bg-slate-950 dark:text-slate-100',
                    valid
                      ? 'border-slate-200 focus:border-violet-300 focus:ring-violet-100 dark:border-slate-700 dark:focus:ring-violet-500/15'
                      : 'border-rose-300 text-rose-700 focus:border-rose-400 focus:ring-rose-100',
                  )}
                />
                <span className="text-xs font-black text-slate-400">%</span>
              </span>
            </label>
          )
        })}
      </div>
      <div className={cn(
        'flex items-center justify-between rounded-lg border px-3 py-2 text-xs font-bold',
        total === 100
          ? 'border-teal-200 bg-teal-50 text-teal-700 dark:border-teal-500/30 dark:bg-teal-500/10 dark:text-teal-200'
          : 'border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-200',
      )}>
        <span>五档合计</span>
        <strong className="text-sm">{total}% / 100%</strong>
      </div>
    </div>
  )
}
