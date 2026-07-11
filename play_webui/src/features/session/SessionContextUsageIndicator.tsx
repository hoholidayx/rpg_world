import { useEffect, useRef, useState } from 'react'
import { cn } from '@/lib/utils/cn'
import type { ContextUsageSnapshot } from '@/types/contextUsage'

const statusColor: Record<ContextUsageSnapshot['status'], string> = {
  normal: '#0f766e',
  warning: '#b45309',
  danger: '#be123c',
  unknown: '#64748b',
}

function formatToken(value: number | null | undefined) {
  if (value === null || value === undefined) return '-'
  const rounded = Math.round(value)
  if (rounded >= 1_000_000) return `${formatCompactNumber(rounded / 1_000_000)}M`
  if (rounded >= 1_000) return `${formatCompactNumber(rounded / 1_000)}K`
  return rounded.toLocaleString()
}

function formatCompactNumber(value: number) {
  const fixed = value >= 10 ? value.toFixed(1) : value.toFixed(2)
  return fixed.replace(/\.0+$|(\.\d*[1-9])0+$/, '$1')
}

function formatRatio(value: number | null | undefined) {
  if (value === null || value === undefined) return '?'
  return `${Math.round(value * 100)}%`
}

function formatCacheHitRate(usage: ContextUsageSnapshot | null | undefined) {
  if (!usage || usage.source !== 'provider_usage') return '-'
  const promptTokens = usage.promptTokens ?? usage.usedTokens
  if (!promptTokens || promptTokens <= 0) return '-'
  return formatRatio(usage.cachedTokens / promptTokens)
}

function previewSourceLabel(usage: ContextUsageSnapshot | null | undefined) {
  if (!usage) return '未知'
  if (usage.source === 'fallback_estimate') return '兜底估算'
  if (usage.source === 'unavailable') return '不可用'
  return 'context-preview'
}

function previewTitle(usage: ContextUsageSnapshot | null | undefined, loading: boolean) {
  if (loading && !usage) return '正在估算下一轮主 Agent Context'
  if (!usage || usage.status === 'unknown') return '下一轮主 Agent Context 暂不可估算'
  if (usage.status === 'danger') return '下一轮主 Agent Context 已达到输入阈值'
  if (usage.status === 'warning') return '下一轮主 Agent Context 接近输入阈值'
  return '下一轮主 Agent Context 估算正常'
}

