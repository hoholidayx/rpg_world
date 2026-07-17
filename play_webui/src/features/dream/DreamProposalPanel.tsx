import { Check, FileEdit, Loader2, Save, Send, XCircle } from 'lucide-react'
import {
  DREAM_EPISTEMIC_STATUSES,
  DREAM_ITEM_ACTIONS,
  DREAM_MAX_MEMORY_TEXT_CHARS,
  DREAM_MEMORY_KINDS,
  type DreamProposalItem,
} from '@/types/dream'
import { cn } from '@/lib/utils/cn'
import {
  DREAM_ACTION_LABELS,
  DREAM_EPISTEMIC_LABELS,
  DREAM_KIND_LABELS,
  DREAM_STATUS_LABELS,
} from './dreamLabels'
import type { DreamMemoryController } from './useDreamMemoryController'

const actionClasses = {
  add: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-200',
  revise: 'bg-sky-100 text-sky-700 dark:bg-sky-500/15 dark:text-sky-200',
  supersede: 'bg-violet-100 text-violet-700 dark:bg-violet-500/15 dark:text-violet-200',
  retire: 'bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200',
} as const

function ProposalItemEditor({
  item,
  controller,
}: {
  item: DreamProposalItem
  controller: DreamMemoryController
}) {
  const draft = controller.draftItems.find((candidate) => candidate.itemId === item.itemId)
  if (!draft) return null
  const selectable = controller.proposal?.status === 'ready'
    && !controller.mutating
    && !controller.refreshing
  const factEditable = selectable && item.action !== 'retire'
  const targetMemory = controller.memoriesQuery.data?.items.find(
    (memory) => memory.memoryId === item.targetMemoryId,
  )

  return (
    <article className={cn(
      'rounded-xl border p-4 transition',
      draft.selected
        ? 'border-violet-200 bg-white dark:border-violet-500/30 dark:bg-slate-950'
        : 'border-slate-200 bg-slate-50 opacity-70 dark:border-slate-800 dark:bg-slate-900',
    )}>
      <div className="flex flex-wrap items-center gap-2">
        <label className="inline-flex cursor-pointer items-center gap-2 text-sm font-black text-slate-700 dark:text-slate-200">
          <input
            type="checkbox"
            checked={draft.selected}
            disabled={!selectable}
            onChange={(event) => controller.updateDraftItem(item.itemId, { selected: event.target.checked })}
            className="h-4 w-4 rounded accent-violet-600"
          />
          纳入本次应用
        </label>
        <span className={cn('rounded-full px-2.5 py-1 text-xs font-black', actionClasses[item.action])}>
          {DREAM_ACTION_LABELS[item.action]}
        </span>
        {item.targetMemoryId ? <code className="text-xs text-slate-400">目标 {item.targetMemoryId}</code> : null}
      </div>

      <textarea
        value={draft.text}
        disabled={!factEditable}
        onChange={(event) => controller.updateDraftItem(item.itemId, { text: event.target.value })}
        maxLength={DREAM_MAX_MEMORY_TEXT_CHARS}
        rows={3}
        aria-label={`${DREAM_ACTION_LABELS[item.action]}记忆正文`}
        className="mt-3 w-full resize-y rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-semibold leading-6 text-slate-800 outline-none transition focus:border-violet-400 disabled:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 dark:disabled:bg-slate-800"
      />
      <p className="mt-1 text-right text-[11px] font-bold text-slate-400">
        {draft.text.length} / {DREAM_MAX_MEMORY_TEXT_CHARS}
      </p>
      {item.action === 'retire' ? (
        <p className="mt-2 rounded-lg bg-slate-100 px-3 py-2 text-xs font-bold leading-5 text-slate-500 dark:bg-slate-800 dark:text-slate-300">
          退休只改变记忆生命周期；当前 revision 的正文、类别、可信状态和重要度保持不变。
        </p>
      ) : null}
      {item.reason ? (
        <p className="mt-2 text-xs font-semibold leading-5 text-slate-400">建议理由：{item.reason}</p>
      ) : null}
      {targetMemory && item.action !== 'add' ? (
        <div className="mt-3 rounded-lg border border-dashed border-slate-200 bg-slate-50 px-3 py-2 dark:border-slate-700 dark:bg-slate-900">
          <span className="text-[11px] font-black uppercase text-slate-400">修改前 · rev {targetMemory.currentRevisionNumber}</span>
          <p className="mt-1 text-xs font-semibold leading-5 text-slate-600 dark:text-slate-300">{targetMemory.currentRevision.text}</p>
        </div>
      ) : null}

      <div className="mt-3 grid gap-3 sm:grid-cols-[1fr_1fr_150px]">
        <label className="grid gap-1 text-xs font-black text-slate-500 dark:text-slate-300">
          记忆类别
          <select
            value={draft.memoryKind}
            disabled={!factEditable}
            onChange={(event) => controller.updateDraftItem(item.itemId, { memoryKind: event.target.value as typeof draft.memoryKind })}
            className="h-9 rounded-lg border border-slate-200 bg-white px-2 text-sm font-bold text-slate-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
          >
            {DREAM_MEMORY_KINDS.map((kind) => <option key={kind} value={kind}>{DREAM_KIND_LABELS[kind]}</option>)}
          </select>
        </label>
        <label className="grid gap-1 text-xs font-black text-slate-500 dark:text-slate-300">
          可信状态
          <select
            value={draft.epistemicStatus}
            disabled={!factEditable}
            onChange={(event) => controller.updateDraftItem(item.itemId, { epistemicStatus: event.target.value as typeof draft.epistemicStatus })}
            className="h-9 rounded-lg border border-slate-200 bg-white px-2 text-sm font-bold text-slate-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
          >
            {DREAM_EPISTEMIC_STATUSES.map((status) => <option key={status} value={status}>{DREAM_EPISTEMIC_LABELS[status]}</option>)}
          </select>
        </label>
        <label className="grid gap-1 text-xs font-black text-slate-500 dark:text-slate-300">
          重要度 · {draft.salience.toFixed(2)}
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={draft.salience}
            disabled={!factEditable}
            onChange={(event) => controller.updateDraftItem(item.itemId, { salience: Number(event.target.value) })}
            className="h-9 accent-violet-600"
          />
        </label>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2 text-xs font-bold text-slate-400">
        <span>证据</span>
        {item.evidence.length ? item.evidence.map((evidence) => (
          <span key={`${item.itemId}-${evidence.messageId}`} className="rounded-full bg-slate-100 px-2 py-1 dark:bg-slate-800 dark:text-slate-300">
            turn {evidence.turnId} · msg {evidence.messageId}
          </span>
        )) : <span className="text-amber-600 dark:text-amber-300">无可应用证据</span>}
        {item.evidence.length && !controller.evidenceHistoryLoaded ? (
          <button
            type="button"
            onClick={() => void controller.loadEvidenceHistory()}
            disabled={controller.refreshing || controller.mutating}
            className="rounded-full border border-slate-200 bg-white px-2 py-1 text-violet-700 transition hover:border-violet-300 disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-700 dark:bg-slate-950 dark:text-violet-200"
          >
            查看当前消息定位
          </button>
        ) : null}
      </div>
      {controller.evidenceHistoryLoaded && item.evidence.length ? (
        <div className="mt-2 grid gap-2">
          <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-bold leading-5 text-amber-800 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-200">
            当前消息仅供按 ID 定位，页面无法核对 Evidence 的历史版本与哈希；Apply 会按 version/hash 重新校验。
          </p>
          {item.evidence.map((evidence) => {
            const message = controller.evidenceMessagesById.get(evidence.messageId)
            return (
              <div key={`preview-${item.itemId}-${evidence.messageId}`} className="rounded-lg bg-slate-50 px-3 py-2 dark:bg-slate-900">
                <span className="text-[11px] font-black text-slate-400">
                  turn {evidence.turnId} · msg {evidence.messageId} · Evidence v{evidence.messageVersion} / {evidence.contentHash.slice(0, 8)}…
                </span>
                <p className="mt-1 line-clamp-3 text-xs font-semibold leading-5 text-slate-600 dark:text-slate-300">
                  {message
                    ? `当前 ${message.role} 消息（仅供定位）：${message.content}`
                    : '当前主历史中已找不到这条 Evidence 对应消息。'}
                </p>
              </div>
            )
          })}
        </div>
      ) : null}
    </article>
  )
}

