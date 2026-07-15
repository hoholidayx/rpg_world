'use client'

import { useEffect, useMemo, useState } from 'react'
import {
  Ban,
  Check,
  ImagePlus,
  Images,
  Loader2,
  RefreshCcw,
  RotateCcw,
  Square,
  Trash2,
  WandSparkles,
  Wallpaper,
} from 'lucide-react'
import { ConfirmDialog, Dialog } from '@/components/common/Dialog'
import { mediaAssetContentUrl } from '@/lib/api/media'
import { cn } from '@/lib/utils/cn'
import {
  MEDIA_ASPECT_RATIOS,
  type MediaBrief,
  type MediaGalleryItem,
  type MediaJob,
  type VisualBrief,
} from '@/types/media'
import type { SessionMediaController } from './hooks/useSessionMedia'

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : '未知错误'
}

function statusLabel(status: MediaJob['status']) {
  return {
    queued: '排队中',
    running: '生成中',
    cancelling: '取消中',
    succeeded: '已完成',
    failed: '失败',
    cancelled: '已取消',
    interrupted: '服务中断',
  }[status]
}

function jobTone(status: MediaJob['status']) {
  if (status === 'failed' || status === 'interrupted') return 'border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-200'
  if (status === 'cancelled' || status === 'cancelling') return 'border-slate-200 bg-slate-50 text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300'
  return 'border-violet-200 bg-violet-50 text-violet-700 dark:border-violet-500/30 dark:bg-violet-500/10 dark:text-violet-200'
}

function BriefEditor({
  value,
  disabled,
  onChange,
}: {
  value: VisualBrief
  disabled: boolean
  onChange: (next: VisualBrief) => void
}) {
  const set = <Key extends keyof VisualBrief,>(key: Key, fieldValue: VisualBrief[Key]) => {
    onChange({ ...value, [key]: fieldValue })
  }
  const textFields: Array<{ key: Exclude<keyof VisualBrief, 'subjects' | 'aspectRatio'>; label: string; rows?: number }> = [
    { key: 'sceneDescription', label: '场景描述', rows: 4 },
    { key: 'environment', label: '环境' },
    { key: 'action', label: '动作' },
    { key: 'composition', label: '构图' },
    { key: 'moodLighting', label: '氛围与光线' },
    { key: 'style', label: '视觉风格' },
    { key: 'negativeConstraints', label: '负面约束', rows: 2 },
  ]

  return (
    <div className="space-y-3">
      {textFields.map((field) => (
        <label key={field.key} className="block text-xs font-black text-slate-600 dark:text-slate-300">
          {field.label}
          <textarea
            value={value[field.key]}
            rows={field.rows ?? 2}
            disabled={disabled}
            onChange={(event) => set(field.key, event.target.value)}
            className="mt-1.5 w-full resize-y rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-semibold leading-5 text-slate-800 outline-none transition focus:border-violet-400 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
          />
        </label>
      ))}
      <label className="block text-xs font-black text-slate-600 dark:text-slate-300">
        主体（逗号分隔）
        <input
          value={value.subjects.join(', ')}
          disabled={disabled}
          onChange={(event) => set('subjects', event.target.value.split(',').map((item) => item.trim()).filter(Boolean))}
          className="mt-1.5 h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-800 outline-none transition focus:border-violet-400 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
        />
      </label>
      <label className="block text-xs font-black text-slate-600 dark:text-slate-300">
        画幅
        <select
          value={value.aspectRatio}
          disabled={disabled}
          onChange={(event) => set('aspectRatio', event.target.value as VisualBrief['aspectRatio'])}
          className="mt-1.5 h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm font-black text-slate-800 outline-none dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
        >
          {MEDIA_ASPECT_RATIOS.map((ratio) => <option key={ratio} value={ratio}>{ratio}</option>)}
        </select>
      </label>
    </div>
  )
}

