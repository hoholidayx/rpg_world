'use client'

import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Loader2, RefreshCcw } from 'lucide-react'
import { Dialog } from '@/components/common/Dialog'
import { getMediaJob } from '@/lib/api/media'
import type { VisualBrief } from '@/types/media'
import type { SessionMediaController } from './hooks/useSessionMedia'
import { VisualBriefEditor } from './VisualBriefEditor'

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : '未知错误'
}

export function MediaRetryDialog({
  sessionId,
  jobId,
  media,
  onClose,
}: {
  sessionId: string
  jobId: string
  media: SessionMediaController
  onClose: () => void
}) {
  const jobQuery = useQuery({
    queryKey: ['play-session-media-job', sessionId, jobId],
    queryFn: () => getMediaJob(sessionId, jobId),
    retry: false,
    refetchOnWindowFocus: false,
  })
  const [draft, setDraft] = useState<VisualBrief | null>(null)
  const pending = media.editRetryJobMutation.isPending

  useEffect(() => {
    const job = jobQuery.data
    if (!job) return
    setDraft((current) => current ?? {
      ...job.visualBrief,
      subjects: [...job.visualBrief.subjects],
    })
  }, [jobQuery.data])

  const submit = async () => {
    if (!draft?.sceneDescription.trim()) return
    try {
      await media.editRetryJobMutation.mutateAsync({
        jobId,
        visualBrief: draft,
      })
      onClose()
    } catch {
      // Mutation errors are rendered inline and surfaced through the shared toast.
    }
  }

  return (
    <Dialog
      title="编辑提示词后重抽"
      onClose={onClose}
      size="3xl"
      overlayClassName="z-[90]"
      closeDisabled={pending}
      className="flex max-h-[calc(100vh-3rem)] flex-col dark:border-slate-700 dark:bg-slate-950"
    >
      <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
        {jobQuery.isLoading ? (
          <div className="py-16 text-center text-sm font-bold text-slate-400">
            <Loader2 size={20} className="mx-auto mb-3 animate-spin" />
            正在载入上次提示词
          </div>
        ) : jobQuery.isError ? (
          <p className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-4 text-sm font-bold text-rose-700 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-200">
            载入生图任务失败：{errorMessage(jobQuery.error)}
          </p>
        ) : jobQuery.data && draft ? (
          <>
            <div className="mb-5 grid gap-3 rounded-xl border border-slate-200 bg-slate-50 p-4 text-xs font-bold text-slate-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 sm:grid-cols-2">
              <span>
                来源 Turn
                <strong className="ml-2 text-slate-900 dark:text-slate-100">
                  {jobQuery.data.startTurnId}–{jobQuery.data.endTurnId}
                </strong>
              </span>
              <span>
                图片 Provider
                <strong className="ml-2 text-slate-900 dark:text-slate-100">
                  {jobQuery.data.providerKey}
                </strong>
              </span>
            </div>
            <VisualBriefEditor
              value={draft}
              disabled={pending}
              onChange={setDraft}
            />
            {media.editRetryJobMutation.isError ? (
              <p className="mt-3 rounded-lg border border-rose-200 bg-rose-50 px-3 py-3 text-xs font-bold text-rose-700 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-200">
                编辑重抽失败：{errorMessage(media.editRetryJobMutation.error)}
              </p>
            ) : null}
          </>
        ) : null}
      </div>
      <footer className="flex items-center justify-end gap-2 border-t border-slate-200 bg-slate-50 px-6 py-4 dark:border-slate-800 dark:bg-slate-900">
        <button
          type="button"
          onClick={onClose}
          disabled={pending}
          className="h-10 rounded-lg border border-slate-200 bg-white px-4 text-sm font-black text-slate-600 transition hover:border-violet-300 hover:text-violet-700 disabled:opacity-50 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-300"
        >
          取消
        </button>
        <button
          type="button"
          onClick={() => void submit()}
          disabled={
            !draft?.sceneDescription.trim()
            || jobQuery.isLoading
            || jobQuery.isError
            || pending
          }
          className="inline-flex h-10 items-center gap-2 rounded-lg bg-violet-600 px-4 text-sm font-black text-white transition hover:bg-violet-700 disabled:bg-slate-300 dark:disabled:bg-slate-700"
        >
          {pending ? (
            <Loader2 size={16} className="animate-spin" />
          ) : (
            <RefreshCcw size={16} />
          )}
          提交编辑后重抽
        </button>
      </footer>
    </Dialog>
  )
}
