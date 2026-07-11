import { useMemo } from 'react'
import {
  BookOpenText,
  ChevronLeft,
  ChevronRight,
  Clock3,
  FileText,
  MapPin,
  Sparkles,
  UsersRound,
  X,
} from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { cn } from '@/lib/utils/cn'
import type { Scene } from '@/types/scene'
import type { SessionSummary } from '@/types/session'
import type { SummaryDetail, SummaryIndex, SummaryPreview } from '@/types/summaries'
import { SessionRailDrawer } from './SessionRailDrawer'
import { formatDateTime } from './sessionRoomHelpers'
import type { SessionRailDrawerState } from './sessionRoomTypes'

function turnRange(summary?: SummaryPreview | null) {
  if (!summary || summary.turnStart === null || summary.turnEnd === null) return 'Turn 范围待关联'
  return summary.turnStart === summary.turnEnd
    ? `Turn ${summary.turnStart}`
    : `Turn ${summary.turnStart}–${summary.turnEnd}`
}

function sessionUpdatedLabel(value?: string | null) {
  const formatted = formatDateTime(value)
  if (!formatted) return '暂无记录'
  const [, time] = formatted.split(' ')
  return time || formatted
}

function SessionSnapshot({
  session,
  scene,
  lastTurnId,
  summaryIndex,
}: {
  session?: SessionSummary
  scene?: Scene | null
  lastTurnId: number
  summaryIndex?: SummaryIndex
}) {
  const batches = summaryIndex?.batches ?? []
  const overall = summaryIndex?.overall
  const coveredBatches = overall?.lastBatchId === null || !overall
    ? 0
    : batches.filter((batch) => (
      batch.batchId !== null && batch.batchId <= (overall.lastBatchId ?? -1)
    )).length
  const progress = batches.length
    ? Math.round((coveredBatches / batches.length) * 100)
    : overall ? 100 : 0
  const coverageLabel = overall
    ? batches.length ? `overall 覆盖 ${coveredBatches}/${batches.length} 批次` : 'overall 已生成'
    : batches.length ? `${batches.length} 个批次 · overall 待生成` : '等待首次自动归纳'

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-3 shadow-sm dark:border-slate-700 dark:bg-slate-900 dark:shadow-black/25" aria-labelledby="session-summary-snapshot-title">
      <div className="flex items-center justify-between gap-3">
        <strong id="session-summary-snapshot-title" className="text-sm font-black text-slate-950 dark:text-slate-100">会话速览</strong>
        <span className="rounded-full bg-teal-50 px-2 py-1 text-[10px] font-black text-teal-700 dark:bg-teal-500/15 dark:text-teal-200">LIVE</span>
      </div>
      <dl className="mt-3 grid grid-cols-2 gap-2">
        <div className="rounded-lg bg-slate-50 px-2.5 py-2 dark:bg-slate-800/70">
          <dt className="text-[10px] font-bold text-slate-400 dark:text-slate-400">当前回合</dt>
          <dd className="mt-1 truncate text-xs font-black text-slate-800 dark:text-slate-100">{lastTurnId > 0 ? `Turn ${lastTurnId}` : '尚未开始'}</dd>
        </div>
        <div className="rounded-lg bg-slate-50 px-2.5 py-2 dark:bg-slate-800/70">
          <dt className="text-[10px] font-bold text-slate-400 dark:text-slate-400">扮演角色</dt>
          <dd className="mt-1 truncate text-xs font-black text-slate-800 dark:text-slate-100">{session?.playerCharacter?.name ?? '尚未绑定'}</dd>
        </div>
        <div className="rounded-lg bg-slate-50 px-2.5 py-2 dark:bg-slate-800/70">
          <dt className="text-[10px] font-bold text-slate-400 dark:text-slate-400">在场角色</dt>
          <dd className="mt-1 truncate text-xs font-black text-slate-800 dark:text-slate-100">{scene?.presentCharacters?.length ?? 0} 位</dd>
        </div>
        <div className="rounded-lg bg-slate-50 px-2.5 py-2 dark:bg-slate-800/70">
          <dt className="text-[10px] font-bold text-slate-400 dark:text-slate-400">最后更新</dt>
          <dd className="mt-1 truncate text-xs font-black text-slate-800 dark:text-slate-100">{sessionUpdatedLabel(session?.updatedAt)}</dd>
        </div>
      </dl>
      <div className="mt-3">
        <div className="flex items-center justify-between gap-2 text-[10px] font-bold text-slate-400 dark:text-slate-400">
          <span>归纳覆盖</span>
          <span className="truncate text-right">{coverageLabel}</span>
        </div>
        <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
          <span className="block h-full rounded-full bg-gradient-to-r from-teal-500 to-cyan-400 transition-all" style={{ width: `${progress}%` }} />
        </div>
      </div>
    </section>
  )
}