export function DreamProposalPanel({ controller }: { controller: DreamMemoryController }) {
  const proposal = controller.proposal

  return (
    <section className="rounded-2xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-950">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-5 py-4 dark:border-slate-800">
        <div>
          <div className="flex items-center gap-2">
            <FileEdit size={18} className="text-violet-600 dark:text-violet-300" />
            <h2 className="text-base font-black text-slate-950 dark:text-slate-100">Dream 提案</h2>
          </div>
          <p className="mt-1 text-xs font-semibold text-slate-400">逐项选择与编辑；动作目标和消息证据不可修改。</p>
        </div>
        {proposal ? (
          <span className="rounded-full bg-slate-100 px-3 py-1.5 text-xs font-black text-slate-600 dark:bg-slate-800 dark:text-slate-200">
            {DREAM_STATUS_LABELS[proposal.status]}
          </span>
        ) : null}
      </header>

      {!controller.proposalId ? (
        <div className="px-5 py-12 text-center text-sm font-semibold text-slate-400">先生成一份 Dream proposal。</div>
      ) : controller.proposalQuery.isLoading ? (
        <div className="flex items-center justify-center gap-2 px-5 py-12 text-sm font-bold text-slate-500"><Loader2 size={16} className="animate-spin" />正在读取 proposal</div>
      ) : !proposal ? (
        <div className="px-5 py-12 text-center text-sm font-semibold text-slate-400">无法读取当前 proposal，请检查错误信息或重新生成。</div>
      ) : proposal.status === 'generating' ? (
        <div className="px-5 py-12 text-center">
          <Loader2 size={24} className="mx-auto animate-spin text-violet-600" />
          <p className="mt-3 text-sm font-black text-slate-700 dark:text-slate-200">Dream 正在生成</p>
          <p className="mt-1 text-xs font-semibold text-slate-400">页面不会自动轮询。稍后点击上方“手动刷新”。</p>
        </div>
      ) : (
        <>
          {proposal.errorMessage ? (
            <div className="m-5 rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-bold text-rose-700 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-200">
              {proposal.errorMessage}{proposal.errorCode ? ` (${proposal.errorCode})` : ''}
            </div>
          ) : null}
          {proposal.items.length ? (
            <div className="grid gap-5 p-5">
              {DREAM_ITEM_ACTIONS.map((action) => {
                const items = proposal.items.filter((item) => item.action === action)
                if (!items.length) return null
                return (
                  <section key={action}>
                    <h3 className="mb-2 text-xs font-black uppercase tracking-wide text-slate-400">
                      {DREAM_ACTION_LABELS[action]} · {items.length}
                    </h3>
                    <div className="grid gap-3">
                      {items.map((item) => <ProposalItemEditor key={item.itemId} item={item} controller={controller} />)}
                    </div>
                  </section>
                )
              })}
            </div>
          ) : proposal.status === 'ready' || proposal.status === 'applied' ? (
            <div className="flex items-center justify-center gap-2 px-5 py-10 text-sm font-bold text-slate-500 dark:text-slate-300">
              <Check size={17} className="text-emerald-500" />本次扫描没有发现需要变更的持久记忆
            </div>
          ) : null}

          {proposal.status === 'ready' ? (
            <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 bg-slate-50 px-5 py-4 dark:border-slate-800 dark:bg-slate-900">
              <p className="text-xs font-bold text-slate-500 dark:text-slate-300">已选择 {controller.selectedItemCount} / {proposal.items.length} 项</p>
              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  onClick={() => controller.rejectProposal()}
                  disabled={controller.mutating || controller.refreshing}
                  className="inline-flex h-10 items-center gap-2 rounded-lg border border-rose-200 bg-white px-3 text-sm font-black text-rose-700 transition hover:bg-rose-50 disabled:opacity-50 dark:border-rose-500/30 dark:bg-slate-950 dark:text-rose-200"
                >
                  <XCircle size={15} />拒绝整份
                </button>
                <button
                  type="button"
                  onClick={() => controller.saveProposal()}
                  disabled={controller.mutating || controller.refreshing}
                  className="inline-flex h-10 items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 text-sm font-black text-slate-700 transition hover:border-violet-300 hover:text-violet-700 disabled:opacity-50 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-200"
                >
                  <Save size={15} />保存编辑
                </button>
                <button
                  type="button"
                  onClick={() => controller.applyProposal()}
                  disabled={controller.mutating || controller.refreshing}
                  className="inline-flex h-10 items-center gap-2 rounded-lg bg-violet-600 px-4 text-sm font-black text-white transition hover:bg-violet-700 disabled:bg-slate-400"
                >
                  {controller.mutating ? <Loader2 size={15} className="animate-spin" /> : <Send size={15} />}
                  应用选中项
                </button>
              </div>
            </footer>
          ) : null}
        </>
      )}
    </section>
  )
}
