'use client'

import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2, Save, Trash2 } from 'lucide-react'
import { Dialog } from '@/components/common/Dialog'
import { NarrativeOutcomeWeightsEditor } from '@/components/narrative-outcome/NarrativeOutcomeWeightsEditor'
import {
  clearSessionRPModuleOverride,
  getSessionRPModules,
  patchSessionRPModule,
} from '@/lib/api/rpModules'
import {
  copyNarrativeOutcomeWeights,
  validNarrativeOutcomeWeights,
  type NarrativeOutcomeWeights,
} from '@/types/narrativeOutcome'
import { RP_MODULE_NAME, type RPModuleConfig, type RPModuleConfigValues } from '@/types/rpModules'

type EnabledMode = 'inherit' | 'enabled' | 'disabled'

function SessionModuleCard({
  module,
  sessionId,
  onChanged,
  showToast,
}: {
  module: RPModuleConfig
  sessionId: string
  onChanged: () => void
  showToast: (message: string) => void
}) {
  const [enabledMode, setEnabledMode] = useState<EnabledMode>(
    module.sessionEnabledOverride === null ? 'inherit' : module.sessionEnabledOverride ? 'enabled' : 'disabled',
  )
  const [configOverride, setConfigOverride] = useState(Object.keys(module.sessionConfig).length > 0)
  const [autoAdjudication, setAutoAdjudication] = useState(module.effectiveConfig.auto_adjudication_enabled ?? true)
  const [weights, setWeights] = useState<NarrativeOutcomeWeights | null>(
    module.effectiveConfig.weights ? copyNarrativeOutcomeWeights(module.effectiveConfig.weights) : null,
  )
  const [defaultDC, setDefaultDC] = useState(module.effectiveConfig.default_dc ?? 12)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setEnabledMode(module.sessionEnabledOverride === null ? 'inherit' : module.sessionEnabledOverride ? 'enabled' : 'disabled')
    setConfigOverride(Object.keys(module.sessionConfig).length > 0)
    setAutoAdjudication(module.effectiveConfig.auto_adjudication_enabled ?? true)
    setWeights(module.effectiveConfig.weights ? copyNarrativeOutcomeWeights(module.effectiveConfig.weights) : null)
    setDefaultDC(module.effectiveConfig.default_dc ?? 12)
  }, [module])

  const saveMutation = useMutation({
    mutationFn: () => {
      const config: RPModuleConfigValues = !configOverride
        ? {}
        : module.moduleName === RP_MODULE_NAME.NARRATIVE_OUTCOME
          ? { auto_adjudication_enabled: autoAdjudication, ...(weights ? { weights } : {}) }
          : { default_dc: defaultDC }
      return patchSessionRPModule(sessionId, module.moduleName, {
        enabled: enabledMode === 'inherit' ? null : enabledMode === 'enabled',
        config,
      })
    },
    onSuccess: () => {
      setError(null)
      onChanged()
      showToast(`${module.displayName}会话覆盖已保存`)
    },
    onError: (reason) => setError(reason instanceof Error ? reason.message : '会话覆盖保存失败'),
  })
  const clearMutation = useMutation({
    mutationFn: () => clearSessionRPModuleOverride(sessionId, module.moduleName),
    onSuccess: () => {
      setError(null)
      onChanged()
      showToast(`${module.displayName}已恢复继承 Story`)
    },
    onError: (reason) => setError(reason instanceof Error ? reason.message : '清除覆盖失败'),
  })
  const pending = saveMutation.isPending || clearMutation.isPending
  const valid = !configOverride || (
    module.moduleName === RP_MODULE_NAME.NARRATIVE_OUTCOME
      ? Boolean(weights && validNarrativeOutcomeWeights(weights))
      : Number.isInteger(defaultDC) && defaultDC > 0
  )

  return (
    <article className="rounded-lg border border-slate-200 bg-slate-50 p-4">
      <div>
        <h3 className="text-sm font-black text-slate-950">{module.displayName}</h3>
        <p className="mt-1 text-xs font-semibold leading-5 text-slate-500">{module.description}</p>
      </div>
      <div className="mt-4 grid grid-cols-3 gap-2">
        {(['inherit', 'enabled', 'disabled'] as EnabledMode[]).map((mode) => (
          <button
            key={mode}
            type="button"
            disabled={pending}
            onClick={() => setEnabledMode(mode)}
            className={`h-9 rounded-lg border text-xs font-black ${enabledMode === mode ? 'border-violet-500 bg-violet-50 text-violet-700' : 'border-slate-200 bg-white text-slate-500'}`}
          >
            {mode === 'inherit' ? '继承 Story' : mode === 'enabled' ? '会话启用' : '会话停用'}
          </button>
        ))}
      </div>
      <label className="mt-4 flex items-center gap-2 text-xs font-black text-slate-700">
        <input type="checkbox" checked={configOverride} disabled={pending} onChange={(event) => setConfigOverride(event.target.checked)} className="h-4 w-4 accent-violet-600" />
        覆盖本模块配置
      </label>

      {configOverride && module.moduleName === RP_MODULE_NAME.NARRATIVE_OUTCOME && weights ? (
        <div className="mt-4 space-y-4">
          <label className="flex items-center justify-between rounded-lg border border-slate-200 bg-white px-3 py-3 text-sm font-black text-slate-800">
            自动判断隐式外部变数
            <input type="checkbox" checked={autoAdjudication} disabled={pending} onChange={(event) => setAutoAdjudication(event.target.checked)} className="h-4 w-4 accent-violet-600" />
          </label>
          <NarrativeOutcomeWeightsEditor value={weights} definitions={module.outcomeDefinitions ?? []} disabled={pending} onChange={setWeights} />
        </div>
      ) : null}
      {configOverride && module.moduleName === RP_MODULE_NAME.DICE ? (
        <label className="mt-4 block text-xs font-black text-slate-600">
          手动 /check_dc 默认 DC
          <input type="number" min={1} step={1} value={defaultDC} disabled={pending} onChange={(event) => setDefaultDC(Number(event.target.value))} className="mt-2 h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm outline-none" />
        </label>
      ) : null}
      {!module.storyEnabled ? <p className="mt-3 text-xs font-semibold text-amber-700">Story 已停用该模块，会话不能越过 Story 能力上限重新启用。</p> : null}
      {error ? <p className="mt-3 text-xs font-semibold text-rose-700">{error}</p> : null}
      <div className="mt-4 flex justify-end gap-2">
        <button type="button" disabled={pending || (module.sessionEnabledOverride === null && Object.keys(module.sessionConfig).length === 0)} onClick={() => clearMutation.mutate()} className="inline-flex h-9 items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 text-xs font-black text-slate-600 disabled:opacity-50"><Trash2 size={14} />清除覆盖</button>
        <button type="button" disabled={pending || !valid} onClick={() => saveMutation.mutate()} className="inline-flex h-9 items-center gap-2 rounded-lg bg-violet-600 px-3 text-xs font-black text-white disabled:bg-slate-300">{pending ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}保存</button>
      </div>
    </article>
  )
}

