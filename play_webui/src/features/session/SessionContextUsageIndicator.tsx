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

function formatCacheTokens(usage: ContextUsageSnapshot | null | undefined) {
  if (!usage) return '-'
  if (usage.source !== 'provider_usage' && usage.cachedTokens <= 0) return '-'
  return formatToken(usage.cachedTokens)
}

function formatCacheHitRate(usage: ContextUsageSnapshot | null | undefined) {
  if (!usage || usage.source !== 'provider_usage') return '-'
  const promptTokens = usage.promptTokens ?? usage.usedTokens
  if (!promptTokens || promptTokens <= 0) return '-'
  return formatRatio(usage.cachedTokens / promptTokens)
}

function sourceLabel(usage: ContextUsageSnapshot | null | undefined) {
  if (!usage) return '未知'
  if (usage.source === 'provider_usage') return '准确'
  if (usage.source === 'context_preview') return '估算'
  if (usage.source === 'fallback_estimate') return '兜底'
  return '未知'
}

function titleFor(usage: ContextUsageSnapshot | null | undefined, loading: boolean) {
  if (loading && !usage) return '正在估算 context 用量'
  if (!usage) return '暂无 context 用量'
  if (usage.accuracy === 'accurate') return 'Context 用量已按本轮返回值更新'
  if (usage.status === 'unknown') return '无法获取准确 context 用量'
  if (usage.status === 'danger') return 'Context 即将达到上限'
  if (usage.status === 'warning') return 'Context 接近上限'
  return 'Context 用量估算正常'
}

function detailFor(usage: ContextUsageSnapshot | null | undefined, loading: boolean) {
  if (loading && !usage) return '正在读取 context-preview 估算。'
  if (!usage) return '尚未取得 context-preview 或 provider usage。'
  if (usage.source === 'provider_usage') return '数据来自正常 turn 返回的 provider usage；不会额外请求 usage。'
  if (usage.source === 'context_preview') return '数据来自 context-preview 估算，不等同于 provider 最终 usage。'
  if (usage.source === 'fallback_estimate') return '无法获取完整 context-preview，当前为兜底估算。'
  return usage.errorReason || 'context 上限或 token 估算不可用。'
}

export function SessionContextUsageIndicator({
  usage,
  loading = false,
}: {
  usage?: ContextUsageSnapshot | null
  loading?: boolean
}) {
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement | null>(null)
  const ratio = usage?.ratio ?? null
  const progress = ratio === null ? 0 : Math.min(100, Math.max(0, ratio * 100))
  const ringColor = statusColor[usage?.status ?? 'unknown']
  const ringBackground = usage?.status === 'unknown'
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
        aria-label="查看 context 用量"
        className={cn(
          'relative grid h-11 w-11 place-items-center rounded-full transition focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-violet-200 dark:focus-visible:ring-violet-500/30',
          open ? 'ring-4 ring-violet-100 dark:ring-violet-500/20' : '',
        )}
      >
        <span
          aria-hidden="true"
          className="absolute inset-0 rounded-full"
          style={{ background: ringBackground }}
        />
        <span aria-hidden="true" className="absolute inset-1.5 rounded-full bg-white shadow-inner dark:bg-slate-900" />
        <span className="relative text-[11px] font-black leading-none text-slate-900 dark:text-slate-100">
          {loading && !usage ? '...' : formatRatio(ratio)}
        </span>
      </button>

      {open ? (
        <div
          role="dialog"
          aria-label="Context 用量详情"
          className="absolute bottom-[calc(100%+12px)] right-0 z-30 w-[min(330px,calc(100vw-32px))] rounded-lg border border-slate-200 bg-white p-4 text-left shadow-2xl shadow-slate-900/15 dark:border-slate-700 dark:bg-slate-900 dark:shadow-black/40"
        >
          <div className="flex items-start justify-between gap-3">
            <div>
              <strong className="block text-sm font-black text-slate-950 dark:text-slate-50">{titleFor(usage, loading)}</strong>
              <span className="mt-1 block text-xs font-semibold leading-5 text-slate-500 dark:text-slate-300">{detailFor(usage, loading)}</span>
            </div>
            <span
              className={cn(
                'inline-flex h-6 shrink-0 items-center rounded-full px-2 text-[11px] font-black',
                usage?.source === 'provider_usage'
                  ? 'bg-teal-50 text-teal-700 dark:bg-teal-500/15 dark:text-teal-200'
                  : usage?.status === 'danger'
                    ? 'bg-rose-50 text-rose-700 dark:bg-rose-500/15 dark:text-rose-200'
                    : usage?.status === 'warning'
                      ? 'bg-amber-50 text-amber-700 dark:bg-amber-500/15 dark:text-amber-200'
                      : 'bg-sky-50 text-sky-700 dark:bg-sky-500/15 dark:text-sky-200',
              )}
            >
              {sourceLabel(usage)}
            </span>
          </div>

          <div className="mt-3 h-2 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
            <span className="block h-full rounded-full" style={{ width: `${progress}%`, backgroundColor: ringColor }} />
          </div>

          <div className="mt-3 grid grid-cols-2 gap-2">
            <UsageCell label="当前使用" value={formatToken(usage?.usedTokens)} />
            <UsageCell label="Context 上限" value={formatToken(usage?.contextLimit)} />
            <UsageCell label="使用比例" value={formatRatio(usage?.ratio)} />
            <UsageCell label="更新时间" value={usage?.createdAt ? new Date(usage.createdAt).toLocaleTimeString() : '-'} />
            <UsageCell label="Prompt" value={formatToken(usage?.promptTokens)} />
            <UsageCell label="Completion" value={formatToken(usage?.completionTokens)} />
            <UsageCell label="Cache 命中" value={formatCacheTokens(usage)} />
            <UsageCell label="Cache 命中率" value={formatCacheHitRate(usage)} />
          </div>

          {usage?.model || usage?.finishReason ? (
            <p className="mt-3 text-xs font-semibold leading-5 text-slate-500 dark:text-slate-300">
              {usage.model ? `模型：${usage.model}` : ''}
              {usage.model && usage.finishReason ? ' / ' : ''}
              {usage.finishReason ? `结束：${usage.finishReason}` : ''}
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}

function UsageCell({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 dark:border-slate-700 dark:bg-slate-950/60">
      <span className="block text-[11px] font-bold text-slate-400 dark:text-slate-400">{label}</span>
      <strong className="mt-1 block text-sm font-black text-slate-900 dark:text-slate-100">{value}</strong>
    </div>
  )
}
