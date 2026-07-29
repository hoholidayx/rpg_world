// @vitest-environment jsdom

import { act, renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useSessionTTS } from './useSessionTTS'

const ttsApi = vi.hoisted(() => ({
  createTTSJob: vi.fn(),
  getTTSJob: vi.fn(),
  retryTTSJob: vi.fn(),
  ttsAudioUrl: vi.fn((value: string) => value),
}))

vi.mock('@/lib/api/tts', () => ttsApi)

describe('useSessionTTS service isolation', () => {
  beforeEach(() => {
    ttsApi.createTTSJob.mockRejectedValue(new Error('tts service unavailable'))
  })

  it('does not query until requested and keeps a failed message independently retryable', async () => {
    const { result } = renderHook(() => useSessionTTS('session_1', [42]))

    expect(ttsApi.createTTSJob).not.toHaveBeenCalled()
    expect(result.current.byMessageId).toEqual({})

    await act(async () => {
      await result.current.toggle(42)
    })

    expect(ttsApi.createTTSJob).toHaveBeenCalledTimes(1)
    expect(result.current.byMessageId[42]).toMatchObject({
      phase: 'error',
      error: 'tts service unavailable',
    })

    await act(async () => {
      await result.current.toggle(42)
    })

    expect(ttsApi.createTTSJob).toHaveBeenCalledTimes(2)
    expect(ttsApi.retryTTSJob).not.toHaveBeenCalled()
  })
})