export function SessionRPModulesDialog({
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
  const queryKey = ['session-rp-modules', sessionId] as const
  const query = useQuery({ queryKey, queryFn: () => getSessionRPModules(sessionId), enabled: open })
  if (!open) return null

  return (
    <Dialog title="会话 RP Modules" onClose={onClose} size="3xl" overlayClassName="z-[70]">
      <div className="max-h-[72vh] overflow-y-auto px-6 py-5">
        {query.isError ? (
          <p className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-4 text-sm font-semibold text-rose-700">加载失败：{query.error instanceof Error ? query.error.message : '未知错误'}</p>
        ) : query.isLoading || !query.data ? (
          <div className="py-10 text-center text-sm font-semibold text-slate-500"><Loader2 size={18} className="mx-auto mb-2 animate-spin" />正在读取 RP Modules</div>
        ) : (
          <div className="grid gap-4">
            {query.data.modules.map((module) => (
              <SessionModuleCard
                key={module.moduleName}
                module={module}
                sessionId={sessionId}
                showToast={showToast}
                onChanged={() => queryClient.invalidateQueries({ queryKey })}
              />
            ))}
          </div>
        )}
      </div>
      <footer className="flex justify-end border-t border-slate-200 bg-slate-50 px-6 py-4">
        <button type="button" onClick={onClose} className="h-10 rounded-lg border border-slate-200 bg-white px-4 text-sm font-black text-slate-600">关闭</button>
      </footer>
    </Dialog>
  )
}
