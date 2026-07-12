'use client'

import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Boxes, Loader2, RotateCcw, Save } from 'lucide-react'
import { NarrativeOutcomeWeightsEditor } from '@/components/narrative-outcome/NarrativeOutcomeWeightsEditor'
import { getStoryRPModules, patchStoryRPModule } from '@/lib/api/rpModules'
import {
  copyNarrativeOutcomeWeights,
  validNarrativeOutcomeWeights,
  type NarrativeOutcomeWeights,
} from '@/types/narrativeOutcome'
import { RP_MODULE_NAME, type RPModuleConfig, type RPModuleConfigValues } from '@/types/rpModules'
import { cn } from '@/lib/utils/cn'

function StoryModuleCard({
  module,
  workspace,
  storyId,
  onSaved,
}: {
  module: RPModuleConfig
  workspace: string
  storyId: number
  onSaved: (value: RPModuleConfig) => void
}) {
  const [enabled, setEnabled] = useState(module.storyEnabled)
  const [autoAdjudication, setAutoAdjudication] = useState(
    module.effectiveConfig.auto_adjudication_enabled ?? true,
  )
  const [weights, setWeights] = useState<NarrativeOutcomeWeights | null>(
    module.effectiveConfig.weights ? copyNarrativeOutcomeWeights(module.effectiveConfig.weights) : null,
  )
  const [defaultDC, setDefaultDC] = useState(module.effectiveConfig.default_dc ?? 12)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setEnabled(module.storyEnabled)
    setAutoAdjudication(module.effectiveConfig.auto_adjudication_enabled ?? true)
    setWeights(module.effectiveConfig.weights ? copyNarrativeOutcomeWeights(module.effectiveConfig.weights) : null)
    setDefaultDC(module.effectiveConfig.default_dc ?? 12)
  }, [module])

  const mutation = useMutation({
    mutationFn: (payload: { enabled: boolean; config: RPModuleConfigValues }) => (
      patchStoryRPModule(workspace, storyId, module.moduleName, payload)
    ),
    onSuccess: (value) => {
      setError(null)
      onSaved(value)
    },
    onError: (reason) => setError(reason instanceof Error ? reason.message : '模块配置保存失败'),
  })

  const config: RPModuleConfigValues = module.moduleName === RP_MODULE_NAME.NARRATIVE_OUTCOME
    ? { auto_adjudication_enabled: autoAdjudication, ...(weights ? { weights } : {}) }
    : { default_dc: defaultDC }
  const valid = module.moduleName !== RP_MODULE_NAME.NARRATIVE_OUTCOME
    ? Number.isInteger(defaultDC) && defaultDC > 0
    : Boolean(weights && validNarrativeOutcomeWeights(weights))

  return (
    <article className="rounded-lg border border-slate-200 bg-slate-50 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-black text-slate-950">{module.displayName}</h3>
          <p className="mt-1 text-xs font-semibold leading-5 text-slate-500">{module.description}</p>
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={enabled}
          disabled={!module.systemEnabled || mutation.isPending}
          onClick={() => setEnabled((current) => !current)}
          className={cn('h-6 w-11 rounded-full p-0.5 transition', enabled ? 'bg-violet-600' : 'bg-slate-300')}
        >
          <span className={cn('block h-5 w-5 rounded-full bg-white transition', enabled ? 'translate-x-5' : 'translate-x-0')} />
        </button>
      </div>

      {module.moduleName === RP_MODULE_NAME.NARRATIVE_OUTCOME && weights ? (
        <div className="mt-4 space-y-4">
          <label className="flex items-center justify-between gap-3 rounded-lg border border-slate-200 bg-white px-3 py-3 text-sm font-black text-slate-800">
            自动判断隐式外部变数
            <input
              type="checkbox"
              checked={autoAdjudication}
              disabled={mutation.isPending}
              onChange={(event) => setAutoAdjudication(event.target.checked)}
              className="h-4 w-4 accent-violet-600"
            />
          </label>
          <NarrativeOutcomeWeightsEditor
            value={weights}
            definitions={module.outcomeDefinitions ?? []}
            disabled={mutation.isPending}
            onChange={setWeights}
          />
        </div>
      ) : null}

      {module.moduleName === RP_MODULE_NAME.DICE ? (
        <label className="mt-4 block text-xs font-black text-slate-600">
          手动 /check_dc 默认 DC
          <input
            type="number"
            min={1}
            step={1}
            value={defaultDC}
            disabled={mutation.isPending}
            onChange={(event) => setDefaultDC(Number(event.target.value))}
            className="mt-2 h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm outline-none focus:border-violet-300"
          />
        </label>
      ) : null}

      {error ? <p className="mt-3 text-xs font-semibold text-rose-700">{error}</p> : null}
      <div className="mt-4 flex justify-end gap-2">
        <button
          type="button"
          disabled={mutation.isPending}
          onClick={() => {
            const system = module.systemConfig
            setAutoAdjudication(system.auto_adjudication_enabled ?? true)
            setWeights(system.weights ? copyNarrativeOutcomeWeights(system.weights) : weights)
            setDefaultDC(system.default_dc ?? 12)
            mutation.mutate({ enabled, config: {} })
          }}
          className="inline-flex h-9 items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 text-xs font-black text-slate-600 disabled:opacity-50"
        >
          <RotateCcw size={14} /> 恢复系统配置
        </button>
        <button
          type="button"
          disabled={!valid || mutation.isPending}
          onClick={() => mutation.mutate({ enabled, config })}
          className="inline-flex h-9 items-center gap-2 rounded-lg bg-violet-600 px-3 text-xs font-black text-white disabled:bg-slate-300"
        >
          {mutation.isPending ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />} 保存
        </button>
      </div>
    </article>
  )
}

export function StoryRPModulesPanel({ workspace, storyId }: { workspace: string; storyId: number }) {
  const queryClient = useQueryClient()
  const queryKey = useMemo(() => ['story-rp-modules', workspace, storyId] as const, [workspace, storyId])
  const query = useQuery({ queryKey, queryFn: () => getStoryRPModules(workspace, storyId) })

  if (query.isError) {
    return <section className="rounded-lg border border-rose-200 bg-rose-50 px-5 py-5 text-sm font-semibold text-rose-700">RP Modules 加载失败：{query.error instanceof Error ? query.error.message : '未知错误'}</section>
  }
  if (query.isLoading || !query.data) {
    return <section className="rounded-lg border border-slate-200 bg-white px-5 py-8 text-center text-sm font-semibold text-slate-500 shadow-sm"><Loader2 size={18} className="mx-auto mb-2 animate-spin" />正在读取 RP Modules</section>
  }

  return (
    <section className="rounded-lg border border-slate-200 bg-white shadow-sm">
      <header className="border-b border-slate-200 px-5 py-4">
        <h2 className="flex items-center gap-2 text-lg font-black text-slate-950"><Boxes size={18} className="text-violet-600" />RP Modules</h2>
        <p className="mt-1 text-sm leading-6 text-slate-500">Story 决定会话可用能力上限；配置从下一 turn 生效。</p>
      </header>
      <div className="grid gap-4 p-5">
        {query.data.modules.map((module) => (
          <StoryModuleCard
            key={module.moduleName}
            module={module}
            workspace={workspace}
            storyId={storyId}
            onSaved={(saved) => {
              queryClient.setQueryData(queryKey, {
                modules: query.data.modules.map((item) => item.moduleName === saved.moduleName ? saved : item),
              })
              queryClient.invalidateQueries({ queryKey: ['session-rp-modules'] })
            }}
          />
        ))}
      </div>
    </section>
  )
}