function OverallCard({ summary, onOpen }: { summary: SummaryPreview; onOpen: () => void }) {
  return (
    <button
      type="button"
      onClick={onOpen}
      className="w-full rounded-xl border border-teal-200 bg-gradient-to-br from-teal-50 to-cyan-50 px-3 py-3 text-left shadow-sm transition hover:-translate-y-0.5 hover:border-teal-300 hover:shadow-md dark:border-teal-500/30 dark:from-teal-500/10 dark:to-cyan-500/10 dark:hover:border-teal-400/50"
      aria-haspopup="dialog"
    >
      <span className="flex items-center justify-between gap-3 text-[10px] font-black uppercase tracking-[0.08em] text-teal-700 dark:text-teal-200">
        <span>Overall.md</span>
        <span>阅读全文 ›</span>
      </span>
      <strong className="mt-2 block line-clamp-2 text-sm font-black leading-5 text-slate-950 dark:text-slate-100">{summary.title}</strong>
      <span className="mt-2 line-clamp-3 block text-xs font-semibold leading-5 text-slate-500 dark:text-slate-300">{summary.excerpt || '该归纳暂时没有正文。'}</span>
      <span className="mt-2 block font-mono text-[10px] font-black text-teal-700/80 dark:text-teal-300">{turnRange(summary)}</span>
    </button>
  )
}

function BatchCard({ summary, onOpen }: { summary: SummaryPreview; onOpen: () => void }) {
  const metadata = [summary.time, summary.location].filter(Boolean)
  return (
    <button
      type="button"
      onClick={onOpen}
      className="relative w-full overflow-hidden rounded-xl border border-slate-200 bg-white px-3 py-3 pl-4 text-left shadow-sm transition before:absolute before:bottom-3 before:left-0 before:top-3 before:w-[3px] before:rounded-r before:bg-violet-400 hover:-translate-x-0.5 hover:border-violet-200 hover:bg-violet-50/30 dark:border-slate-700 dark:bg-slate-900 dark:hover:border-violet-500/50 dark:hover:bg-violet-500/5"
      aria-haspopup="dialog"
    >
      <span className="flex items-center justify-between gap-2">
        <span className="font-mono text-[10px] font-black text-violet-700 dark:text-violet-300">BATCH {String(summary.batchId ?? 0).padStart(3, '0')}</span>
        <span className="rounded-full bg-slate-100 px-2 py-1 font-mono text-[9px] font-black text-slate-500 dark:bg-slate-800 dark:text-slate-300">{turnRange(summary)}</span>
      </span>
      <strong className="mt-2 block line-clamp-2 text-sm font-black leading-5 text-slate-950 dark:text-slate-100">{summary.title}</strong>
      {metadata.length ? (
        <span className="mt-1.5 flex flex-wrap gap-x-2 gap-y-1 text-[10px] font-bold text-slate-400 dark:text-slate-400">
          {summary.time ? <span className="inline-flex items-center gap-1"><Clock3 size={11} />{summary.time}</span> : null}
          {summary.location ? <span className="inline-flex items-center gap-1"><MapPin size={11} />{summary.location}</span> : null}
        </span>
      ) : null}
      {summary.characters.length ? (
        <span className="mt-1.5 flex items-center gap-1 text-[10px] font-bold text-slate-400 dark:text-slate-400">
          <UsersRound size={11} />
          <span className="truncate">{summary.characters.join('、')}</span>
        </span>
      ) : null}
      <span className="mt-2 line-clamp-3 block text-xs font-semibold leading-5 text-slate-500 dark:text-slate-300">{summary.excerpt || '该批次暂时没有正文。'}</span>
    </button>
  )
}