function GalleryCard({
  sessionId,
  item,
  backgroundAssetId,
  pending,
  onSetBackground,
  onClearBackground,
  onRegenerate,
  onDelete,
}: {
  sessionId: string
  item: MediaGalleryItem
  backgroundAssetId: string | null
  pending: boolean
  onSetBackground: () => void
  onClearBackground: () => void
  onRegenerate: () => void
  onDelete: () => void
}) {
  const isBackground = backgroundAssetId === item.assetId
  return (
    <article className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-700 dark:bg-slate-900 dark:shadow-black/30">
      <div className="relative aspect-video overflow-hidden bg-slate-100 dark:bg-slate-800">
        <img
          src={mediaAssetContentUrl(sessionId, item.assetId)}
          alt={item.visualBrief.sceneDescription}
          className="h-full w-full object-cover transition duration-300 hover:scale-[1.03]"
        />
        <div className="absolute left-2 top-2 flex gap-1.5">
          {isBackground ? <span className="rounded-full bg-teal-500 px-2.5 py-1 text-[10px] font-black text-white shadow">当前背景</span> : null}
          {item.source.stale ? <span className="rounded-full bg-amber-500 px-2.5 py-1 text-[10px] font-black text-white shadow">来源已变化</span> : null}
        </div>
      </div>
      <div className="p-3">
        <p className="line-clamp-2 text-sm font-black leading-5 text-slate-900 dark:text-slate-100">{item.visualBrief.sceneDescription}</p>
        <p className="mt-1 text-[11px] font-semibold text-slate-400">turn {item.source.startTurnId}–{item.source.endTurnId} · {item.visualBrief.aspectRatio}</p>
        <div className="mt-3 grid grid-cols-2 gap-2">
          <button
            type="button"
            disabled={pending}
            onClick={isBackground ? onClearBackground : onSetBackground}
            className="inline-flex h-9 items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white text-xs font-black text-slate-600 transition hover:border-violet-300 hover:text-violet-700 disabled:opacity-50 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-300"
          >
            {isBackground ? <Ban size={14} /> : <Wallpaper size={14} />}
            {isBackground ? '清除背景' : '设为背景'}
          </button>
          <button
            type="button"
            disabled={pending || !item.jobId}
            onClick={onRegenerate}
            className="inline-flex h-9 items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white text-xs font-black text-slate-600 transition hover:border-violet-300 hover:text-violet-700 disabled:opacity-50 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-300"
          >
            <RefreshCcw size={14} />再生成
          </button>
        </div>
        <button
          type="button"
          disabled={pending}
          onClick={onDelete}
          className="mt-2 inline-flex h-8 w-full items-center justify-center gap-2 rounded-lg text-xs font-black text-rose-600 transition hover:bg-rose-50 disabled:opacity-50 dark:text-rose-300 dark:hover:bg-rose-500/10"
        >
          <Trash2 size={13} />删除资产
        </button>
      </div>
    </article>
  )
}

