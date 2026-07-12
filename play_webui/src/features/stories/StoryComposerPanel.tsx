'use client'

import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2, Plus, Save, Trash2 } from 'lucide-react'
import {
  createStoryQuickReply,
  deleteStoryQuickReply,
  listNarrativeStyles,
  listStoryNarrativeStyles,
  listStoryQuickReplies,
  mountStoryNarrativeStyle,
  setStoryBaseNarrativeStyle,
  unmountStoryNarrativeStyle,
  updateStoryQuickReply,
} from '@/lib/api/sessionComposer'
import type { QuickReplyInput, StoryQuickReply } from '@/types/sessionComposer'

function QuickReplyEditor({
  reply,
  pending,
  onSave,
  onDelete,
}: {
  reply: StoryQuickReply
  pending: boolean
  onSave: (input: QuickReplyInput) => void
  onDelete: () => void
}) {
  const [draft, setDraft] = useState<QuickReplyInput>({
    title: reply.title,
    message: reply.message,
    sortOrder: reply.sortOrder,
    enabled: reply.enabled,
  })
  useEffect(() => {
    setDraft({
      title: reply.title,
      message: reply.message,
      sortOrder: reply.sortOrder,
      enabled: reply.enabled,
    })
  }, [reply])

  return (
    <article className="rounded-lg border border-slate-200 bg-white p-3">
      <div className="grid gap-3 md:grid-cols-[minmax(120px,0.45fr)_minmax(0,1fr)_90px_auto] md:items-center">
        <input
          value={draft.title}
          onChange={(event) => setDraft((current) => ({ ...current, title: event.target.value }))}
          placeholder="标题"
          className="h-10 rounded-lg border border-slate-200 bg-slate-50 px-3 text-sm font-bold outline-none focus:border-violet-300"
        />
        <input
          value={draft.message}
          onChange={(event) => setDraft((current) => ({ ...current, message: event.target.value }))}
          placeholder="发送的消息正文"
          className="h-10 rounded-lg border border-slate-200 bg-slate-50 px-3 text-sm font-semibold outline-none focus:border-violet-300"
        />
        <input
          type="number"
          value={draft.sortOrder}
          onChange={(event) => setDraft((current) => ({ ...current, sortOrder: Number(event.target.value) || 0 }))}
          aria-label="排序"
          className="h-10 rounded-lg border border-slate-200 bg-slate-50 px-3 text-sm font-bold outline-none"
        />
        <label className="flex items-center gap-2 text-xs font-black text-slate-500">
          <input
            type="checkbox"
            checked={draft.enabled}
            onChange={(event) => setDraft((current) => ({ ...current, enabled: event.target.checked }))}
          />
          启用
        </label>
      </div>
      <div className="mt-3 flex justify-end gap-2">
        <button
          type="button"
          disabled={pending || !draft.title.trim() || !draft.message.trim()}
          onClick={() => onSave(draft)}
          className="inline-flex h-9 items-center gap-2 rounded-lg bg-slate-950 px-3 text-xs font-black text-white hover:bg-violet-700 disabled:opacity-50"
        >
          {pending ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />} 保存
        </button>
        <button
          type="button"
          disabled={pending}
          onClick={onDelete}
          className="inline-flex h-9 items-center gap-2 rounded-lg border border-rose-200 px-3 text-xs font-black text-rose-600 hover:bg-rose-50 disabled:opacity-50"
        >
          <Trash2 size={14} /> 删除
        </button>
      </div>
    </article>
  )
}

