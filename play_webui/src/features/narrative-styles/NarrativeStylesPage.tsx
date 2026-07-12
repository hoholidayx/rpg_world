'use client'

import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2, Plus, Save, Trash2, WandSparkles } from 'lucide-react'
import { AppShell, useAppShell } from '@/features/layout/AppShell'
import {
  createNarrativeStyle,
  deleteNarrativeStyle,
  listNarrativeStyles,
  updateNarrativeStyle,
} from '@/lib/api/sessionComposer'
import type { NarrativeStyle, NarrativeStyleInput } from '@/types/sessionComposer'

const emptyDraft: NarrativeStyleInput = { name: '', prompt: '', sortOrder: 0 }

function NarrativeStylesContent() {
  const { currentWorkspace } = useAppShell()
  const queryClient = useQueryClient()
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [draft, setDraft] = useState<NarrativeStyleInput>(emptyDraft)
  const [message, setMessage] = useState('')

  const stylesQuery = useQuery({
    queryKey: ['play-narrative-styles', currentWorkspace],
    enabled: Boolean(currentWorkspace),
    queryFn: () => listNarrativeStyles(currentWorkspace ?? ''),
  })
  const styles = useMemo(() => stylesQuery.data ?? [], [stylesQuery.data])
  const selected = styles.find((style) => style.id === selectedId) ?? null

  useEffect(() => {
    if (selectedId !== null && !styles.some((style) => style.id === selectedId)) {
      setSelectedId(null)
    }
  }, [selectedId, styles])

  useEffect(() => {
    setDraft(selected
      ? { name: selected.name, prompt: selected.prompt, sortOrder: selected.sortOrder }
      : emptyDraft)
  }, [selected])

  const invalidate = async () => {
    await queryClient.invalidateQueries({ queryKey: ['play-narrative-styles', currentWorkspace] })
  }

  const createMutation = useMutation({
    mutationFn: (input: NarrativeStyleInput) => createNarrativeStyle(currentWorkspace ?? '', input),
    onSuccess: async (created) => {
      await invalidate()
      setSelectedId(created.id)
      setMessage('风格已创建；既有 Story 不会自动挂载。')
    },
    onError: (error) => setMessage(error instanceof Error ? error.message : '创建失败'),
  })
  const updateMutation = useMutation({
    mutationFn: ({ id, input }: { id: number; input: NarrativeStyleInput }) => (
      updateNarrativeStyle(currentWorkspace ?? '', id, input)
    ),
    onSuccess: async () => {
      await invalidate()
      setMessage('风格已保存。')
    },
    onError: (error) => setMessage(error instanceof Error ? error.message : '保存失败'),
  })
  const deleteMutation = useMutation({
    mutationFn: (id: number) => deleteNarrativeStyle(currentWorkspace ?? '', id),
    onSuccess: async () => {
      setSelectedId(null)
      await invalidate()
      setMessage('风格已删除；相关 Story 挂载已同步移除。')
    },
    onError: (error) => setMessage(error instanceof Error ? error.message : '删除失败'),
  })

  const pending = createMutation.isPending || updateMutation.isPending || deleteMutation.isPending
  const validDraft = Boolean(draft.name.trim())

  return (
    <div className="mx-auto max-w-[1500px] px-5 py-8 xl:px-7">
      <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="mb-2 flex items-center gap-2 text-sm font-black text-violet-600">
            <WandSparkles size={17} /> Workspace 内容资产
          </div>
          <h1 className="text-3xl font-black text-slate-950">叙事风格库</h1>
          <p className="mt-2 text-sm font-semibold leading-6 text-slate-500">
            风格 prompt 由 Workspace 统一维护；Story 决定挂载范围和唯一基础风格。
          </p>
        </div>
        <button
          type="button"
          onClick={() => setSelectedId(null)}
          disabled={!currentWorkspace || pending}
          className="inline-flex h-10 items-center gap-2 rounded-lg bg-violet-600 px-4 text-sm font-black text-white transition hover:bg-violet-700 disabled:opacity-50"
        >
          <Plus size={16} /> 新建风格
        </button>
      </header>

      {!currentWorkspace ? (
        <div className="rounded-lg border border-dashed border-slate-300 bg-white px-6 py-16 text-center font-semibold text-slate-400">请选择 Workspace</div>
      ) : (
        <div className="grid gap-5 lg:grid-cols-[360px_minmax(0,1fr)]">
          <section className="rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
            {stylesQuery.isLoading ? (
              <p className="flex items-center gap-2 px-3 py-6 text-sm font-semibold text-slate-400"><Loader2 size={16} className="animate-spin" />加载风格库</p>
            ) : styles.length ? styles.map((style: NarrativeStyle) => (
              <button
                key={style.id}
                type="button"
                onClick={() => setSelectedId(style.id)}
                className={`mb-2 w-full rounded-lg border px-4 py-3 text-left transition ${selectedId === style.id ? 'border-violet-300 bg-violet-50' : 'border-slate-200 hover:border-violet-200'}`}
              >
                <span className="block truncate text-sm font-black text-slate-900">{style.name}</span>
                <span className="mt-1 block truncate text-xs font-semibold text-slate-400">排序 {style.sortOrder} · v{style.version}</span>
              </button>
            )) : (
              <p className="px-4 py-12 text-center text-sm font-semibold text-slate-400">暂无叙事风格</p>
            )}
          </section>

          <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
            <div className="mb-5 flex items-center justify-between gap-3">
              <div>
                <h2 className="text-lg font-black text-slate-950">{selected ? `编辑 · ${selected.name}` : '创建叙事风格'}</h2>
                <p className="mt-1 text-xs font-semibold text-slate-400">删除基础风格时，Story 自动回退为无额外风格。</p>
              </div>
              {selected ? (
                <button
                  type="button"
                  onClick={() => {
                    if (window.confirm(`删除叙事风格“${selected.name}”？`)) deleteMutation.mutate(selected.id)
                  }}
                  disabled={pending}
                  className="inline-flex h-9 items-center gap-2 rounded-lg border border-rose-200 px-3 text-xs font-black text-rose-600 hover:bg-rose-50 disabled:opacity-50"
                >
                  <Trash2 size={14} /> 删除
                </button>
              ) : null}
            </div>
            <div className="grid gap-4">
              <label>
                <span className="mb-2 block text-xs font-black uppercase text-slate-500">名称</span>
                <input
                  value={draft.name}
                  onChange={(event) => setDraft((current) => ({ ...current, name: event.target.value }))}
                  className="h-11 w-full rounded-lg border border-slate-200 bg-slate-50 px-3 text-sm font-bold outline-none focus:border-violet-300 focus:ring-4 focus:ring-violet-100"
                />
              </label>
              <label>
                <span className="mb-2 block text-xs font-black uppercase text-slate-500">排序</span>
                <input
                  type="number"
                  value={draft.sortOrder}
                  onChange={(event) => setDraft((current) => ({ ...current, sortOrder: Number(event.target.value) || 0 }))}
                  className="h-11 w-full rounded-lg border border-slate-200 bg-slate-50 px-3 text-sm font-bold outline-none focus:border-violet-300"
                />
              </label>
              <label>
                <span className="mb-2 block text-xs font-black uppercase text-slate-500">Prompt</span>
                <textarea
                  value={draft.prompt}
                  onChange={(event) => setDraft((current) => ({ ...current, prompt: event.target.value }))}
                  className="min-h-56 w-full resize-y rounded-lg border border-slate-200 bg-slate-50 px-3 py-3 font-mono text-sm leading-7 outline-none focus:border-violet-300 focus:ring-4 focus:ring-violet-100"
                />
              </label>
              <button
                type="button"
                disabled={!validDraft || pending}
                onClick={() => selected
                  ? updateMutation.mutate({ id: selected.id, input: draft })
                  : createMutation.mutate(draft)}
                className="inline-flex h-11 items-center justify-center gap-2 rounded-lg bg-slate-950 px-5 text-sm font-black text-white hover:bg-violet-700 disabled:opacity-50"
              >
                {pending ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
                {selected ? '保存风格' : '创建风格'}
              </button>
              {message ? <p role="status" className="rounded-lg bg-slate-50 px-3 py-2 text-xs font-semibold text-slate-500">{message}</p> : null}
            </div>
          </section>
        </div>
      )}
    </div>
  )
}

export function NarrativeStylesPage() {
  return <AppShell><NarrativeStylesContent /></AppShell>
}
