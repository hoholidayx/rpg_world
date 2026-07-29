// @vitest-environment jsdom

import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import React, { type ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useSessionMedia } from './useSessionMedia'

const mediaApi = vi.hoisted(() => ({
  cancelMediaJob: vi.fn(),
  clearMediaBackground: vi.fn(),
  createMediaBrief: vi.fn(),
  createMediaJob: vi.fn(),
  deleteMediaAsset: vi.fn(),
  getMediaBackground: vi.fn(),
  getMediaGallery: vi.fn(),
  getMediaBackgroundEvaluation: vi.fn(),
  getMediaLibrary: vi.fn(),
  getMediaProviders: vi.fn(),
  getMediaSourceTurns: vi.fn(),
  retryMediaJob: vi.fn(),
  queueMediaBackgroundEvaluation: vi.fn(),
  setMediaBackground: vi.fn(),
}))

vi.mock('@/lib/api/media', () => mediaApi)

function wrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })
  return function TestWrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        {children}
      </QueryClientProvider>
    )
  }
}

describe('useSessionMedia query isolation', () => {
  beforeEach(() => {
    mediaApi.getMediaBackground.mockResolvedValue({
      background: null,
      revisionToken: 'none',
    })
    mediaApi.getMediaProviders.mockResolvedValue({ providers: [] })
    mediaApi.getMediaSourceTurns.mockResolvedValue({ turns: [], shortcuts: [1, 5, 10, 20] })
    mediaApi.getMediaGallery.mockResolvedValue({ items: [], activeJobs: [], recentJobs: [] })
    mediaApi.getMediaLibrary.mockResolvedValue({ items: [], total: 0 })
  })

  it('keeps the visual background active but defers workbench queries until open', async () => {
    const showToast = vi.fn()
    const { rerender } = renderHook(
      ({ galleryOpen }) => useSessionMedia({
        sessionId: 'session_1',
        workspaceId: 'workspace_1',
        storyId: 1,
        latestCommittedTurnId: 0,
        galleryOpen,
        showToast,
      }),
      {
        initialProps: { galleryOpen: false },
        wrapper: wrapper(),
      },
    )

    await waitFor(() => expect(mediaApi.getMediaBackground).toHaveBeenCalledTimes(1))
    expect(mediaApi.getMediaProviders).not.toHaveBeenCalled()
    expect(mediaApi.getMediaSourceTurns).not.toHaveBeenCalled()
    expect(mediaApi.getMediaGallery).not.toHaveBeenCalled()
    expect(mediaApi.getMediaLibrary).not.toHaveBeenCalled()

    rerender({ galleryOpen: true })

    await waitFor(() => {
      expect(mediaApi.getMediaProviders).toHaveBeenCalledTimes(1)
      expect(mediaApi.getMediaSourceTurns).toHaveBeenCalledTimes(1)
      expect(mediaApi.getMediaGallery).toHaveBeenCalledTimes(1)
      expect(mediaApi.getMediaLibrary).toHaveBeenCalledTimes(1)
    })
  })
})