export function StoryComposerPanel({ workspaceId, storyId }: { workspaceId: string; storyId: number }) {
  const queryClient = useQueryClient()
  const [newReply, setNewReply] = useState<QuickReplyInput>({ title: '', message: '', sortOrder: 0, enabled: true })
  const [message, setMessage] = useState('')
  const libraryQuery = useQuery({
    queryKey: ['play-narrative-styles', workspaceId],
    queryFn: () => listNarrativeStyles(workspaceId),
  })
  const mountsQuery = useQuery({
    queryKey: ['play-story-narrative-styles', workspaceId, storyId],
    queryFn: () => listStoryNarrativeStyles(workspaceId, storyId),
  })
  const repliesQuery = useQuery({
    queryKey: ['play-story-quick-replies', workspaceId, storyId],
    queryFn: () => listStoryQuickReplies(workspaceId, storyId),
  })
  const mounts = useMemo(() => mountsQuery.data ?? [], [mountsQuery.data])
  const mountedByStyle = new Map(mounts.map((mount) => [mount.narrativeStyleId, mount]))

  const invalidateComposer = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['play-story-narrative-styles', workspaceId, storyId] }),
      queryClient.invalidateQueries({ queryKey: ['play-story-quick-replies', workspaceId, storyId] }),
      queryClient.invalidateQueries({ queryKey: ['play-session-composer'] }),
      queryClient.invalidateQueries({ queryKey: ['play-session-context-preview'] }),
    ])
  }

  const mountMutation = useMutation({
    mutationFn: async ({ styleId, mountId }: { styleId: number; mountId?: number }) => {
      if (mountId) return unmountStoryNarrativeStyle(workspaceId, storyId, mountId)
      return mountStoryNarrativeStyle(workspaceId, storyId, styleId)
    },
    onSuccess: invalidateComposer,
    onError: (error) => setMessage(error instanceof Error ? error.message : '风格挂载更新失败'),
  })
  const baseMutation = useMutation({
    mutationFn: (mountId: number | null) => setStoryBaseNarrativeStyle(workspaceId, storyId, mountId),
    onSuccess: invalidateComposer,
    onError: (error) => setMessage(error instanceof Error ? error.message : '基础风格更新失败'),
  })
  const createReplyMutation = useMutation({
    mutationFn: (input: QuickReplyInput) => createStoryQuickReply(workspaceId, storyId, input),
    onSuccess: async () => {
      setNewReply({ title: '', message: '', sortOrder: 0, enabled: true })
      await invalidateComposer()
      setMessage('快速回复已创建。')
    },
    onError: (error) => setMessage(error instanceof Error ? error.message : '快速回复创建失败'),
  })
  const updateReplyMutation = useMutation({
    mutationFn: ({ replyId, input }: { replyId: number; input: QuickReplyInput }) => (
      updateStoryQuickReply(workspaceId, storyId, replyId, input)
    ),
    onSuccess: invalidateComposer,
    onError: (error) => setMessage(error instanceof Error ? error.message : '快速回复保存失败'),
  })
  const deleteReplyMutation = useMutation({
    mutationFn: (replyId: number) => deleteStoryQuickReply(workspaceId, storyId, replyId),
    onSuccess: invalidateComposer,
    onError: (error) => setMessage(error instanceof Error ? error.message : '快速回复删除失败'),
  })

  const loading = libraryQuery.isLoading || mountsQuery.isLoading || repliesQuery.isLoading
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
      <header className="mb-5">
        <h2 className="text-lg font-black text-slate-950">叙事风格与快速回复</h2>
        <p className="mt-1 text-sm font-semibold leading-6 text-slate-500">
          Story 决定可用风格、唯一基础风格与快速回复；一次性风格由 Session Composer 在发送时选择。
        </p>
      </header>
      {loading ? <p className="flex items-center gap-2 py-5 text-sm font-semibold text-slate-400"><Loader2 size={16} className="animate-spin" />加载 Composer 配置</p> : (
        <div className="space-y-6">
          <div>
            <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
              <h3 className="text-xs font-black uppercase text-slate-500">Story 风格挂载</h3>
              <label className="flex items-center gap-2 text-xs font-black text-slate-500">
                基础风格
                <select
                  value={mounts.find((mount) => mount.isBase)?.mountId ?? ''}
                  disabled={baseMutation.isPending}
                  onChange={(event) => baseMutation.mutate(event.target.value ? Number(event.target.value) : null)}
                  className="h-9 rounded-lg border border-slate-200 bg-slate-50 px-3 text-xs font-bold"
                >
                  <option value="">无额外风格</option>
                  {mounts.map((mount) => <option key={mount.mountId} value={mount.mountId}>{mount.name}</option>)}
                </select>
              </label>
            </div>
            <div className="grid gap-2 md:grid-cols-2">
              {(libraryQuery.data ?? []).map((style) => {
                const mount = mountedByStyle.get(style.id)
                const pending = mountMutation.isPending && mountMutation.variables?.styleId === style.id
                return (
                  <article key={style.id} className="flex items-center justify-between gap-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-3">
                    <span className="min-w-0">
                      <strong className="block truncate text-sm text-slate-900">{style.name}</strong>
                      <span className="mt-1 block truncate text-xs font-semibold text-slate-400">{style.prompt || '空 prompt'}</span>
                    </span>
                    <button
                      type="button"
                      disabled={mountMutation.isPending}
                      onClick={() => mountMutation.mutate({ styleId: style.id, mountId: mount?.mountId })}
                      className={`h-9 shrink-0 rounded-lg px-3 text-xs font-black ${mount ? 'border border-rose-200 text-rose-600 hover:bg-rose-50' : 'bg-violet-600 text-white hover:bg-violet-700'} disabled:opacity-50`}
                    >
                      {pending ? '处理中' : mount ? '卸载' : '挂载'}
                    </button>
                  </article>
                )
              })}
              {!libraryQuery.data?.length ? <p className="rounded-lg border border-dashed border-slate-200 px-4 py-8 text-center text-sm font-semibold text-slate-400">Workspace 风格库为空</p> : null}
            </div>
          </div>

          <div>
            <h3 className="mb-3 text-xs font-black uppercase text-slate-500">快速回复</h3>
            <div className="space-y-2">
              {(repliesQuery.data ?? []).map((reply) => (
                <QuickReplyEditor
                  key={reply.id}
                  reply={reply}
                  pending={(updateReplyMutation.isPending && updateReplyMutation.variables?.replyId === reply.id) || deleteReplyMutation.isPending}
                  onSave={(input) => updateReplyMutation.mutate({ replyId: reply.id, input })}
                  onDelete={() => {
                    if (window.confirm(`删除快速回复“${reply.title}”？`)) deleteReplyMutation.mutate(reply.id)
                  }}
                />
              ))}
              <article className="rounded-lg border border-dashed border-violet-200 bg-violet-50/50 p-3">
                <div className="grid gap-3 md:grid-cols-[minmax(120px,0.45fr)_minmax(0,1fr)_90px_auto] md:items-center">
                  <input value={newReply.title} onChange={(event) => setNewReply((current) => ({ ...current, title: event.target.value }))} placeholder="新标题" className="h-10 rounded-lg border border-slate-200 bg-white px-3 text-sm font-bold outline-none" />
                  <input value={newReply.message} onChange={(event) => setNewReply((current) => ({ ...current, message: event.target.value }))} placeholder="快速消息正文" className="h-10 rounded-lg border border-slate-200 bg-white px-3 text-sm font-semibold outline-none" />
                  <input type="number" value={newReply.sortOrder} onChange={(event) => setNewReply((current) => ({ ...current, sortOrder: Number(event.target.value) || 0 }))} aria-label="新快速回复排序" className="h-10 rounded-lg border border-slate-200 bg-white px-3 text-sm font-bold outline-none" />
                  <button
                    type="button"
                    disabled={createReplyMutation.isPending || !newReply.title.trim() || !newReply.message.trim()}
                    onClick={() => createReplyMutation.mutate(newReply)}
                    className="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-violet-600 px-3 text-xs font-black text-white hover:bg-violet-700 disabled:opacity-50"
                  >
                    {createReplyMutation.isPending ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />} 添加
                  </button>
                </div>
              </article>
            </div>
          </div>
        </div>
      )}
      {message ? <p role="status" className="mt-4 rounded-lg bg-slate-50 px-3 py-2 text-xs font-semibold text-slate-500">{message}</p> : null}
    </section>
  )
}
