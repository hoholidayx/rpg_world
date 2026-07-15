'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  cancelMediaJob,
  clearMediaBackground,
  createMediaBrief,
  createMediaJob,
  deleteMediaAsset,
  getMediaBackground,
  getMediaGallery,
  getMediaProviders,
  getMediaSourceTurns,
  retryMediaJob,
  setMediaBackground,
} from '@/lib/api/media'

export function useSessionMedia({
  sessionId,
  galleryOpen,
  showToast,
}: {
  sessionId: string
  galleryOpen: boolean
  showToast: (message: string) => void
}) {
  const queryClient = useQueryClient()
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
  const backgroundQuery = useQuery({
    queryKey: backgroundKey,
    queryFn: () => getMediaBackground(sessionId),
    enabled: Boolean(sessionId),
    retry: false,
    refetchOnWindowFocus: false,
  })

  const refreshGallery = () => queryClient.invalidateQueries({ queryKey: galleryKey })
  const refreshBackground = () => queryClient.invalidateQueries({ queryKey: backgroundKey })

  const briefMutation = useMutation({
    mutationFn: (range: { startTurnId: number; endTurnId: number }) => (
      createMediaBrief(sessionId, range)
    ),
  })
  const createJobMutation = useMutation({
    mutationFn: (input: Parameters<typeof createMediaJob>[1]) => createMediaJob(sessionId, input),
    onSuccess: () => {
      void refreshGallery()
      showToast('生图任务已加入队列')
    },
  })
  const cancelJobMutation = useMutation({
    mutationFn: (jobId: string) => cancelMediaJob(sessionId, jobId),
    onSuccess: () => {
      void refreshGallery()
      showToast('已请求取消生图任务')
    },
  })
  const retryJobMutation = useMutation({
    mutationFn: (jobId: string) => retryMediaJob(sessionId, jobId),
    onSuccess: () => {
      void refreshGallery()
      showToast('已创建新的重试任务')
    },
  })
  const setBackgroundMutation = useMutation({
    mutationFn: (assetId: string) => setMediaBackground(sessionId, assetId),
    onSuccess: () => {
      void refreshBackground()
      showToast('会话背景已更新')
    },
  })
  const clearBackgroundMutation = useMutation({
    mutationFn: () => clearMediaBackground(sessionId),
    onSuccess: () => {
      void refreshBackground()
      showToast('会话背景已清除')
    },
  })
  const deleteAssetMutation = useMutation({
    mutationFn: (assetId: string) => deleteMediaAsset(sessionId, assetId),
    onSuccess: () => {
      void refreshGallery()
      void refreshBackground()
      showToast('图片资产已删除')
    },
  })

  return {
    providersQuery,
    sourceTurnsQuery,
    galleryQuery,
    backgroundQuery,
    briefMutation,
    createJobMutation,
    cancelJobMutation,
    retryJobMutation,
    setBackgroundMutation,
    clearBackgroundMutation,
    deleteAssetMutation,
  }
}

export type SessionMediaController = ReturnType<typeof useSessionMedia>
