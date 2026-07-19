'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { useInfiniteQuery, useQuery } from '@tanstack/react-query'
import {
  BookOpenText,
  BrainCircuit,
  CheckCircle2,
  Clock3,
  Database,
  ExternalLink,
  FileText,
  Filter,
  History,
  MapPin,
  RefreshCw,
  ShieldAlert,
  Sparkles,
  UsersRound,
} from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import {
  DREAM_MEMORY_KINDS,
  DREAM_MEMORY_LIFECYCLES,
  type DreamMemory,
  type DreamMemoryKind,
  type DreamMemoryLifecycle,
} from '@/types/dream'
import type { StoryMemoryItem } from '@/types/storyMemory'
import type { SummaryDetail, SummaryPreview } from '@/types/summaries'
import { listDreamMemories } from '@/lib/api/dream'
import { listSessionStoryMemories } from '@/lib/api/storyMemory'
import { getSessionSummary, listSessionSummaries } from '@/lib/api/summaries'
import { cn } from '@/lib/utils/cn'
import {
  DREAM_EPISTEMIC_LABELS,
  DREAM_KIND_LABELS,
  DREAM_LIFECYCLE_LABELS,
} from '@/features/dream/dreamLabels'
import { SessionWorkspacePanel } from './SessionWorkspacePanel'
import {
  EvidenceReferenceButton,
  SessionTurnEvidencePreview,
  type SessionEvidenceReference,
} from './SessionTurnEvidencePreview'
import { formatDateTime } from './sessionRoomHelpers'

export type SessionStoryTab = 'summaries' | 'storyMemory' | 'persistentMemory'
type DreamCheckpointFilter = 'all' | 'pending' | 'processed'
type MemoryKindFilter = 'all' | DreamMemoryKind
type LifecycleFilter = 'all' | DreamMemoryLifecycle

function turnRange(summary?: SummaryPreview | null) {
  if (!summary || summary.turnStart === null || summary.turnEnd === null) return 'Turn 范围待关联'
  return summary.turnStart === summary.turnEnd
    ? `Turn ${summary.turnStart}`
    : `Turn ${summary.turnStart}–${summary.turnEnd}`
}

function storyMemoryTurnRange(memory: StoryMemoryItem) {
  return memory.sourceTurnStart === memory.sourceTurnEnd
    ? `Turn ${memory.sourceTurnStart}`
    : `Turn ${memory.sourceTurnStart}–${memory.sourceTurnEnd}`
}

function summaryKey(summary: SummaryPreview) {
  return summary.kind === 'overall' ? 'overall' : String(summary.batchId)
}

function EmptyState({ icon, title, description }: { icon: React.ReactNode; title: string; description: string }) {
  return (
    <div className="flex min-h-64 items-center justify-center rounded-2xl border border-dashed border-slate-300 bg-white/70 px-6 py-12 text-center dark:border-slate-700 dark:bg-slate-900/70">
      <div className="max-w-md">
        <span className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-violet-100 text-violet-700 dark:bg-violet-500/15 dark:text-violet-200">{icon}</span>
        <h3 className="mt-4 text-base font-black text-slate-950 dark:text-slate-100">{title}</h3>
        <p className="mt-2 text-sm font-semibold leading-6 text-slate-500 dark:text-slate-300">{description}</p>
      </div>
    </div>
  )
}

function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="rounded-2xl border border-rose-200 bg-rose-50 px-5 py-6 text-center dark:border-rose-500/30 dark:bg-rose-500/10">
      <p className="text-sm font-bold text-rose-700 dark:text-rose-200">{message}</p>
      <button type="button" onClick={onRetry} className="mt-3 inline-flex h-9 items-center gap-2 rounded-lg bg-rose-600 px-3 text-xs font-black text-white">
        <RefreshCw size={14} /> 重试
      </button>
    </div>
  )
}

function RefreshButton({ loading, onClick }: { loading: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={loading}
      className="inline-flex h-10 items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 text-xs font-black text-slate-600 transition hover:border-violet-200 hover:text-violet-700 disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300"
    >
      <RefreshCw size={14} className={loading ? 'animate-spin' : ''} /> 手动刷新
    </button>
  )
}