export function SessionMediaGallery({
  open,
  sessionId,
  media,
  onClose,
}: {
  open: boolean
  sessionId: string
  media: SessionMediaController
  onClose: () => void
}) {
  const turns = media.sourceTurnsQuery.data?.turns ?? []
  const [startTurnId, setStartTurnId] = useState<number | null>(null)
  const [endTurnId, setEndTurnId] = useState<number | null>(null)
  const [providerKey, setProviderKey] = useState<string | null>(null)
  const [briefResult, setBriefResult] = useState<MediaBrief | null>(null)
  const [draftBrief, setDraftBrief] = useState<VisualBrief | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<MediaGalleryItem | null>(null)

  useEffect(() => {
    if (!open || !turns.length) return
    const latest = turns[turns.length - 1].turnId
    setEndTurnId((current) => current !== null && turns.some((turn) => turn.turnId === current) ? current : latest)
    setStartTurnId((current) => current !== null && turns.some((turn) => turn.turnId === current) ? current : latest)
  }, [open, turns])

  useEffect(() => {
    const catalog = media.providersQuery.data
    if (!catalog) return
    setProviderKey((current) => current && catalog.providers.some((provider) => provider.key === current)
      ? current
      : catalog.defaultKey)
  }, [media.providersQuery.data])

  useEffect(() => {
    setBriefResult(null)
    setDraftBrief(null)
    media.briefMutation.reset()
  // Mutation object identity changes between renders; range changes are the intended reset boundary.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [startTurnId, endTurnId])

  const selectedTurns = useMemo(() => {
    if (startTurnId === null || endTurnId === null) return []
    return turns.filter((turn) => turn.turnId >= startTurnId && turn.turnId <= endTurnId)
  }, [endTurnId, startTurnId, turns])
  const selectionCount = startTurnId !== null && endTurnId !== null ? endTurnId - startTurnId + 1 : 0
  const selectionValid = selectionCount >= 1
    && selectionCount <= (media.sourceTurnsQuery.data?.maxTurns ?? 20)
    && selectedTurns.length === selectionCount
  const selectedProvider = media.providersQuery.data?.providers.find((provider) => provider.key === providerKey)
  const backgroundAssetId = media.backgroundQuery.data?.background?.assetId ?? null
  const gallery = media.galleryQuery.data
  const actionPending = media.setBackgroundMutation.isPending
    || media.clearBackgroundMutation.isPending
    || media.retryJobMutation.isPending
    || media.deleteAssetMutation.isPending

  const applyShortcut = (count: number) => {
    if (!turns.length) return
    const endIndex = Math.max(0, turns.findIndex((turn) => turn.turnId === endTurnId))
    const slice = turns.slice(Math.max(0, endIndex - count + 1), endIndex + 1)
    if (!slice.length) return
    setStartTurnId(slice[0].turnId)
    setEndTurnId(slice[slice.length - 1].turnId)
  }

  const createBrief = async () => {
    if (!selectionValid || startTurnId === null || endTurnId === null) return
    try {
      const result = await media.briefMutation.mutateAsync({ startTurnId, endTurnId })
      setBriefResult(result)
      setDraftBrief(result.brief)
    } catch {
      // The mutation error is rendered inline.
    }
  }

  const createJob = async () => {
    if (!briefResult || !draftBrief || !selectedProvider?.available) return
    try {
      await media.createJobMutation.mutateAsync({
        providerKey: selectedProvider.key,
        startTurnId: briefResult.startTurnId,
        endTurnId: briefResult.endTurnId,
        sourceFingerprint: briefResult.sourceFingerprint,
        visualBrief: draftBrief,
      })
    } catch {
      // The mutation error is rendered inline.
    }
  }

  if (!open) return null

  return (
    <>
      <Dialog title="Session 图像工作室" onClose={onClose} size="7xl" overlayClassName="z-[70]" className="flex max-h-[calc(100vh-3rem)] flex-col dark:border-slate-700 dark:bg-slate-950 dark:shadow-black/50">
        <div className="grid min-h-0 flex-1 lg:grid-cols-[390px_minmax(0,1fr)]">
          <aside className="min-h-0 overflow-y-auto border-b border-slate-200 bg-slate-50/70 px-5 py-5 dark:border-slate-800 dark:bg-slate-900/70 lg:border-b-0 lg:border-r">
            <div className="flex items-center gap-3">
              <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-violet-600 text-white shadow-lg shadow-violet-200 dark:shadow-violet-950/50"><WandSparkles size={18} /></span>
              <div>
                <h3 className="text-sm font-black text-slate-950 dark:text-slate-100">从剧情生成图片</h3>
                <p className="mt-0.5 text-xs font-semibold text-slate-400">选段 → 检查简报 → 异步生成</p>
              </div>
            </div>

            {media.providersQuery.isError || media.sourceTurnsQuery.isError ? (
              <p className="mt-4 rounded-lg border border-rose-200 bg-rose-50 px-3 py-3 text-xs font-bold leading-5 text-rose-700 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-200">
                媒体服务暂不可用：{errorMessage(media.providersQuery.error ?? media.sourceTurnsQuery.error)}。聊天与会话功能不受影响。
              </p>
            ) : null}

            <section className="mt-5">
              <div className="flex items-center justify-between gap-3">
                <strong className="text-xs font-black uppercase tracking-wide text-slate-500 dark:text-slate-300">1 · 选择连续 Turn</strong>
                <span className={cn('text-xs font-black', selectionValid ? 'text-teal-600 dark:text-teal-300' : 'text-rose-600 dark:text-rose-300')}>{selectionCount || 0}/20</span>
              </div>
              <div className="mt-2 grid grid-cols-4 gap-2">
                {(media.sourceTurnsQuery.data?.shortcuts ?? [1, 5, 10, 20]).map((count) => (
                  <button key={count} type="button" onClick={() => applyShortcut(count)} disabled={!turns.length} className="h-8 rounded-lg border border-slate-200 bg-white text-xs font-black text-slate-600 transition hover:border-violet-300 hover:text-violet-700 disabled:opacity-40 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-300">{count}</button>
                ))}
              </div>
              <div className="mt-2 grid grid-cols-2 gap-2">
                <label className="text-[11px] font-black text-slate-500 dark:text-slate-300">起始
                  <select value={startTurnId ?? ''} onChange={(event) => setStartTurnId(Number(event.target.value))} className="mt-1 h-9 w-full rounded-lg border border-slate-200 bg-white px-2 text-xs font-black dark:border-slate-700 dark:bg-slate-950">
                    {turns.map((turn) => <option key={turn.turnId} value={turn.turnId}>Turn {turn.turnId}</option>)}
                  </select>
                </label>
                <label className="text-[11px] font-black text-slate-500 dark:text-slate-300">结束
                  <select value={endTurnId ?? ''} onChange={(event) => setEndTurnId(Number(event.target.value))} className="mt-1 h-9 w-full rounded-lg border border-slate-200 bg-white px-2 text-xs font-black dark:border-slate-700 dark:bg-slate-950">
                    {turns.map((turn) => <option key={turn.turnId} value={turn.turnId}>Turn {turn.turnId}</option>)}
                  </select>
                </label>
              </div>
              {!selectionValid && selectionCount ? <p className="mt-2 text-xs font-bold text-rose-600 dark:text-rose-300">只能选择 1–20 个连续且仍存在的已提交 turn。</p> : null}
              <div className="mt-3 max-h-36 space-y-2 overflow-y-auto pr-1">
                {selectedTurns.map((turn) => (
                  <div key={turn.turnId} className="rounded-lg border border-slate-200 bg-white px-3 py-2 dark:border-slate-700 dark:bg-slate-950">
                    <div className="flex justify-between text-[10px] font-black uppercase text-slate-400"><span>Turn {turn.turnId}</span><span>{turn.messageCount} messages</span></div>
                    <p className="mt-1 text-xs font-semibold leading-5 text-slate-600 dark:text-slate-300">{turn.preview || '（空正文）'}</p>
                  </div>
                ))}
              </div>
              <button type="button" disabled={!selectionValid || media.briefMutation.isPending} onClick={() => void createBrief()} className="mt-3 inline-flex h-10 w-full items-center justify-center gap-2 rounded-lg bg-violet-600 text-sm font-black text-white shadow-lg shadow-violet-200 transition hover:bg-violet-700 disabled:bg-slate-300 disabled:shadow-none dark:shadow-violet-950/50 dark:disabled:bg-slate-700">
                {media.briefMutation.isPending ? <Loader2 size={15} className="animate-spin" /> : <ImagePlus size={15} />}生成可编辑简报
              </button>
              {media.briefMutation.isError ? <p className="mt-2 text-xs font-bold text-rose-600 dark:text-rose-300">{errorMessage(media.briefMutation.error)}</p> : null}
            </section>

            {draftBrief ? (
              <section className="mt-6 border-t border-slate-200 pt-5 dark:border-slate-700">
                <strong className="text-xs font-black uppercase tracking-wide text-slate-500 dark:text-slate-300">2 · 检查并编辑简报</strong>
                <div className="mt-3"><BriefEditor value={draftBrief} disabled={media.createJobMutation.isPending} onChange={setDraftBrief} /></div>
                <label className="mt-3 block text-xs font-black text-slate-600 dark:text-slate-300">图片 Provider
                  <select value={providerKey ?? ''} onChange={(event) => setProviderKey(event.target.value)} className="mt-1.5 h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm font-black dark:border-slate-700 dark:bg-slate-950">
                    {(media.providersQuery.data?.providers ?? []).map((provider) => <option key={provider.key} value={provider.key} disabled={!provider.available}>{provider.displayName}{provider.available ? '' : '（不可用）'}</option>)}
                  </select>
                </label>
                {selectedProvider && !selectedProvider.available ? <p className="mt-2 break-words text-xs font-bold text-amber-700 [overflow-wrap:anywhere] dark:text-amber-300">{selectedProvider.reason}</p> : null}
                <button type="button" disabled={!draftBrief.sceneDescription.trim() || !selectedProvider?.available || media.createJobMutation.isPending} onClick={() => void createJob()} className="mt-4 inline-flex h-11 w-full items-center justify-center gap-2 rounded-lg bg-teal-600 text-sm font-black text-white shadow-lg shadow-teal-100 transition hover:bg-teal-700 disabled:bg-slate-300 disabled:shadow-none dark:shadow-teal-950/40 dark:disabled:bg-slate-700">
                  {media.createJobMutation.isPending ? <Loader2 size={16} className="animate-spin" /> : <WandSparkles size={16} />}提交异步生图
                </button>
                {media.createJobMutation.isError ? <p className="mt-2 text-xs font-bold text-rose-600 dark:text-rose-300">{errorMessage(media.createJobMutation.error)}</p> : null}
              </section>
            ) : null}
          </aside>

          <section className="min-h-0 overflow-y-auto px-5 py-5 sm:px-6">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h3 className="flex items-center gap-2 text-base font-black text-slate-950 dark:text-slate-100"><Images size={18} />Session Gallery</h3>
                <p className="mt-1 text-xs font-semibold text-slate-400">图片资产与消息历史分离；来源变化只会标记陈旧，不删除图片。</p>
              </div>
              <button type="button" onClick={() => void media.galleryQuery.refetch()} disabled={media.galleryQuery.isFetching} className="inline-flex h-9 items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 text-xs font-black text-slate-600 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300">
                <RotateCcw size={14} className={media.galleryQuery.isFetching ? 'animate-spin' : ''} />刷新
              </button>
            </div>

            {gallery?.recentJobs.some((job) => job.status !== 'succeeded') ? (
              <div className="mt-4 space-y-2">
                {gallery.recentJobs.filter((job) => job.status !== 'succeeded').slice(0, 8).map((job) => (
                  <div key={job.jobId} className={cn('flex flex-wrap items-center justify-between gap-3 rounded-lg border px-3 py-2.5 text-xs font-bold', jobTone(job.status))}>
                    <span className="min-w-0"><strong>{statusLabel(job.status)}</strong> · turn {job.startTurnId}–{job.endTurnId}{job.errorMessage ? <span className="ml-2 font-semibold opacity-80">{job.errorMessage}</span> : null}</span>
                    <span className="flex items-center gap-2">
                      {['queued', 'running', 'cancelling'].includes(job.status) ? (
                        <button type="button" disabled={job.status === 'cancelling' || media.cancelJobMutation.isPending} onClick={() => media.cancelJobMutation.mutate(job.jobId)} className="inline-flex h-7 items-center gap-1 rounded-md border border-current/20 px-2"><Square size={11} />取消</button>
                      ) : (
                        <button type="button" disabled={media.retryJobMutation.isPending} onClick={() => media.retryJobMutation.mutate(job.jobId)} className="inline-flex h-7 items-center gap-1 rounded-md border border-current/20 px-2"><RefreshCcw size={11} />重试</button>
                      )}
                    </span>
                  </div>
                ))}
              </div>
            ) : null}

            {media.galleryQuery.isError ? (
              <p className="mt-6 rounded-lg border border-rose-200 bg-rose-50 px-4 py-4 text-sm font-bold text-rose-700 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-200">画廊加载失败：{errorMessage(media.galleryQuery.error)}</p>
            ) : media.galleryQuery.isLoading ? (
              <div className="py-16 text-center text-sm font-bold text-slate-400"><Loader2 size={20} className="mx-auto mb-3 animate-spin" />正在加载 Session Gallery</div>
            ) : gallery?.items.length ? (
              <div className="mt-5 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
                {gallery.items.map((item) => (
                  <GalleryCard
                    key={item.assetId}
                    sessionId={sessionId}
                    item={item}
                    backgroundAssetId={backgroundAssetId}
                    pending={actionPending}
                    onSetBackground={() => media.setBackgroundMutation.mutate(item.assetId)}
                    onClearBackground={() => media.clearBackgroundMutation.mutate()}
                    onRegenerate={() => item.jobId && media.retryJobMutation.mutate(item.jobId)}
                    onDelete={() => setDeleteTarget(item)}
                  />
                ))}
              </div>
            ) : (
              <div className="mt-8 rounded-xl border border-dashed border-slate-300 bg-slate-50 px-6 py-16 text-center dark:border-slate-700 dark:bg-slate-900/70">
                <Images size={28} className="mx-auto text-slate-300 dark:text-slate-600" />
                <h4 className="mt-3 text-base font-black text-slate-800 dark:text-slate-100">还没有生成图片</h4>
                <p className="mt-2 text-sm font-semibold text-slate-400">从左侧选择 1–20 个连续 turn，先检查简报，再提交生成。</p>
              </div>
            )}
          </section>
        </div>
      </Dialog>
      {deleteTarget ? (
        <ConfirmDialog
          title="删除图片资产"
          heading="永久删除这次生成的 Asset？"
          body={backgroundAssetId === deleteTarget.assetId ? '当前图片仍是会话背景，请先清除背景后再删除。' : '该 Asset 会从 Session Gallery 删除；若它是 Blob 的最后一个引用，文件也会被回收。'}
          confirmLabel="删除图片"
          pending={media.deleteAssetMutation.isPending}
          disabled={backgroundAssetId === deleteTarget.assetId}
          onClose={() => setDeleteTarget(null)}
          onConfirm={() => {
            media.deleteAssetMutation.mutate(deleteTarget.assetId, { onSuccess: () => setDeleteTarget(null) })
          }}
        />
      ) : null}
    </>
  )
}
