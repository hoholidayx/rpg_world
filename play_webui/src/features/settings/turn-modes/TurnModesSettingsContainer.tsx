'use client'

import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2, Save } from 'lucide-react'
import { listWorkspaceTurnModes, updateWorkspaceTurnMode } from '@/lib/api/sessionComposer'
import type { InputMode } from '@/types/command'
import type { WorkspaceTurnMode } from '@/types/sessionComposer'

type ModeDraft = { shortName: string; prompt: string }

const modeLabels: Record<InputMode, string> = {
  ic: 'IC · 角色内',
  ooc: 'OOC · 场外',
  gm: 'GM · 主持',
}

export function TurnModesSettingsContainer({ workspaceId }: { workspaceId: string | null }) {
  const queryClient = useQueryClient()
  const [drafts, setDrafts] = useState<Partial<Record<InputMode, ModeDraft>>>({})
  const [message, setMessage] = useState('')
  const modesQuery = useQuery({
    queryKey: ['play-workspace-turn-modes', workspaceId],
    enabled: Boolean(workspaceId),
    queryFn: () => listWorkspaceTurnModes(workspaceId ?? ''),
  })

  useEffect(() => {
    if (!modesQuery.data) return
    setDrafts(Object.fromEntries(modesQuery.data.map((item) => [
      item.mode,
      { shortName: item.shortName, prompt: item.prompt },
    ])) as Record<InputMode, ModeDraft>)
  }, [modesQuery.data])

  const updateMutation = useMutation({
    mutationFn: ({ mode, draft }: { mode: InputMode; draft: ModeDraft }) => (
      updateWorkspaceTurnMode(workspaceId ?? '', mode, draft)
    ),
    onSuccess: async (updated) => {
      await queryClient.invalidateQueries({ queryKey: ['play-workspace-turn-modes', workspaceId] })
      await queryClient.invalidateQueries({ queryKey: ['play-session-composer'] })
      setMessage(`${updated.mode.toUpperCase()} 配置已保存。`)
    },
    onError: (error) => setMessage(error instanceof Error ? error.message : '保存失败'),
  })

  if (!workspaceId) {
    return <section className="rounded-xl border border-dashed border-slate-300 bg-white px-6 py-16 text-center font-semibold text-slate-400">请选择 Workspace</section>
  }

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      <header className="mb-6">
        <h1 className="text-2xl font-black text-slate-950">IC / OOC / GM 模式</h1>
        <p className="mt-2 text-sm font-semibold leading-6 text-slate-500">
          mode ID 固定不可扩展；这里只编辑简短中文名和本轮模式 prompt。OOC 的状态写入禁用由 Core 强制，prompt 无法重新开启。
        </p>
      </header>
      {modesQuery.isLoading ? (
        <p className="flex items-center gap-2 py-10 text-sm font-semibold text-slate-400"><Loader2 size={16} className="animate-spin" />加载模式配置</p>
      ) : (
        <div className="grid gap-4 xl:grid-cols-3">
          {(modesQuery.data ?? []).map((item: WorkspaceTurnMode) => {
            const draft = drafts[item.mode] ?? { shortName: item.shortName, prompt: item.prompt }
            const pending = updateMutation.isPending && updateMutation.variables?.mode === item.mode
            return (
              <article key={item.mode} className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                <div className="mb-4 flex items-center justify-between gap-3">
                  <h2 className="font-black text-slate-950">{modeLabels[item.mode]}</h2>
                  <code className="rounded bg-white px-2 py-1 text-xs font-black text-violet-700">{item.mode}</code>
                </div>
                <label className="block">
                  <span className="mb-2 block text-xs font-black uppercase text-slate-500">简短中文名</span>
                  <input
                    value={draft.shortName}
                    onChange={(event) => setDrafts((current) => ({
                      ...current,
                      [item.mode]: { ...draft, shortName: event.target.value },
                    }))}
                    className="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm font-bold outline-none focus:border-violet-300"
                  />
                </label>
                <label className="mt-4 block">
                  <span className="mb-2 block text-xs font-black uppercase text-slate-500">Prompt</span>
                  <textarea
                    value={draft.prompt}
                    onChange={(event) => setDrafts((current) => ({
                      ...current,
                      [item.mode]: { ...draft, prompt: event.target.value },
                    }))}
                    className="min-h-44 w-full resize-y rounded-lg border border-slate-200 bg-white px-3 py-3 font-mono text-xs leading-6 outline-none focus:border-violet-300"
                  />
                </label>
                <button
                  type="button"
                  disabled={!draft.shortName.trim() || updateMutation.isPending}
                  onClick={() => updateMutation.mutate({ mode: item.mode, draft })}
                  className="mt-4 inline-flex h-10 w-full items-center justify-center gap-2 rounded-lg bg-slate-950 text-sm font-black text-white hover:bg-violet-700 disabled:opacity-50"
                >
                  {pending ? <Loader2 size={15} className="animate-spin" /> : <Save size={15} />}
                  保存 {item.mode.toUpperCase()}
                </button>
              </article>
            )
          })}
        </div>
      )}
      {modesQuery.isError ? <p className="mt-4 text-sm font-semibold text-rose-600">模式配置加载失败。</p> : null}
      {message ? <p role="status" className="mt-4 rounded-lg bg-slate-50 px-3 py-2 text-xs font-semibold text-slate-500">{message}</p> : null}
    </section>
  )
}
