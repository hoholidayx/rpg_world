'use client'

import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { GitBranch, Loader2, RotateCcw, Save } from 'lucide-react'
import { NarrativeOutcomeWeightsEditor } from '@/components/narrative-outcome/NarrativeOutcomeWeightsEditor'
import {
  getStoryNarrativeOutcome,
  setStoryNarrativeOutcome,
} from '@/lib/api/narrativeOutcome'
import {
  copyNarrativeOutcomeWeights,
  validNarrativeOutcomeWeights,
  type NarrativeOutcomeWeights,
} from '@/types/narrativeOutcome'

function sourceLabel(source: 'config' | 'story' | 'session') {
  if (source === 'story') return 'Story 覆盖'
  if (source === 'session') return 'Session 覆盖'
  return '系统默认'
}

function equalWeights(first: NarrativeOutcomeWeights, second: NarrativeOutcomeWeights) {
  return Object.keys(first).every((key) => (
    first[key as keyof NarrativeOutcomeWeights] === second[key as keyof NarrativeOutcomeWeights]
  ))
}

export function StoryNarrativeOutcomePanel({
  workspace,
  storyId,
}: {
  workspace: string
  storyId: number
}) {
  const queryClient = useQueryClient()
  const [draft, setDraft] = useState<NarrativeOutcomeWeights | null>(null)
  const [error, setError] = useState<string | null>(null)
  const queryKey = useMemo(
    () => ['story-narrative-outcome', workspace, storyId] as const,
    [storyId, workspace],
  )
  const query = useQuery({
    queryKey,
    queryFn: () => getStoryNarrativeOutcome(workspace, storyId),
  })

  useEffect(() => {
    if (!query.data) return
    setDraft(copyNarrativeOutcomeWeights(query.data.storyOverride ?? query.data.effectiveWeights))
  }, [query.data])

  const mutation = useMutation({
    mutationFn: (weights: NarrativeOutcomeWeights | null) => (
      setStoryNarrativeOutcome(workspace, storyId, weights)
    ),
    onSuccess: (selection) => {
      setError(null)
      queryClient.setQueryData(queryKey, selection)
      setDraft(copyNarrativeOutcomeWeights(selection.storyOverride ?? selection.effectiveWeights))
      queryClient.invalidateQueries({ queryKey: ['session-narrative-outcome'] })
    },
    onError: (reason) => {
      setError(reason instanceof Error ? reason.message : '剧情结果分布保存失败')
    },
  })

  if (query.isLoading || !draft || !query.data) {
    return (
      <section className="rounded-lg border border-slate-200 bg-white px-5 py-8 text-center text-sm font-semibold text-slate-500 shadow-sm">
        <Loader2 size={18} className="mx-auto mb-2 animate-spin" />
        正在读取剧情结果分布
      </section>
    )
  }

  if (query.isError) {
    return (
      <section className="rounded-lg border border-rose-200 bg-rose-50 px-5 py-5 text-sm font-semibold text-rose-700">
        剧情结果分布加载失败：{query.error instanceof Error ? query.error.message : '未知错误'}
      </section>
    )
  }

  const savedWeights = query.data.storyOverride ?? query.data.effectiveWeights
  const dirty = !equalWeights(draft, savedWeights)
  const valid = validNarrativeOutcomeWeights(draft)
  const canRestore = Boolean(query.data.storyOverride) || !equalWeights(draft, query.data.systemDefault)

  return (
    <section className="rounded-lg border border-slate-200 bg-white shadow-sm">
      <header className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-200 px-5 py-4">
        <div>
          <h2 className="flex items-center gap-2 text-lg font-black text-slate-950">
            <GitBranch size={18} className="text-violet-600" />
            剧情结果分布
          </h2>
          <p className="mt-1 text-sm leading-6 text-slate-500">
            五档比例只影响剧情分支裁定；生成中的 turn 使用开始时快照。
          </p>
        </div>
        <span className="rounded-full bg-violet-100 px-3 py-1.5 text-xs font-black text-violet-700">
          当前：{sourceLabel(query.data.effectiveSource)}
        </span>
      </header>
      <div className="p-5">
        <NarrativeOutcomeWeightsEditor
          value={draft}
          definitions={query.data.definitions}
          disabled={mutation.isPending}
          onChange={setDraft}
        />
        {error ? (
          <p className="mt-3 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs font-semibold text-rose-700">{error}</p>
        ) : null}
        <div className="mt-4 flex flex-wrap justify-end gap-2">
          <button
            type="button"
            disabled={!canRestore || mutation.isPending}
            onClick={() => mutation.mutate(null)}
            className="inline-flex h-10 items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 text-sm font-black text-slate-600 transition hover:border-violet-200 hover:text-violet-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <RotateCcw size={15} />
            恢复系统默认
          </button>
          <button
            type="button"
            disabled={!dirty || !valid || mutation.isPending}
            onClick={() => mutation.mutate(draft)}
            className="inline-flex h-10 items-center gap-2 rounded-lg bg-violet-600 px-4 text-sm font-black text-white transition hover:bg-violet-700 disabled:cursor-not-allowed disabled:bg-slate-300"
          >
            {mutation.isPending ? <Loader2 size={15} className="animate-spin" /> : <Save size={15} />}
            保存比例
          </button>
        </div>
      </div>
    </section>
  )
}
