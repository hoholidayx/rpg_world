'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useRef, useState } from 'react'
import {
  cancelMediaJob,
  clearMediaBackground,
  createMediaBrief,
  createMediaJob,
  deleteMediaAsset,
  getMediaBackground,
  getMediaGallery,
  getMediaBackgroundEvaluation,
  getMediaLibrary,
  getMediaProviders,
  getMediaSourceTurns,
  retryMediaJob,
  queueMediaBackgroundEvaluation,
  setMediaBackground,
} from '@/lib/api/media'
import { sessionMediaConfig } from '@/lib/config/appConfig'
import type { VisualBrief } from '@/types/media'

const activeEvaluationStatuses = new Set(['queued', 'running'])

export function useSessionMedia({
  sessionId,
  workspaceId,
  storyId,
  latestCommittedTurnId,
  galleryOpen,
  showToast,
}: {
  sessionId: string
  workspaceId: string | null
  storyId: number | null
  latestCommittedTurnId: number
  galleryOpen: boolean
  showToast: (message: string) => void
}) {
  const queryClient = useQueryClient()
  const [evaluationId, setEvaluationId] = useState<string | null>(null)
  const evaluationStartedAtRef = useRef(0)
  const latestRequestedTurnRef = useRef(0)
  const requestVersionRef = useRef(0)
  const galleryKey = ['play-session-media-gallery', sessionId] as const
  const backgroundKey = ['play-session-media-background', sessionId] as const

  const providersQuery = useQuery({
    queryKey: ['play-session-media-providers', sessionId],
    queryFn: () => getMediaProviders(sessionId),
    enabled: galleryOpen,
    retry: false,
  })
  const sourceTurnsQuery = useQuery({
    queryKey: ['play-session-media-source-turns', sessionId],
    queryFn: () => getMediaSourceTurns(sessionId),
    enabled: galleryOpen,
    retry: false,
  })
  const galleryQuery = useQuery({
    queryKey: galleryKey,
    queryFn: () => getMediaGallery(sessionId),
    enabled: galleryOpen,
    retry: false,
    refetchInterval: (query) => query.state.data?.activeJobs.length ? 1000 : false,
  })
  const storyLibraryQuery = useQuery({
    queryKey: ['play-session-media-story-library', workspaceId, storyId],
    queryFn: () => getMediaLibrary(workspaceId ?? '', {
      scope: 'story',
      storyId: storyId ?? undefined,
      mediaTypes: ['background'],
      pageSize: 100,
    }),
    enabled: galleryOpen && Boolean(workspaceId && storyId),
    retry: false,
  })
  const backgroundQuery = useQuery({
    queryKey: backgroundKey,
    queryFn: () => getMediaBackground(sessionId),
    enabled: Boolean(sessionId),
    retry: false,
    refetchOnWindowFocus: false,
  })
  const evaluationQuery = useQuery({
    queryKey: ['play-session-media-background-evaluation', sessionId, evaluationId],
    queryFn: () => getMediaBackgroundEvaluation(sessionId, evaluationId ?? ''),
    enabled: Boolean(evaluationId),
    retry: false,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      if (!status || !activeEvaluationStatuses.has(status)) return false
      if (Date.now() - evaluationStartedAtRef.current >= sessionMediaConfig.backgroundEvaluationTimeoutMs) {
        return false
      }
      return sessionMediaConfig.backgroundEvaluationPollIntervalMs
    },
    refetchOnWindowFocus: false,
  })

  const refreshGallery = () => queryClient.invalidateQueries({ queryKey: galleryKey })
  const refreshBackground = () => queryClient.invalidateQueries({ queryKey: backgroundKey })
  const showMutationError = (label: string, error: unknown) => {
    showToast(`${label}：${error instanceof Error ? error.message : '未知错误'}`)
  }

  const requestBackgroundEvaluation = useCallback((observedTurnId: number, force = false) => {
    if (
      observedTurnId <= 0
      || (!force && observedTurnId <= latestRequestedTurnRef.current)
    ) return
    latestRequestedTurnRef.current = Math.max(
      latestRequestedTurnRef.current,
      observedTurnId,
    )
    const version = ++requestVersionRef.current
    void queueMediaBackgroundEvaluation(sessionId, observedTurnId)
      .then((evaluation) => {
        if (version !== requestVersionRef.current) return
        if (!activeEvaluationStatuses.has(evaluation.status)) {
          void queryClient.invalidateQueries({ queryKey: ['play-session-media-background', sessionId] })
          return
        }
        evaluationStartedAtRef.current = Date.now()
        setEvaluationId(evaluation.evaluationId)
      })
      .catch(() => {
        // Media availability is deliberately isolated from chat and session state.
      })
  }, [queryClient, sessionId])

  useEffect(() => {
    latestRequestedTurnRef.current = 0
    requestVersionRef.current += 1
    setEvaluationId(null)
  }, [sessionId])

  useEffect(() => {
    if (latestCommittedTurnId > 0) requestBackgroundEvaluation(latestCommittedTurnId)
  }, [latestCommittedTurnId, requestBackgroundEvaluation])

  useEffect(() => {
    if (!evaluationId) return
    const timer = window.setTimeout(
      () => setEvaluationId((current) => current === evaluationId ? null : current),
      sessionMediaConfig.backgroundEvaluationTimeoutMs,
    )
    return () => window.clearTimeout(timer)
  }, [evaluationId])

  useEffect(() => {
    const evaluation = evaluationQuery.data
    if (!evaluation || activeEvaluationStatuses.has(evaluation.status)) return
    void queryClient.invalidateQueries({ queryKey: ['play-session-media-background', sessionId] })
    setEvaluationId((current) => current === evaluation.evaluationId ? null : current)
  }, [evaluationQuery.data, queryClient, sessionId])

  const briefMutation = useMutation({
    mutationFn: (range: { startTurnId: number; endTurnId: number }) => (
      createMediaBrief(sessionId, range)
    ),
    onError: (error) => showMutationError('生成简报失败', error),
  })
  const createJobMutation = useMutation({
    mutationFn: (input: Parameters<typeof createMediaJob>[1]) => createMediaJob(sessionId, input),
    onSuccess: () => {
      void refreshGallery()
      showToast('生图任务已加入队列')
    },
    onError: (error) => showMutationError('提交生图任务失败', error),
  })
  const cancelJobMutation = useMutation({
    mutationFn: (jobId: string) => cancelMediaJob(sessionId, jobId),
    onSuccess: () => {
      void refreshGallery()
      showToast('已请求取消生图任务')
    },
    onError: (error) => showMutationError('取消生图任务失败', error),
  })
  const retryJobMutation = useMutation({
    mutationFn: (jobId: string) => retryMediaJob(sessionId, jobId),
    onSuccess: () => {
      void refreshGallery()
      showToast('已创建新的直接重抽任务')
    },
    onError: (error) => {
      showMutationError('重抽失败', error)
    },
  })
  const editRetryJobMutation = useMutation({
    mutationFn: (input: { jobId: string; visualBrief: VisualBrief }) => (
      retryMediaJob(sessionId, input.jobId, { visualBrief: input.visualBrief })
    ),
    onSuccess: () => {
      void refreshGallery()
      showToast('已创建编辑后的重抽任务')
    },
    onError: (error) => {
      showMutationError('编辑重抽失败', error)
    },
  })
  const setBackgroundMutation = useMutation({
    mutationFn: (assetId: string) => setMediaBackground(sessionId, assetId),
    onSuccess: () => {
      void refreshBackground()
      showToast('会话背景已更新')
    },
    onError: (error) => showMutationError('设置会话背景失败', error),
  })
  const clearBackgroundMutation = useMutation({
    mutationFn: () => clearMediaBackground(sessionId),
    onSuccess: () => {
      void refreshBackground()
      showToast('会话背景已清除')
    },
    onError: (error) => showMutationError('清除会话背景失败', error),
  })
  const deleteAssetMutation = useMutation({
    mutationFn: (assetId: string) => deleteMediaAsset(sessionId, assetId),
    onSuccess: () => {
      void refreshGallery()
      void refreshBackground()
      showToast('图片资产已删除')
    },
    onError: (error) => showMutationError('删除图片资产失败', error),
  })

  return {
    providersQuery,
    sourceTurnsQuery,
    galleryQuery,
    storyLibraryQuery,
    backgroundQuery,
    evaluationQuery,
    requestBackgroundEvaluation,
    briefMutation,
    createJobMutation,
    cancelJobMutation,
    retryJobMutation,
    editRetryJobMutation,
    setBackgroundMutation,
    clearBackgroundMutation,
    deleteAssetMutation,
  }
}

export type SessionMediaController = ReturnType<typeof useSessionMedia>
