import { useCallback, useEffect, useRef, useState } from 'react'
import { createTTSJob, getTTSJob, retryTTSJob, ttsAudioUrl } from '@/lib/api/tts'
import type { TTSJob } from '@/types/tts'

export type TTSPlaybackPhase = 'idle' | 'queued' | 'running' | 'ready' | 'playing' | 'paused' | 'error'

export type TTSMessagePlayback = {
  phase: TTSPlaybackPhase
  job?: TTSJob
  error?: string
}

const POLL_INTERVAL_MS = 800

export function useSessionTTS(sessionId: string, visibleMessageIds: number[]) {
  const [byMessageId, setByMessageId] = useState<Record<number, TTSMessagePlayback>>({})
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const activeMessageIdRef = useRef<number | null>(null)
  const activeJobRef = useRef<TTSJob | null>(null)
  const activeEpochRef = useRef(-1)
  const activePartRef = useRef(0)
  const playbackTokenRef = useRef(0)
  const inFlightRef = useRef<Map<number, number>>(new Map())
  const playPartRef = useRef<((
    messageId: number,
    job: TTSJob,
    partIndex: number,
    sessionEpoch: number,
    playbackToken: number,
  ) => Promise<void>) | null>(null)
  const mountedRef = useRef(true)
  const sessionEpochRef = useRef(0)

  const update = useCallback((
    sessionEpoch: number,
    messageId: number,
    value: TTSMessagePlayback,
  ) => {
    if (!mountedRef.current || sessionEpochRef.current !== sessionEpoch) return
    setByMessageId((current) => ({ ...current, [messageId]: value }))
  }, [])

  const stopActive = useCallback((nextPhase: TTSPlaybackPhase = 'ready') => {
    playbackTokenRef.current += 1
    const audio = audioRef.current
    if (audio) {
      audio.pause()
      audio.onended = null
      audio.onerror = null
      audio.removeAttribute('src')
      audio.load()
    }
    const previous = activeMessageIdRef.current
    const previousJob = activeJobRef.current
    const previousEpoch = activeEpochRef.current
    activeMessageIdRef.current = null
    activeJobRef.current = null
    activeEpochRef.current = -1
    activePartRef.current = 0
    if (previous !== null && previousJob) {
      update(previousEpoch, previous, { phase: nextPhase, job: previousJob })
    }
  }, [update])

  const playPart = useCallback(async (
    messageId: number,
    job: TTSJob,
    partIndex: number,
    sessionEpoch: number,
    playbackToken: number,
  ) => {
    if (
      !mountedRef.current
      || sessionEpochRef.current !== sessionEpoch
      || playbackTokenRef.current !== playbackToken
    ) return
    const part = job.parts[partIndex]
    if (!part) {
      stopActive('error')
      update(sessionEpoch, messageId, {
        phase: 'error',
        job,
        error: '语音任务未返回可播放的音频分段',
      })
      return
    }
    const audio = audioRef.current ?? new Audio()
    audioRef.current = audio
    activeMessageIdRef.current = messageId
    activeJobRef.current = job
    activeEpochRef.current = sessionEpoch
    activePartRef.current = partIndex
    audio.src = ttsAudioUrl(part.audioUrl)
    audio.onended = () => {
      if (
        sessionEpochRef.current !== sessionEpoch
        || playbackTokenRef.current !== playbackToken
      ) return
      const nextIndex = activePartRef.current + 1
      if (nextIndex < job.parts.length) {
        const nextPlayback = playPartRef.current?.(
          messageId,
          job,
          nextIndex,
          sessionEpoch,
          playbackToken,
        )
        if (nextPlayback) {
          void nextPlayback.catch(() => {
            if (
              sessionEpochRef.current !== sessionEpoch
              || playbackTokenRef.current !== playbackToken
            ) return
            stopActive('error')
            update(sessionEpoch, messageId, {
              phase: 'error',
              job,
              error: '语音文件播放失败',
            })
          })
        }
      } else {
        stopActive('ready')
      }
    }
    audio.onerror = () => {
      if (
        sessionEpochRef.current !== sessionEpoch
        || playbackTokenRef.current !== playbackToken
      ) return
      stopActive('error')
      update(sessionEpoch, messageId, {
        phase: 'error',
        job,
        error: '语音文件播放失败',
      })
    }
    await audio.play()
    if (
      !mountedRef.current
      || sessionEpochRef.current !== sessionEpoch
      || playbackTokenRef.current !== playbackToken
    ) return
    update(sessionEpoch, messageId, { phase: 'playing', job })
  }, [stopActive, update])
  playPartRef.current = playPart

  const beginPlayback = useCallback(async (
    messageId: number,
    job: TTSJob,
    sessionEpoch: number,
  ) => {
    if (!mountedRef.current || sessionEpochRef.current !== sessionEpoch) return
    stopActive('ready')
    playbackTokenRef.current += 1
    const playbackToken = playbackTokenRef.current
    try {
      await playPart(messageId, job, 0, sessionEpoch, playbackToken)
    } catch (error) {
      if (
        !mountedRef.current
        || sessionEpochRef.current !== sessionEpoch
        || playbackTokenRef.current !== playbackToken
      ) return
      const blockedByBrowser = error instanceof DOMException && error.name === 'NotAllowedError'
      stopActive(blockedByBrowser ? 'ready' : 'error')
      update(sessionEpoch, messageId, blockedByBrowser
        ? { phase: 'ready', job }
        : { phase: 'error', job, error: '语音文件播放失败' })
    }
  }, [playPart, stopActive, update])

  const waitForJob = useCallback(async (
    messageId: number,
    initial: TTSJob,
    sessionEpoch: number,
  ) => {
    let job = initial
    while (
      mountedRef.current
      && sessionEpochRef.current === sessionEpoch
      && (job.status === 'queued' || job.status === 'running')
    ) {
      update(sessionEpoch, messageId, { phase: job.status, job })
      await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS))
      if (!mountedRef.current || sessionEpochRef.current !== sessionEpoch) return
      job = await getTTSJob(sessionId, job.jobId)
    }
    if (!mountedRef.current || sessionEpochRef.current !== sessionEpoch) return
    if (job.status === 'succeeded') {
      if (!job.parts.length) {
        update(sessionEpoch, messageId, {
          phase: 'error',
          job,
          error: '语音任务未返回可播放的音频分段',
        })
        return
      }
      update(sessionEpoch, messageId, { phase: 'ready', job })
      await beginPlayback(messageId, job, sessionEpoch)
      return
    }
    update(sessionEpoch, messageId, {
      phase: 'error',
      job,
      error: job.errorMessage || '语音生成失败',
    })
  }, [beginPlayback, sessionId, update])

  const toggle = useCallback(async (messageId: number) => {
    const sessionEpoch = sessionEpochRef.current
    const state = byMessageId[messageId]
    const active = (
      activeMessageIdRef.current === messageId
      && activeEpochRef.current === sessionEpoch
    )
    const audio = audioRef.current
    if (active && state?.phase === 'playing' && audio) {
      audio.pause()
      update(sessionEpoch, messageId, { phase: 'paused', job: state.job })
      return
    }
    if (active && state?.phase === 'paused' && audio) {
      const playbackToken = playbackTokenRef.current
      try {
        await audio.play()
        if (
          mountedRef.current
          && sessionEpochRef.current === sessionEpoch
          && activeMessageIdRef.current === messageId
          && playbackTokenRef.current === playbackToken
        ) {
          update(sessionEpoch, messageId, { phase: 'playing', job: state.job })
        }
      } catch {
        if (playbackTokenRef.current === playbackToken) {
          update(sessionEpoch, messageId, {
            phase: 'paused',
            job: state.job,
            error: '浏览器阻止了音频播放',
          })
        }
      }
      return
    }
    if (state?.job?.status === 'succeeded' && state.phase !== 'error') {
      await beginPlayback(messageId, state.job, sessionEpoch)
      return
    }
    if (inFlightRef.current.get(messageId) === sessionEpoch) return
    inFlightRef.current.set(messageId, sessionEpoch)
    update(sessionEpoch, messageId, { phase: 'queued', job: state?.job })
    try {
      const shouldRetry = Boolean(
        state?.job
        && (
          state.phase === 'error'
          || state.job.status === 'failed'
          || state.job.status === 'interrupted'
        )
      )
      let job = shouldRetry && state?.job
        ? await retryTTSJob(sessionId, state.job.jobId)
        : await createTTSJob(sessionId, messageId)
      if (!shouldRetry && (job.status === 'failed' || job.status === 'interrupted')) {
        job = await retryTTSJob(sessionId, job.jobId)
      }
      if (!mountedRef.current || sessionEpochRef.current !== sessionEpoch) return
      await waitForJob(messageId, job, sessionEpoch)
    } catch (error) {
      update(sessionEpoch, messageId, {
        phase: 'error',
        job: state?.job,
        error: error instanceof Error ? error.message : 'TTS 服务不可用',
      })
    } finally {
      if (inFlightRef.current.get(messageId) === sessionEpoch) {
        inFlightRef.current.delete(messageId)
      }
    }
  }, [beginPlayback, byMessageId, sessionId, update, waitForJob])

  useEffect(() => {
    const active = activeMessageIdRef.current
    if (active !== null && !visibleMessageIds.includes(active)) stopActive('ready')
  }, [stopActive, visibleMessageIds])

  useEffect(() => {
    sessionEpochRef.current += 1
    mountedRef.current = true
    playbackTokenRef.current += 1
    inFlightRef.current.clear()
    activeMessageIdRef.current = null
    activeJobRef.current = null
    activeEpochRef.current = -1
    activePartRef.current = 0
    setByMessageId({})
    return () => {
      mountedRef.current = false
      sessionEpochRef.current += 1
      playbackTokenRef.current += 1
      inFlightRef.current.clear()
      const audio = audioRef.current
      if (audio) {
        audio.pause()
        audio.onended = null
        audio.onerror = null
        audio.removeAttribute('src')
        audio.load()
      }
      audioRef.current = null
      activeMessageIdRef.current = null
      activeJobRef.current = null
      activeEpochRef.current = -1
      activePartRef.current = 0
    }
  }, [sessionId])

  return { byMessageId, toggle }
}
