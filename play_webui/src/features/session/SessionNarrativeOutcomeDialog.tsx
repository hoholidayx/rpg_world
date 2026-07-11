'use client'

import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2, Save, Trash2 } from 'lucide-react'
import { Dialog } from '@/components/common/Dialog'
import { NarrativeOutcomeWeightsEditor } from '@/components/narrative-outcome/NarrativeOutcomeWeightsEditor'
import {
  getSessionNarrativeOutcome,
  setSessionNarrativeOutcome,
} from '@/lib/api/narrativeOutcome'
import {
  copyNarrativeOutcomeWeights,
  validNarrativeOutcomeWeights,
  type NarrativeOutcomeWeights,
} from '@/types/narrativeOutcome'
import { cn } from '@/lib/utils/cn'

function sourceLabel(source: 'config' | 'story' | 'session') {
  if (source === 'session') return '会话覆盖'
  if (source === 'story') return 'Story 继承'
  return '系统默认'
}

export function SessionNarrativeOutcomeDialog({
  open,
  sessionId,
  onClose,
  showToast,
}: {
  open: boolean
  sessionId: string
  onClose: () => void
  showToast: (message: string) => void
}) {
  const queryClient = useQueryClient()
  const [overrideEnabled, setOverrideEnabled] = useState(false)
  const [draft, setDraft] = useState<NarrativeOutcomeWeights | null>(null)
  const [error, setError] = useState<string | null>(null)
  const queryKey = ['session-narrative-outcome', sessionId] as const
  const query = useQuery({
    queryKey,
    queryFn: () => getSessionNarrativeOutcome(sessionId),
    enabled: open,
  })

  useEffect(() => {
    if (!open || !query.data) return
    setOverrideEnabled(query.data.sessionOverride !== null)
    setDraft(copyNarrativeOutcomeWeights(query.data.sessionOverride ?? query.data.effectiveWeights))
    setError(null)
  }, [open, query.data])

  const mutation = useMutation({
    mutationFn: (weights: NarrativeOutcomeWeights | null) => (
      setSessionNarrativeOutcome(sessionId, weights)
    ),
    onSuccess: (selection) => {
      queryClient.setQueryData(queryKey, selection)
      setOverrideEnabled(selection.sessionOverride !== null)
      setDraft(copyNarrativeOutcomeWeights(selection.sessionOverride ?? selection.effectiveWeights))
      setError(null)
      showToast(selection.sessionOverride ? '会话剧情比例已保存' : '已清除覆盖并继承 Story')
    },
    onError: (reason) => {
      setError(reason instanceof Error ? reason.message : '会话剧情比例保存失败')
    },
  })

  if (!open) return null

  return (
    <Dialog title="会话剧情结果分布" onClose={onClose} size="3xl" overlayClassName="z-[70]">
      <div className="max-h-[70vh] overflow-y-auto px-6 py-5">
        {query.isLoading || !query.data || !draft ? (
          <div className="py-10 text-center text-sm font-semibold text-slate-500">
            <Loader2 size={18} className="mx-auto mb-2 animate-spin" />
            正在读取有效比例
          </div>
        ) : query.isError ? (
          <p className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-4 text-sm font-semibold text-rose-700">
            加载失败：{query.error instanceof Error ? query.error.message : '未知错误'}
          </p>
        ) : (
          <>
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
              <div>
                <strong className="block text-sm font-black text-slate-900">启用 Session 覆盖</strong>
                <span className="mt-1 block text-xs font-semibold text-slate-500">
                  当前有效来源：{sourceLabel(query.data.effectiveSource)}
                </span>
              </div>
              <button
                type="button"
                role="switch"
                aria-checked={overrideEnabled}
                disabled={mutation.isPending}
                onClick={() => {
                  const enabled = !overrideEnabled
                  setOverrideEnabled(enabled)
                  if (enabled) {
                    setDraft(copyNarrativeOutcomeWeights(query.data.effectiveWeights))
                  }
                }}
                className={cn('h-6 w-11 rounded-full p-0.5 transition', overrideEnabled ? 'bg-violet-600' : 'bg-slate-300')}
              >
                <span className={cn('block h-5 w-5 rounded-full bg-white transition', overrideEnabled ? 'translate-x-5' : 'translate-x-0')} />
              </button>
            </div>
            <NarrativeOutcomeWeightsEditor
              value={draft}
              definitions={query.data.definitions}
              disabled={!overrideEnabled || mutation.isPending}
              onChange={setDraft}
            />
            {!overrideEnabled ? (
              <p className="mt-3 text-xs font-semibold leading-5 text-slate-500">
                保存后会清除 Session 覆盖；下一 turn 自动继承 Story，没有 Story 覆盖时使用系统默认。
              </p>
            ) : null}
            {error ? (
              <p className="mt-3 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs font-semibold text-rose-700">{error}</p>
            ) : null}
          </>
        )}
      </div>
      <footer className="flex flex-wrap items-center justify-between gap-2 border-t border-slate-200 bg-slate-50 px-6 py-4">
        <button
          type="button"
          disabled={!query.data?.sessionOverride || mutation.isPending}
          onClick={() => mutation.mutate(null)}
          className="inline-flex h-10 items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 text-sm font-black text-slate-600 transition hover:border-rose-200 hover:text-rose-600 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <Trash2 size={15} />
          清除覆盖并继承 Story
        </button>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={onClose}
            className="h-10 rounded-lg border border-slate-200 bg-white px-4 text-sm font-black text-slate-600 transition hover:border-violet-200 hover:text-violet-700"
          >
            关闭
          </button>
          <button
            type="button"
            disabled={
              !query.data
              || !draft
              || mutation.isPending
              || (overrideEnabled && !validNarrativeOutcomeWeights(draft))
            }
            onClick={() => mutation.mutate(overrideEnabled ? draft : null)}
            className="inline-flex h-10 items-center gap-2 rounded-lg bg-violet-600 px-4 text-sm font-black text-white transition hover:bg-violet-700 disabled:cursor-not-allowed disabled:bg-slate-300"
          >
            {mutation.isPending ? <Loader2 size={15} className="animate-spin" /> : <Save size={15} />}
            保存
          </button>
        </div>
      </footer>
    </Dialog>
  )
}