function MarkdownReader({ detail }: { detail: SummaryDetail }) {
  return (
    <article className="text-sm leading-7 text-slate-700 dark:text-slate-200">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: ({ children }) => <h2 className="mb-4 mt-7 text-2xl font-black text-slate-950 first:mt-0 dark:text-slate-100">{children}</h2>,
          h2: ({ children }) => <h3 className="mb-3 mt-7 text-xl font-black text-slate-950 first:mt-0 dark:text-slate-100">{children}</h3>,
          h3: ({ children }) => <h4 className="mb-2 mt-6 text-lg font-black text-slate-900 dark:text-slate-100">{children}</h4>,
          p: ({ children }) => <p className="my-4 whitespace-pre-wrap leading-8">{children}</p>,
          ul: ({ children }) => <ul className="my-4 list-disc space-y-2 pl-6 marker:text-violet-500">{children}</ul>,
          ol: ({ children }) => <ol className="my-4 list-decimal space-y-2 pl-6 marker:font-black marker:text-violet-500">{children}</ol>,
          blockquote: ({ children }) => <blockquote className="my-5 border-l-4 border-violet-300 bg-violet-50/60 px-5 py-3 text-slate-600 dark:border-violet-500/50 dark:bg-violet-500/10 dark:text-slate-300">{children}</blockquote>,
          a: ({ children, href }) => <a href={href} target="_blank" rel="noreferrer" className="font-bold text-violet-700 underline decoration-violet-300 underline-offset-2 dark:text-violet-300">{children}</a>,
          code: ({ children }) => <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[0.9em] text-violet-700 dark:bg-slate-800 dark:text-violet-300">{children}</code>,
          pre: ({ children }) => <pre className="my-5 overflow-x-auto rounded-xl bg-slate-950 p-4 text-xs leading-6 text-slate-100">{children}</pre>,
          table: ({ children }) => <div className="my-5 overflow-x-auto"><table className="min-w-full border-collapse text-xs">{children}</table></div>,
          th: ({ children }) => <th className="border border-slate-200 bg-slate-50 px-3 py-2 text-left font-black dark:border-slate-700 dark:bg-slate-800">{children}</th>,
          td: ({ children }) => <td className="border border-slate-200 px-3 py-2 align-top dark:border-slate-700">{children}</td>,
        }}
      >
        {detail.markdown}
      </ReactMarkdown>
    </article>
  )
}

function SummaryListItem({ summary, selected, onClick }: { summary: SummaryPreview; selected: boolean; onClick: () => void }) {
  const metadata = [summary.time, summary.location].filter(Boolean)
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'w-full rounded-xl border px-4 py-3 text-left transition',
        selected
          ? 'border-violet-300 bg-violet-50 shadow-sm dark:border-violet-500/50 dark:bg-violet-500/15'
          : 'border-slate-200 bg-white hover:border-violet-200 hover:bg-violet-50/40 dark:border-slate-800 dark:bg-slate-950 dark:hover:border-violet-500/40',
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-[10px] font-black uppercase tracking-[0.08em] text-violet-700 dark:text-violet-300">
          {summary.kind === 'overall' ? '整体归纳' : '归纳批次'}
        </span>
        <span className="rounded-full bg-slate-100 px-2 py-1 text-[10px] font-black text-slate-500 dark:bg-slate-800 dark:text-slate-300">{turnRange(summary)}</span>
      </div>
      <strong className="mt-2 block line-clamp-2 text-sm font-black text-slate-950 dark:text-slate-100">{summary.title}</strong>
      {metadata.length ? <span className="mt-2 block truncate text-[11px] font-semibold text-slate-400">{metadata.join(' · ')}</span> : null}
      <span className="mt-2 line-clamp-2 block text-xs font-semibold leading-5 text-slate-500 dark:text-slate-300">{summary.excerpt || '暂无预览正文'}</span>
    </button>
  )
}

