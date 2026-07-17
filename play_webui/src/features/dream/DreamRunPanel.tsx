import { Brain, History, Loader2, MoonStar, Play, RefreshCcw, Sparkles } from 'lucide-react'
import type { DreamMemoryController } from './useDreamMemoryController'
import { DREAM_DEPTH_LABELS, DREAM_SCOPE_LABELS, DREAM_STATUS_LABELS } from './dreamLabels'

export function DreamRunPanel({ controller }: { controller: DreamMemoryController }) {
  const { proposal } = controller
  const proposals = controller.proposalsQuery.data?.items ?? []
  const currentGenerating = proposal?.status === 'generating'
  const generating = proposals.some((item) => item.status === 'generating') || currentGenerating

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-950">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-violet-700 dark:text-violet-200">
            <MoonStar size={19} />
            <h2 className="text-base font-black">开始一次 Dream</h2>
          </div>
          <p className="mt-2 max-w-3xl text-sm font-semibold leading-6 text-slate-500 dark:text-slate-300">
            Dream 只生成可审阅的记忆提案；在你确认应用前，不会改变主 Agent 的持久记忆。
          </p>
        </div>
        <button
          type="button"
          onClick={() => void controller.refresh()}
          disabled={controller.refreshing || controller.mutating}
          className="inline-flex h-10 items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 text-sm font-black text-slate-600 transition hover:border-violet-300 hover:text-violet-700 disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300"
        >
          <RefreshCcw size={15} className={controller.refreshing ? 'animate-spin' : ''} />
          手动刷新
        </button>
      </div>

      <div className="mt-5 grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] lg:items-end">
        <label className="grid gap-2 text-sm font-black text-slate-700 dark:text-slate-200">
          睡眠深度
          <span className="relative">
            <Brain className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-violet-500" size={16} />
            <select
              value={controller.depth}
              onChange={(event) => controller.setDepth(event.target.value as typeof controller.depth)}
              disabled={controller.mutating || generating}
              className="h-11 w-full appearance-none rounded-lg border border-slate-200 bg-white pl-10 pr-3 text-sm font-bold text-slate-800 outline-none transition focus:border-violet-400 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
            >
              <option value="shallow">浅睡 · 从 summary / story memory 提炼</option>
              <option value="deep">深睡 · 重新分析主消息证据</option>
            </select>
          </span>
        </label>
        <label className="grid gap-2 text-sm font-black text-slate-700 dark:text-slate-200">
          分析范围
          <span className="relative">
            <Sparkles className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-amber-500" size={16} />
            <select
              value={controller.scope}
              onChange={(event) => controller.setScope(event.target.value as typeof controller.scope)}
              disabled={controller.mutating || generating}
              className="h-11 w-full appearance-none rounded-lg border border-slate-200 bg-white pl-10 pr-3 text-sm font-bold text-slate-800 outline-none transition focus:border-violet-400 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
            >
              <option value="incremental">增量 · 只处理新变化</option>
              <option value="full">全量 · 重新扫描全部可用来源</option>
            </select>
          </span>
        </label>
        <button
          type="button"
          onClick={() => controller.createProposal()}
          disabled={controller.mutating || generating}
          className="inline-flex h-11 items-center justify-center gap-2 rounded-lg bg-violet-600 px-5 text-sm font-black text-white shadow-lg shadow-violet-100 transition hover:bg-violet-700 disabled:cursor-not-allowed disabled:bg-slate-300 disabled:shadow-none dark:shadow-violet-950/40 dark:disabled:bg-slate-700"
        >
          {controller.mutating ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} />}
          生成提案
        </button>
      </div>

      {controller.depth === 'deep' && controller.scope === 'full' ? (
        <p className="mt-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm font-bold leading-6 text-amber-800 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-200">
          深睡全量会扫描当前完整主历史，耗时与模型用量最高；它也是唯一可以根据“全历史已无证据”建议全局退休记忆的模式。
        </p>
      ) : null}

      <div className="mt-4 grid gap-3 rounded-lg bg-slate-50 px-4 py-3 dark:bg-slate-900">
        <label className="grid gap-1.5 text-xs font-black text-slate-500 dark:text-slate-300 sm:grid-cols-[120px_minmax(0,1fr)] sm:items-center">
          <span className="inline-flex items-center gap-1.5"><History size={14} />当前 / 历史提案</span>
          <select
            value={controller.proposalId}
            disabled={!proposals.length || controller.mutating}
            onChange={(event) => {
              const selected = proposals.find((item) => item.proposalId === event.target.value)
              controller.selectProposal(event.target.value, selected)
            }}
            className="h-9 min-w-0 rounded-lg border border-slate-200 bg-white px-3 text-xs font-bold text-slate-700 outline-none transition focus:border-violet-400 disabled:text-slate-400 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-200"
          >
            {!proposals.length ? <option value="">暂无历史提案</option> : null}
            {proposals.map((item) => (
              <option key={item.proposalId} value={item.proposalId}>
                {DREAM_STATUS_LABELS[item.status]} · {DREAM_DEPTH_LABELS[item.depth]} / {DREAM_SCOPE_LABELS[item.scope]} · {item.createdAt || item.proposalId}
              </option>
            ))}
          </select>
        </label>

        {proposal ? (
          <div className="flex flex-wrap items-center gap-2 text-xs font-bold text-slate-500 dark:text-slate-300">
            <span className="rounded-full bg-violet-100 px-2.5 py-1 text-violet-700 dark:bg-violet-500/15 dark:text-violet-200">
              {DREAM_STATUS_LABELS[proposal.status]}
            </span>
            <span>{DREAM_DEPTH_LABELS[proposal.depth]} · {DREAM_SCOPE_LABELS[proposal.scope]}</span>
            <code className="break-all font-mono text-slate-400">{proposal.proposalId}</code>
            {currentGenerating ? <span className="ml-auto inline-flex items-center gap-1"><Loader2 size={13} className="animate-spin" />请稍后手动刷新</span> : null}
          </div>
        ) : controller.proposalsQuery.isLoading ? (
          <span className="inline-flex items-center gap-2 text-xs font-bold text-slate-400"><Loader2 size={13} className="animate-spin" />正在读取历史提案</span>
        ) : null}
      </div>
    </section>
  )
}
