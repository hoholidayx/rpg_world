import { ArchiveRestore, BookOpen, CheckCircle2, History, ShieldAlert } from 'lucide-react'
import { DREAM_MEMORY_LIFECYCLES, type DreamMemory } from '@/types/dream'
import { cn } from '@/lib/utils/cn'
import { DREAM_EPISTEMIC_LABELS, DREAM_KIND_LABELS, DREAM_LIFECYCLE_LABELS } from './dreamLabels'
import type { DreamMemoryController } from './useDreamMemoryController'

function MemoryCard({ memory, controller }: { memory: DreamMemory; controller: DreamMemoryController }) {
  const revision = memory.currentRevision

  return (
    <article className="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-950">
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded-full bg-violet-100 px-2.5 py-1 text-xs font-black text-violet-700 dark:bg-violet-500/15 dark:text-violet-200">
          {DREAM_KIND_LABELS[revision.memoryKind]}
        </span>
        <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-black text-slate-600 dark:bg-slate-800 dark:text-slate-200">
          {DREAM_EPISTEMIC_LABELS[revision.epistemicStatus]}
        </span>
        <span className="text-xs font-bold text-slate-400">重要度 {revision.salience.toFixed(2)} · rev {revision.revisionNumber}</span>
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
      <p className="mt-3 whitespace-pre-wrap text-sm font-semibold leading-6 text-slate-800 dark:text-slate-100">{revision.text}</p>
      <div className="mt-3 flex flex-wrap gap-2 text-xs font-bold text-slate-400">
        {memory.evidence.map((evidence) => (
          <span key={`${memory.memoryId}-${revision.revisionNumber}-${evidence.messageId}`} className="rounded-full bg-slate-100 px-2 py-1 dark:bg-slate-800 dark:text-slate-300">
            turn {evidence.turnId} · msg {evidence.messageId}
          </span>
        ))}
      </div>

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-3 dark:border-slate-800">
        <code className="break-all text-[11px] text-slate-400">{memory.memoryId}</code>
        <div className="flex items-center gap-2">
          {memory.revisions.length > 1 ? (
            <details className="relative">
              <summary className="inline-flex cursor-pointer list-none items-center gap-1 rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs font-black text-slate-600 dark:border-slate-700 dark:text-slate-300">
                <History size={13} />版本 {memory.revisions.length}
              </summary>
              <div className="absolute bottom-full right-0 z-20 mb-2 max-h-72 w-[min(420px,80vw)] overflow-y-auto rounded-xl border border-slate-200 bg-white p-3 shadow-xl dark:border-slate-700 dark:bg-slate-900">
                <div className="grid gap-2">
                  {memory.revisions.map((item) => (
                    <div key={`${memory.memoryId}-${item.revisionNumber}`} className="rounded-lg bg-slate-50 px-3 py-2 dark:bg-slate-800">
                      <span className="text-[11px] font-black text-slate-400">rev {item.revisionNumber} · {DREAM_KIND_LABELS[item.memoryKind]}</span>
                      <p className="mt-1 text-xs font-semibold leading-5 text-slate-700 dark:text-slate-200">{item.text}</p>
                    </div>
                  ))}
                </div>
              </div>
            </details>
          ) : null}
          {memory.lifecycle === 'retired' ? (
            <button
              type="button"
              onClick={() => controller.restoreMemory(memory.memoryId)}
              disabled={!memory.evidenceValid || controller.mutating || controller.refreshing}
              title={memory.evidenceValid ? '恢复为生效记忆' : '证据已失效，不能恢复'}
              className="inline-flex items-center gap-1 rounded-lg bg-violet-600 px-2.5 py-1.5 text-xs font-black text-white transition hover:bg-violet-700 disabled:cursor-not-allowed disabled:bg-slate-300 dark:disabled:bg-slate-700"
            >
              <ArchiveRestore size={13} />恢复
            </button>
          ) : null}
        </div>
      </div>
    </article>
  )
}

export function DreamLedgerPanel({ controller }: { controller: DreamMemoryController }) {
  const memories = controller.memoriesQuery.data?.items ?? []
  const activeCount = controller.memoriesQuery.data?.activeCount
    ?? memories.filter((memory) => memory.lifecycle === 'active').length
  const activeLimit = controller.memoriesQuery.data?.activeLimit ?? 64

  return (
    <section className="rounded-2xl border border-slate-200 bg-slate-50 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-5 py-4 dark:border-slate-800">
        <div>
          <div className="flex items-center gap-2">
            <BookOpen size={18} className="text-teal-600 dark:text-teal-300" />
            <h2 className="text-base font-black text-slate-950 dark:text-slate-100">持久记忆账本</h2>
          </div>
          <p className="mt-1 text-xs font-semibold text-slate-400">生效 {activeCount} / {activeLimit} · 只有证据有效的 active revision 会进入 Context</p>
        </div>
      </header>

      <div className="flex gap-2 overflow-x-auto border-b border-slate-200 px-5 py-3 dark:border-slate-800">
        {DREAM_MEMORY_LIFECYCLES.map((item) => {
          const count = memories.filter((memory) => memory.lifecycle === item).length
          return (
            <button
              key={item}
              type="button"
              onClick={() => controller.setLifecycle(item)}
              className={cn(
                'shrink-0 rounded-full px-3 py-1.5 text-xs font-black transition',
                controller.lifecycle === item
                  ? 'bg-slate-950 text-white dark:bg-violet-600'
                  : 'bg-white text-slate-500 hover:text-violet-700 dark:bg-slate-950 dark:text-slate-300',
              )}
            >
              {DREAM_LIFECYCLE_LABELS[item]} · {count}
            </button>
          )
        })}
      </div>

      {controller.memoriesQuery.isLoading ? (
        <div className="px-5 py-10 text-center text-sm font-semibold text-slate-400">正在读取记忆账本…</div>
      ) : controller.visibleMemories.length ? (
        <div className="grid gap-3 p-5">
          {controller.visibleMemories.map((memory) => <MemoryCard key={memory.memoryId} memory={memory} controller={controller} />)}
        </div>
      ) : (
        <div className="px-5 py-10 text-center text-sm font-semibold text-slate-400">
          当前没有{DREAM_LIFECYCLE_LABELS[controller.lifecycle]}的记忆。
        </div>
      )}
    </section>
  )
}