function SummariesView({ sessionId, enabled }: { sessionId: string; enabled: boolean }) {
  const [selectedKey, setSelectedKey] = useState<string | null>(null)
  const indexQuery = useQuery({
    queryKey: ['play-session-summaries', sessionId],
    queryFn: () => listSessionSummaries(sessionId),
    enabled,
    retry: false,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  })
  const summaries = useMemo(() => {
    const data = indexQuery.data
    return data ? [...(data.overall ? [data.overall] : []), ...data.batches] : []
  }, [indexQuery.data])

  useEffect(() => {
    setSelectedKey(null)
  }, [sessionId])

  useEffect(() => {
    if (!summaries.length) {
      setSelectedKey(null)
      return
    }
    if (!selectedKey || !summaries.some((summary) => summaryKey(summary) === selectedKey)) {
      setSelectedKey(summaryKey(summaries[0]))
    }
  }, [selectedKey, summaries])

  const selectedPreview = summaries.find((summary) => summaryKey(summary) === selectedKey) ?? null
  const detailQuery = useQuery({
    queryKey: ['play-session-summary', sessionId, selectedKey],
    queryFn: () => getSessionSummary(sessionId, selectedKey ?? ''),
    enabled: enabled && selectedKey !== null,
    retry: false,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  })
  const refreshing = indexQuery.isFetching || detailQuery.isFetching

  if (indexQuery.isLoading) return <EmptyState icon={<RefreshCw size={20} className="animate-spin" />} title="正在读取故事归纳" description="归纳索引加载完成后可按 Turn 范围浏览。" />
  if (indexQuery.isError) return <ErrorState message="故事归纳暂时无法读取。" onRetry={() => { void indexQuery.refetch() }} />
  if (!summaries.length) return <EmptyState icon={<Sparkles size={20} />} title="尚无故事归纳" description="归纳生成后会按来源 Turn 范围出现在这里；这里不使用章节或支线概念。" />

  return (
    <div className="grid min-h-[560px] gap-4 lg:grid-cols-[340px_minmax(0,1fr)]">
      <section className="flex min-h-0 flex-col overflow-hidden rounded-2xl border border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-900">
        <header className="flex items-center justify-between gap-3 border-b border-slate-200 px-4 py-3 dark:border-slate-800">
          <div>
            <h3 className="text-sm font-black text-slate-950 dark:text-slate-100">归纳索引</h3>
            <p className="mt-1 text-[11px] font-semibold text-slate-400">新 → 旧 · {summaries.length} 项</p>
          </div>
          <RefreshButton loading={refreshing} onClick={() => { void indexQuery.refetch(); if (selectedKey) void detailQuery.refetch() }} />
        </header>
        <div className="grid gap-2 p-3 lg:max-h-[calc(100vh-270px)] lg:overflow-y-auto">
          {summaries.map((summary) => (
            <SummaryListItem key={summaryKey(summary)} summary={summary} selected={summaryKey(summary) === selectedKey} onClick={() => setSelectedKey(summaryKey(summary))} />
          ))}
        </div>
      </section>
      <article className="min-h-[420px] rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-950 sm:p-7">
        {selectedPreview ? (
          <header className="mb-6 border-b border-slate-100 pb-5 dark:border-slate-800">
            <span className="text-[10px] font-black uppercase tracking-[0.1em] text-violet-700 dark:text-violet-300">{selectedPreview.kind === 'overall' ? '整体故事归纳' : '实时归纳批次'}</span>
            <h3 className="mt-2 text-2xl font-black text-slate-950 dark:text-slate-100">{selectedPreview.title}</h3>
            <div className="mt-3 flex flex-wrap gap-2 text-xs font-bold text-slate-500 dark:text-slate-300">
              <span className="rounded-full bg-slate-100 px-2.5 py-1 dark:bg-slate-800">{turnRange(selectedPreview)}</span>
              {selectedPreview.time ? <span className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2.5 py-1 dark:bg-slate-800"><Clock3 size={12} />{selectedPreview.time}</span> : null}
              {selectedPreview.location ? <span className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2.5 py-1 dark:bg-slate-800"><MapPin size={12} />{selectedPreview.location}</span> : null}
              {selectedPreview.characters.length ? <span className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2.5 py-1 dark:bg-slate-800"><UsersRound size={12} />{selectedPreview.characters.join('、')}</span> : null}
            </div>
          </header>
        ) : null}
        {detailQuery.isLoading || detailQuery.isFetching && !detailQuery.data ? <p className="py-16 text-center text-sm font-semibold text-slate-400">正在读取归纳全文…</p> : null}
        {detailQuery.isError ? <ErrorState message="该归纳全文暂时无法读取。" onRetry={() => { void detailQuery.refetch() }} /> : null}
        {detailQuery.data ? <MarkdownReader detail={detailQuery.data} /> : null}
      </article>
    </div>
  )
}

function StoryMemoryCard({
  memory,
  onPreviewEvidence,
}: {
  memory: StoryMemoryItem
  onPreviewEvidence: (reference: SessionEvidenceReference) => void
}) {
  return (
    <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-950">
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded-full bg-violet-100 px-2.5 py-1 text-xs font-black text-violet-700 dark:bg-violet-500/15 dark:text-violet-200">{DREAM_KIND_LABELS[memory.memoryKind]}</span>
        <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-black text-slate-600 dark:bg-slate-800 dark:text-slate-200">{DREAM_EPISTEMIC_LABELS[memory.epistemicStatus]}</span>
        <span className={cn(
          'rounded-full px-2.5 py-1 text-xs font-black',
          memory.dreamProcessed
            ? 'bg-teal-100 text-teal-700 dark:bg-teal-500/15 dark:text-teal-200'
            : 'bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-200',
        )}>
          {memory.dreamProcessed ? '已进入应用 Dream 检查点' : '尚未进入应用 Dream 检查点'}
        </span>
      </div>
      <p className="mt-4 whitespace-pre-wrap text-sm font-semibold leading-7 text-slate-800 dark:text-slate-100">{memory.text}</p>
      <div className="mt-4 flex flex-wrap gap-2 text-[11px] font-bold text-slate-400">
        <span className="rounded-full bg-slate-100 px-2.5 py-1 dark:bg-slate-800">{storyMemoryTurnRange(memory)}</span>
        <span className="rounded-full bg-slate-100 px-2.5 py-1 dark:bg-slate-800">重要度 {memory.salience.toFixed(2)}</span>
        <span className="rounded-full bg-slate-100 px-2.5 py-1 dark:bg-slate-800">版本 {memory.version}</span>
        {memory.updatedAt ? <span className="rounded-full bg-slate-100 px-2.5 py-1 dark:bg-slate-800">更新 {formatDateTime(memory.updatedAt)}</span> : null}
      </div>
      {memory.evidence.length ? (
        <div className="mt-4 border-t border-slate-100 pt-3 dark:border-slate-800">
          <strong className="text-[10px] font-black uppercase tracking-wide text-slate-400">Evidence 引用</strong>
          <div className="mt-2 flex flex-wrap gap-2">
            {memory.evidence.map((evidence) => (
              <EvidenceReferenceButton
                key={`${memory.id}-${evidence.messageId}`}
                reference={evidence}
                onPreview={onPreviewEvidence}
              />
            ))}
          </div>
        </div>
      ) : null}
    </article>
  )
}

function StoryMemoryView({
  sessionId,
  enabled,
  onPreviewEvidence,
}: {
  sessionId: string
  enabled: boolean
  onPreviewEvidence: (reference: SessionEvidenceReference) => void
}) {
  const [kind, setKind] = useState<MemoryKindFilter>('all')
  const [checkpoint, setCheckpoint] = useState<DreamCheckpointFilter>('all')

  useEffect(() => {
    setKind('all')
    setCheckpoint('all')
  }, [sessionId])

  const query = useInfiniteQuery({
    queryKey: ['play-session-story-memories', sessionId, kind, checkpoint],
    queryFn: ({ pageParam }) => listSessionStoryMemories(sessionId, {
      page: pageParam,
      pageSize: 20,
      memoryKind: kind === 'all' ? undefined : kind,
      dreamProcessed: checkpoint === 'all' ? undefined : checkpoint === 'processed',
    }),
    initialPageParam: 1,
    getNextPageParam: (lastPage) => (
      lastPage.page * lastPage.pageSize < lastPage.total ? lastPage.page + 1 : undefined
    ),
    enabled,
    retry: false,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  })
  const items = query.data?.pages.flatMap((page) => page.items) ?? []
  const firstPage = query.data?.pages[0]
  const stats = firstPage?.stats

  return (
    <div className="space-y-5">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {[
          ['剧情事实', stats?.totalFacts ?? '—'],
          ['已进入 Dream 检查点', stats?.dreamProcessedFacts ?? '—'],
          ['待 Dream 检查点', stats?.pendingDreamFacts ?? '—'],
          ['待提取来源 Turn', stats?.unprocessedSourceTurns ?? '—'],
        ].map(([label, value]) => (
          <div key={String(label)} className="rounded-2xl border border-slate-200 bg-white px-4 py-4 shadow-sm dark:border-slate-800 dark:bg-slate-950">
            <span className="text-xs font-bold text-slate-400">{label}</span>
            <strong className="mt-2 block text-2xl font-black text-slate-950 dark:text-slate-100">{value}</strong>
          </div>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-950">
        <span className="inline-flex items-center gap-2 px-1 text-xs font-black text-slate-500 dark:text-slate-300"><Filter size={14} />筛选</span>
        <select value={kind} onChange={(event) => setKind(event.target.value as MemoryKindFilter)} className="h-10 rounded-xl border border-slate-200 bg-white px-3 text-xs font-black text-slate-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200" aria-label="筛选剧情记忆类别">
          <option value="all">全部类别</option>
          {DREAM_MEMORY_KINDS.map((item) => <option key={item} value={item}>{DREAM_KIND_LABELS[item]}</option>)}
        </select>
        <select value={checkpoint} onChange={(event) => setCheckpoint(event.target.value as DreamCheckpointFilter)} className="h-10 rounded-xl border border-slate-200 bg-white px-3 text-xs font-black text-slate-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200" aria-label="筛选 Dream 检查点状态">
          <option value="all">全部 Dream 状态</option>
          <option value="pending">尚未进入应用 Dream 检查点</option>
          <option value="processed">已进入应用 Dream 检查点</option>
        </select>
        <span className="ml-auto text-xs font-bold text-slate-400">当前筛选 {firstPage?.total ?? 0} 项</span>
        <RefreshButton loading={query.isFetching} onClick={() => { void query.refetch() }} />
      </div>

      {query.isLoading ? <EmptyState icon={<RefreshCw size={20} className="animate-spin" />} title="正在读取剧情记忆" description="这里只读取已经落库的 Story Memory，不会启动新的提取任务。" /> : null}
      {query.isError ? <ErrorState message="剧情记忆暂时无法读取。" onRetry={() => { void query.refetch() }} /> : null}
      {!query.isLoading && !query.isError && !items.length ? <EmptyState icon={<BrainCircuit size={20} />} title="暂无剧情记忆" description="当前尚未生成符合筛选条件的 Story Memory；自动提取可能尚未启用或尚未产生记录。" /> : null}
      {items.length ? <div className="grid gap-4 xl:grid-cols-2">{items.map((memory) => <StoryMemoryCard key={memory.id} memory={memory} onPreviewEvidence={onPreviewEvidence} />)}</div> : null}
      {query.hasNextPage ? (
        <button type="button" onClick={() => { void query.fetchNextPage() }} disabled={query.isFetchingNextPage} className="mx-auto flex h-11 items-center gap-2 rounded-xl bg-slate-950 px-5 text-sm font-black text-white disabled:opacity-50 dark:bg-violet-600">
          {query.isFetchingNextPage ? <RefreshCw size={15} className="animate-spin" /> : <History size={15} />}
          {query.isFetchingNextPage ? '正在加载…' : '加载更多剧情记忆'}
        </button>
      ) : null}
    </div>
  )
}

function PersistentMemoryCard({
  memory,
  onPreviewEvidence,
}: {
  memory: DreamMemory
  onPreviewEvidence: (reference: SessionEvidenceReference) => void
}) {
  const revision = memory.currentRevision
  return (
    <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-950">
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded-full bg-violet-100 px-2.5 py-1 text-xs font-black text-violet-700 dark:bg-violet-500/15 dark:text-violet-200">{DREAM_KIND_LABELS[revision.memoryKind]}</span>
        <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-black text-slate-600 dark:bg-slate-800 dark:text-slate-200">{DREAM_EPISTEMIC_LABELS[revision.epistemicStatus]}</span>
        <span className="rounded-full bg-indigo-100 px-2.5 py-1 text-xs font-black text-indigo-700 dark:bg-indigo-500/15 dark:text-indigo-200">{DREAM_LIFECYCLE_LABELS[memory.lifecycle]}</span>
        <span className={cn(
          'ml-auto inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-black',
          memory.evidenceValid
            ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-200'
            : 'bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-200',
        )}>
          {memory.evidenceValid ? <CheckCircle2 size={12} /> : <ShieldAlert size={12} />}
          {memory.evidenceValid ? '证据有效' : '证据失效'}
        </span>
      </div>
      <p className="mt-4 whitespace-pre-wrap text-sm font-semibold leading-7 text-slate-800 dark:text-slate-100">{revision.text}</p>
      <div className="mt-4 flex flex-wrap gap-2 text-[11px] font-bold text-slate-400">
        <span className="rounded-full bg-slate-100 px-2.5 py-1 dark:bg-slate-800">重要度 {revision.salience.toFixed(2)}</span>
        <span className="rounded-full bg-slate-100 px-2.5 py-1 dark:bg-slate-800">当前版本 {revision.revisionNumber}</span>
        <span className="rounded-full bg-slate-100 px-2.5 py-1 dark:bg-slate-800">历史版本 {memory.revisions.length}</span>
      </div>
      {memory.evidence.length ? (
        <div className="mt-4 flex flex-wrap gap-2 border-t border-slate-100 pt-3 dark:border-slate-800">
          {memory.evidence.map((evidence) => (
            <EvidenceReferenceButton
              key={`${memory.memoryId}-${evidence.messageId}`}
              reference={evidence}
              onPreview={onPreviewEvidence}
            />
          ))}
        </div>
      ) : null}
    </article>
  )
}

function PersistentMemoryView({
  sessionId,
  enabled,
  onManageDream,
  onPreviewEvidence,
}: {
  sessionId: string
  enabled: boolean
  onManageDream: () => void
  onPreviewEvidence: (reference: SessionEvidenceReference) => void
}) {
  const [lifecycle, setLifecycle] = useState<LifecycleFilter>('active')
  const [kind, setKind] = useState<MemoryKindFilter>('all')
  const [visibleLimit, setVisibleLimit] = useState(12)
  const query = useQuery({
    queryKey: ['play-session-dream-memories', sessionId],
    queryFn: () => listDreamMemories(sessionId),
    enabled,
    retry: false,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  })

  useEffect(() => {
    setLifecycle('active')
    setKind('all')
    setVisibleLimit(12)
  }, [sessionId])
  useEffect(() => setVisibleLimit(12), [kind, lifecycle])

  const memories = query.data?.items ?? []
  const filtered = memories.filter((memory) => (
    (lifecycle === 'all' || memory.lifecycle === lifecycle)
    && (kind === 'all' || memory.currentRevision.memoryKind === kind)
  ))
  const visible = filtered.slice(0, visibleLimit)

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-950">
        <span className="inline-flex items-center gap-2 px-1 text-xs font-black text-slate-500 dark:text-slate-300"><Filter size={14} />筛选</span>
        <select value={lifecycle} onChange={(event) => setLifecycle(event.target.value as LifecycleFilter)} className="h-10 rounded-xl border border-slate-200 bg-white px-3 text-xs font-black text-slate-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200" aria-label="筛选持久记忆生命周期">
          <option value="all">全部生命周期</option>
          {DREAM_MEMORY_LIFECYCLES.map((item) => <option key={item} value={item}>{DREAM_LIFECYCLE_LABELS[item]}</option>)}
        </select>
        <select value={kind} onChange={(event) => setKind(event.target.value as MemoryKindFilter)} className="h-10 rounded-xl border border-slate-200 bg-white px-3 text-xs font-black text-slate-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200" aria-label="筛选持久记忆类别">
          <option value="all">全部类别</option>
          {DREAM_MEMORY_KINDS.map((item) => <option key={item} value={item}>{DREAM_KIND_LABELS[item]}</option>)}
        </select>
        <span className="ml-auto text-xs font-bold text-slate-400">生效 {query.data?.activeCount ?? '—'} / {query.data?.activeLimit ?? 64} · 当前 {filtered.length} 项</span>
        <RefreshButton loading={query.isFetching} onClick={() => { void query.refetch() }} />
        <button type="button" onClick={onManageDream} className="inline-flex h-10 items-center gap-2 rounded-xl bg-indigo-600 px-3 text-xs font-black text-white transition hover:bg-indigo-700">
          <ExternalLink size={14} /> 前往 Dream Memory 管理
        </button>
      </div>
      {query.isLoading ? <EmptyState icon={<RefreshCw size={20} className="animate-spin" />} title="正在读取持久记忆" description="Persistent Memory 由独立 Dream service 提供。" /> : null}
      {query.isError ? <ErrorState message="Dream service 暂时不可用；对话、归纳和剧情记忆不受影响。" onRetry={() => { void query.refetch() }} /> : null}
      {!query.isLoading && !query.isError && !filtered.length ? <EmptyState icon={<Database size={20} />} title="当前筛选下没有持久记忆" description="可前往 Dream Memory 管理页生成、审阅或恢复记忆。" /> : null}
      {visible.length ? <div className="grid gap-4 xl:grid-cols-2">{visible.map((memory) => <PersistentMemoryCard key={memory.memoryId} memory={memory} onPreviewEvidence={onPreviewEvidence} />)}</div> : null}
      {visible.length < filtered.length ? <button type="button" onClick={() => setVisibleLimit((current) => current + 12)} className="mx-auto flex h-11 items-center gap-2 rounded-xl bg-slate-950 px-5 text-sm font-black text-white dark:bg-violet-600"><History size={15} />加载更多持久记忆</button> : null}
    </div>
  )
}

export function SessionStoryPanel({
  sessionId,
  open,
  activeTab,
  onTabChange,
  onClose,
  onManageDream,
}: {
  sessionId: string
  open: boolean
  activeTab: SessionStoryTab
  onTabChange: (tab: SessionStoryTab) => void
  onClose: () => void
  onManageDream: () => void
}) {
  const [evidenceReference, setEvidenceReference] = useState<SessionEvidenceReference | null>(null)
  const openEvidencePreview = useCallback((reference: SessionEvidenceReference) => {
    setEvidenceReference(reference)
  }, [])
  const closeEvidencePreview = useCallback(() => {
    setEvidenceReference(null)
  }, [])

  useEffect(() => {
    setEvidenceReference(null)
  }, [sessionId])

  useEffect(() => {
    if (!open) setEvidenceReference(null)
  }, [open])

  return (
    <>
      <SessionWorkspacePanel
        open={open}
        eyebrow="Story intelligence"
        title="故事与记忆"
        description="按实时推演的来源 Turn 浏览故事归纳、剧情事实和主 Agent 持久记忆。"
        tabs={[
          { id: 'summaries', label: '故事归纳', shortLabel: '归纳', icon: <FileText size={17} /> },
          { id: 'storyMemory', label: '剧情记忆', shortLabel: '剧情', icon: <BrainCircuit size={17} /> },
          { id: 'persistentMemory', label: '持久记忆', shortLabel: '持久', icon: <BookOpenText size={17} /> },
        ]}
        activeTab={activeTab}
        onTabChange={onTabChange}
        onClose={onClose}
        suspended={evidenceReference !== null}
      >
        {activeTab === 'summaries' ? <SummariesView sessionId={sessionId} enabled={open} /> : null}
        {activeTab === 'storyMemory' ? <StoryMemoryView sessionId={sessionId} enabled={open} onPreviewEvidence={openEvidencePreview} /> : null}
        {activeTab === 'persistentMemory' ? <PersistentMemoryView sessionId={sessionId} enabled={open} onManageDream={onManageDream} onPreviewEvidence={openEvidencePreview} /> : null}
      </SessionWorkspacePanel>
      {evidenceReference ? (
        <SessionTurnEvidencePreview
          sessionId={sessionId}
          reference={evidenceReference}
          onClose={closeEvidencePreview}
        />
      ) : null}
    </>
  )
}