export function SessionContextUsageIndicator({
  contextPreviewUsage,
  lastTurnUsage,
  thresholdRatio,
  previewModel,
  loading = false,
}: {
  contextPreviewUsage?: ContextUsageSnapshot | null
  lastTurnUsage?: ContextUsageSnapshot | null
  thresholdRatio: number
  previewModel?: string | null
  loading?: boolean
}) {
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement | null>(null)
  const ratio = contextPreviewUsage?.ratio ?? null
  const progress = ratio === null ? 0 : Math.min(100, Math.max(0, ratio * 100))
  const ringColor = statusColor[contextPreviewUsage?.status ?? 'unknown']
  const ringBackground = contextPreviewUsage?.status === 'unknown' || !contextPreviewUsage
    ? `repeating-conic-gradient(${ringColor} 0deg 12deg, #e2e8f0 12deg 24deg)`
    : `conic-gradient(${ringColor} ${progress * 3.6}deg, #e2e8f0 0deg)`

  useEffect(() => {
    if (!open) return
    const handlePointerDown = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false)
    }
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', handlePointerDown)
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('mousedown', handlePointerDown)
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [open])

  return (
    <div ref={rootRef} className="relative inline-flex items-center">
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        aria-expanded={open}
        aria-label="查看 context-preview 与上一轮真实 usage"
        className={cn(
          'relative grid h-11 w-11 place-items-center rounded-full transition focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-violet-200 dark:focus-visible:ring-violet-500/30',
          open ? 'ring-4 ring-violet-100 dark:ring-violet-500/20' : '',
        )}
      >
        <span aria-hidden="true" className="absolute inset-0 rounded-full" style={{ background: ringBackground }} />
        <span aria-hidden="true" className="absolute inset-1.5 rounded-full bg-white shadow-inner dark:bg-slate-900" />
        <span className="relative text-[11px] font-black leading-none text-slate-900 dark:text-slate-100">
          {loading && !contextPreviewUsage ? '...' : formatRatio(ratio)}
        </span>
      </button>

      {open ? (
        <div
          role="dialog"
          aria-label="context-preview 与上一轮真实 usage 详情"
          className="absolute bottom-[calc(100%+12px)] right-0 z-30 w-[min(380px,calc(100vw-32px))] rounded-lg border border-slate-200 bg-white p-4 text-left shadow-2xl shadow-slate-900/15 dark:border-slate-700 dark:bg-slate-900 dark:shadow-black/40"
        >
          <section>
            <div className="flex items-start justify-between gap-3">
              <div>
                <strong className="block text-sm font-black text-slate-950 dark:text-slate-50">
                  {previewTitle(contextPreviewUsage, loading)}
                </strong>
                <span className="mt-1 block text-xs font-semibold leading-5 text-slate-500 dark:text-slate-300">
                  圆环始终来自 context-preview，不包含本次尚未发送的 input，也不使用上一轮真实 usage 覆盖。
                </span>
              </div>
              <span className={cn(
                'inline-flex h-6 shrink-0 items-center rounded-full px-2 text-[11px] font-black',
                contextPreviewUsage?.status === 'danger'
                  ? 'bg-rose-50 text-rose-700 dark:bg-rose-500/15 dark:text-rose-200'
                  : contextPreviewUsage?.status === 'warning'
                    ? 'bg-amber-50 text-amber-700 dark:bg-amber-500/15 dark:text-amber-200'
                    : 'bg-sky-50 text-sky-700 dark:bg-sky-500/15 dark:text-sky-200',
              )}>
                {previewSourceLabel(contextPreviewUsage)}
              </span>
            </div>

            <div className="mt-3 h-2 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
              <span className="block h-full rounded-full" style={{ width: `${progress}%`, backgroundColor: ringColor }} />
            </div>

            <div className="mt-3 grid grid-cols-2 gap-2">
              <UsageCell label="Context 估算" value={formatToken(contextPreviewUsage?.usedTokens)} />
              <UsageCell label="模型窗口" value={formatToken(contextPreviewUsage?.contextLimit)} />
              <UsageCell label="窗口占比" value={formatRatio(contextPreviewUsage?.ratio)} />
              <UsageCell label="输入阈值" value={formatRatio(thresholdRatio)} />
              <UsageCell label="估算精度" value={contextPreviewUsage?.accuracy ?? '-'} />
              <UsageCell label="模型" value={previewModel || contextPreviewUsage?.model || '-'} />
              <UsageCell
                label="更新时间"
                value={contextPreviewUsage?.createdAt ? new Date(contextPreviewUsage.createdAt).toLocaleTimeString() : '-'}
              />
            </div>
            {contextPreviewUsage?.errorReason ? (
              <p className="mt-2 text-xs font-semibold leading-5 text-amber-700 dark:text-amber-200">
                估算降级：{contextPreviewUsage.errorReason}
              </p>
            ) : null}
          </section>

          <section className="mt-4 border-t border-slate-200 pt-4 dark:border-slate-700">
            <strong className="block text-sm font-black text-slate-950 dark:text-slate-50">上一轮真实 turn usage</strong>
            <p className="mt-1 text-xs font-semibold leading-5 text-slate-500 dark:text-slate-300">
              仅来自 provider 完成事件，用于回合复盘，不参与下一轮 Context 门禁。
            </p>
            {lastTurnUsage?.source === 'provider_usage' ? (
              <>
                <div className="mt-3 grid grid-cols-2 gap-2">
                  <UsageCell label="Prompt" value={formatToken(lastTurnUsage.promptTokens ?? lastTurnUsage.usedTokens)} />
                  <UsageCell label="Completion" value={formatToken(lastTurnUsage.completionTokens)} />
                  <UsageCell label="Total" value={formatToken(lastTurnUsage.totalTokens)} />
                  <UsageCell label="Cache 命中" value={formatToken(lastTurnUsage.cachedTokens)} />
                  <UsageCell label="Cache 命中率" value={formatCacheHitRate(lastTurnUsage)} />
                  <UsageCell label="模型" value={lastTurnUsage.model || '-'} />
                  <UsageCell label="结束原因" value={lastTurnUsage.finishReason || '-'} />
                  <UsageCell
                    label="耗时"
                    value={lastTurnUsage.durationMs === null || lastTurnUsage.durationMs === undefined
                      ? '-'
                      : `${Math.round(lastTurnUsage.durationMs)} ms`}
                  />
                  <UsageCell label="来源" value="provider usage" />
                  <UsageCell
                    label="更新时间"
                    value={lastTurnUsage.createdAt ? new Date(lastTurnUsage.createdAt).toLocaleTimeString() : '-'}
                  />
                </div>
              </>
            ) : (
              <p className="mt-3 rounded-lg border border-dashed border-slate-200 px-3 py-3 text-xs font-semibold text-slate-400 dark:border-slate-700 dark:text-slate-400">
                当前页面尚未收到可用的 provider usage；不会用 context-preview 代替。
              </p>
            )}
          </section>
        </div>
      ) : null}
    </div>
  )
}

function UsageCell({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 dark:border-slate-700 dark:bg-slate-950/60">
      <span className="block text-[11px] font-bold text-slate-400 dark:text-slate-400">{label}</span>
      <strong className="mt-1 block truncate text-sm font-black text-slate-900 dark:text-slate-100" title={value}>{value}</strong>
    </div>
  )
}