function MarkdownReader({ detail }: { detail: SummaryDetail }) {
  return (
    <article className="text-sm leading-7 text-slate-700 dark:text-slate-200">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: ({ children }) => <h3 className="mb-3 mt-6 text-xl font-black text-slate-950 first:mt-0 dark:text-slate-100">{children}</h3>,
          h2: ({ children }) => <h3 className="mb-3 mt-6 text-lg font-black text-slate-950 first:mt-0 dark:text-slate-100">{children}</h3>,
          h3: ({ children }) => <h4 className="mb-2 mt-5 text-base font-black text-slate-900 dark:text-slate-100">{children}</h4>,
          p: ({ children }) => (
            <p className="my-3 rounded-lg border border-transparent leading-7">
              {children}
              <span className="mt-2 block w-fit rounded-full bg-slate-100 px-2 py-0.5 font-mono text-[9px] font-black leading-4 text-slate-400 dark:bg-slate-800 dark:text-slate-400">
                Turn 定位预留
              </span>
            </p>
          ),
          ul: ({ children }) => <ul className="my-3 list-disc space-y-1 pl-5 marker:text-violet-500">{children}</ul>,
          ol: ({ children }) => <ol className="my-3 list-decimal space-y-1 pl-5 marker:font-black marker:text-violet-500">{children}</ol>,
          blockquote: ({ children }) => <blockquote className="my-4 border-l-4 border-violet-300 bg-violet-50/60 px-4 py-2 text-slate-600 dark:border-violet-500/50 dark:bg-violet-500/10 dark:text-slate-300">{children}</blockquote>,
          a: ({ children, href }) => <a href={href} target="_blank" rel="noreferrer" className="font-bold text-violet-700 underline decoration-violet-300 underline-offset-2 dark:text-violet-300">{children}</a>,
          code: ({ children }) => <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[0.9em] text-violet-700 dark:bg-slate-800 dark:text-violet-300">{children}</code>,
          pre: ({ children }) => <pre className="my-4 overflow-x-auto rounded-xl bg-slate-950 p-4 text-xs leading-6 text-slate-100">{children}</pre>,
          table: ({ children }) => <div className="my-4 overflow-x-auto"><table className="min-w-full border-collapse text-xs">{children}</table></div>,
          th: ({ children }) => <th className="border border-slate-200 bg-slate-50 px-2 py-2 text-left font-black dark:border-slate-700 dark:bg-slate-800">{children}</th>,
          td: ({ children }) => <td className="border border-slate-200 px-2 py-2 align-top dark:border-slate-700">{children}</td>,
          hr: () => <hr className="my-6 border-slate-200 dark:border-slate-700" />,
          img: ({ alt }) => (
            <span className="my-3 block rounded-lg border border-dashed border-slate-300 bg-slate-50 px-3 py-4 text-center text-xs font-semibold text-slate-400 dark:border-slate-700 dark:bg-slate-800/70 dark:text-slate-400">
              图片未在摘要栏中加载{alt ? `：${alt}` : ''}
            </span>
          ),
        }}
      >
        {detail.markdown}
      </ReactMarkdown>
    </article>
  )
}

export function SessionRightRail({
  session,
  scene,
  lastTurnId,
  summaryIndex,
  summariesLoading,
  summariesError,
  summaryDetail,
  summaryDetailLoading,
  summaryDetailError,
  collapsed,
  mobileOpen,
  activeDrawer,
  onCloseMobile,
  onToggleCollapsed,
  onOpenDrawer,
  onCloseDrawer,
}: {
  session?: SessionSummary
  scene?: Scene | null
  lastTurnId: number
  summaryIndex?: SummaryIndex
  summariesLoading: boolean
  summariesError: boolean
  summaryDetail?: SummaryDetail
  summaryDetailLoading: boolean
  summaryDetailError: boolean
  collapsed: boolean
  mobileOpen: boolean
  activeDrawer: SessionRailDrawerState
  onCloseMobile: () => void
  onToggleCollapsed: () => void
  onOpenDrawer: (drawer: Exclude<SessionRailDrawerState, null>) => void
  onCloseDrawer: () => void
}) {
  const overall = summaryIndex?.overall ?? null
  const batches = useMemo(
    () => [...(summaryIndex?.batches ?? [])].sort((first, second) => (
      (second.batchId ?? -1) - (first.batchId ?? -1)
    )),
    [summaryIndex?.batches],
  )
  const activeSummaryKey = activeDrawer?.kind === 'summary'
    ? activeDrawer.summaryKey
    : null
  const activePreview = activeSummaryKey === 'overall'
    ? overall
    : batches.find((batch) => String(batch.batchId) === activeSummaryKey) ?? null
  const fallbackSummaryKey = overall
    ? 'overall'
    : batches[0]?.batchId !== null && batches[0]?.batchId !== undefined
      ? String(batches[0].batchId)
      : null

  return (
    <>
      <aside
        aria-label="会话速览与故事归纳侧栏"
        className={cn(
          'fixed inset-y-0 right-0 z-40 flex w-[min(360px,88vw)] flex-col border-l border-slate-200 bg-white/95 shadow-2xl shadow-slate-950/10 backdrop-blur transition-transform dark:border-slate-800 dark:bg-slate-950/95 dark:shadow-black/40 lg:static lg:z-auto lg:h-screen lg:w-auto lg:translate-x-0 lg:shadow-none',
          mobileOpen ? 'translate-x-0' : 'translate-x-full',
          collapsed ? 'lg:px-3' : '',
        )}
      >
        <header className={cn('flex h-[73px] shrink-0 items-center justify-between gap-3 border-b border-slate-200 px-5 dark:border-slate-800', collapsed ? 'lg:justify-center lg:px-0' : '')}>
          <div className="flex min-w-0 items-center gap-3">
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-teal-500 to-cyan-700 text-white shadow-lg shadow-teal-100 dark:shadow-teal-950/40">
              <BookOpenText size={19} />
            </span>
            <span className={cn('min-w-0 leading-tight', collapsed ? 'lg:hidden' : '')}>
              <strong className="block truncate text-sm font-black text-slate-950 dark:text-slate-100">故事归纳</strong>
              <span className="block truncate text-xs font-semibold text-slate-400 dark:text-slate-300">overall &amp; batch summaries</span>
            </span>
          </div>
          <div className={cn('flex items-center gap-2', collapsed ? 'lg:hidden' : '')}>
            <button
              type="button"
              onClick={onToggleCollapsed}
              className="hidden h-9 w-9 items-center justify-center rounded-lg border border-slate-200 text-slate-500 transition hover:border-violet-200 hover:bg-violet-50 hover:text-violet-700 dark:border-slate-700 dark:text-slate-300 dark:hover:border-violet-500/60 dark:hover:bg-violet-500/10 dark:hover:text-violet-200 lg:flex"
              aria-label="收起右侧栏"
              title="收起右侧栏"
            >
              <ChevronRight size={17} />
            </button>
            <button
              type="button"
              onClick={onCloseMobile}
              className="flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200 text-slate-500 transition hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800 lg:hidden"
              aria-label="关闭会话速览与故事归纳栏"
            >
              <X size={17} />
            </button>
          </div>
        </header>

        {collapsed ? (
          <div className="hidden min-h-0 flex-1 flex-col items-center gap-4 overflow-y-auto py-4 lg:flex">
            <button
              type="button"
              onClick={onToggleCollapsed}
              className="flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200 text-slate-500 transition hover:border-violet-200 hover:bg-violet-50 hover:text-violet-700 dark:border-slate-700 dark:text-slate-300"
              aria-label="展开右侧栏"
              title="展开右侧栏"
            >
              <ChevronLeft size={17} />
            </button>
            <button
              type="button"
              disabled={!fallbackSummaryKey}
              onClick={() => {
                if (fallbackSummaryKey) onOpenDrawer({ kind: 'summary', summaryKey: fallbackSummaryKey })
              }}
              className="flex h-11 w-11 items-center justify-center rounded-full bg-teal-50 text-xs font-black text-teal-700 ring-4 ring-teal-100 transition disabled:cursor-default disabled:opacity-50 dark:bg-teal-500/15 dark:text-teal-200 dark:ring-teal-500/20"
              aria-label="阅读故事归纳"
              aria-haspopup="dialog"
              title="故事归纳"
            >
              归
            </button>
          </div>
        ) : null}

        <div className={cn('flex min-h-0 flex-1 flex-col gap-4 px-5 py-5', collapsed ? 'lg:hidden' : '')}>
          <SessionSnapshot session={session} scene={scene} lastTurnId={lastTurnId} summaryIndex={summaryIndex} />

          {summariesLoading ? <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50 px-4 py-6 text-center text-sm font-semibold text-slate-400 dark:border-slate-700 dark:bg-slate-800/70 dark:text-slate-300">正在加载故事归纳</div> : null}
          {summariesError ? <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-4 text-sm font-semibold text-rose-700 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-200">故事归纳暂时无法读取，请稍后刷新。</div> : null}

          {!summariesLoading && !summariesError && overall ? (
            <OverallCard summary={overall} onOpen={() => onOpenDrawer({ kind: 'summary', summaryKey: 'overall' })} />
          ) : null}
          {!summariesLoading && !summariesError && !overall && batches.length ? (
            <div className="rounded-xl border border-dashed border-teal-200 bg-teal-50/60 px-3 py-3 text-xs font-semibold leading-5 text-teal-800 dark:border-teal-500/30 dark:bg-teal-500/10 dark:text-teal-200">
              已有分段摘要仍可阅读；下一次整体归纳成功后，overall.md 会出现在这里。
            </div>
          ) : null}

          {!summariesLoading && !summariesError && !overall && !batches.length ? (
            <div className="flex min-h-0 flex-1 items-center justify-center">
              <div className="w-full rounded-xl border border-dashed border-slate-300 bg-slate-50 px-4 py-7 text-center dark:border-slate-700 dark:bg-slate-800/70">
                <span className="mx-auto flex h-11 w-11 items-center justify-center rounded-xl bg-teal-50 text-teal-700 dark:bg-teal-500/15 dark:text-teal-200"><Sparkles size={18} /></span>
                <h3 className="mt-3 text-sm font-black text-slate-900 dark:text-slate-100">归纳尚未生成</h3>
                <p className="mt-2 text-xs font-semibold leading-5 text-slate-500 dark:text-slate-300">
                  会话积累到归纳阈值后，整体与分段摘要会自动出现在这里。
                </p>
              </div>
            </div>
          ) : null}

          {!summariesLoading && !summariesError && batches.length ? (
            <section className="flex min-h-0 flex-1 flex-col" aria-labelledby="session-batch-summaries-title">
              <div className="mb-2 flex shrink-0 items-center justify-between gap-3 px-0.5">
                <span className="flex items-center gap-2">
                  <FileText size={14} className="text-violet-600 dark:text-violet-300" />
                  <strong id="session-batch-summaries-title" className="text-sm font-black text-slate-950 dark:text-slate-100">分段摘要</strong>
                </span>
                <span className="text-[10px] font-black text-slate-400 dark:text-slate-400">新 → 旧 · {batches.length}</span>
              </div>
              <div className="min-h-0 flex-1 space-y-2 overflow-y-auto overscroll-contain pr-1">
                {batches.map((batch) => (
                  <BatchCard
                    key={batch.batchId}
                    summary={batch}
                    onOpen={() => onOpenDrawer({ kind: 'summary', summaryKey: String(batch.batchId) })}
                  />
                ))}
              </div>
            </section>
          ) : null}
        </div>
      </aside>

      <SessionRailDrawer
        open={activeSummaryKey !== null}
        side="right"
        eyebrow={activePreview?.kind === 'overall' ? 'Overall.md' : `Batch ${String(activePreview?.batchId ?? '').padStart(3, '0')}`}
        title={summaryDetail?.title ?? activePreview?.title ?? '故事归纳'}
        description="Markdown 全文只在打开时读取；Turn 标签为后续时间线导航预留。"
        meta={activePreview ? (
          <div className="flex flex-wrap gap-1.5 text-[10px] font-black text-slate-500 dark:text-slate-300">
            <span className="rounded-full bg-white px-2 py-1 dark:bg-slate-800">{turnRange(activePreview)} · 导航预留</span>
            {activePreview.time ? <span className="rounded-full bg-white px-2 py-1 dark:bg-slate-800">{activePreview.time}</span> : null}
            {activePreview.location ? <span className="rounded-full bg-white px-2 py-1 dark:bg-slate-800">{activePreview.location}</span> : null}
          </div>
        ) : null}
        onClose={onCloseDrawer}
      >
        {summaryDetailLoading ? <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50 px-4 py-8 text-center text-sm font-semibold text-slate-400 dark:border-slate-700 dark:bg-slate-800/70 dark:text-slate-300">正在读取 Markdown 全文</div> : null}
        {summaryDetailError ? <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-4 text-sm font-semibold text-rose-700 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-200">该摘要全文暂时无法读取。</div> : null}
        {!summaryDetailLoading && !summaryDetailError && summaryDetail ? <MarkdownReader detail={summaryDetail} /> : null}
      </SessionRailDrawer>
    </>
  )
}
