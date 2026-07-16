import { getPlayApiBaseUrl } from '@/lib/config/env'
import type { TTSJob } from '@/types/tts'
import { playApiFetch } from './client'

function ttsPath(sessionId: string) {
  return `/sessions/${encodeURIComponent(sessionId)}/tts`
}

export function createTTSJob(sessionId: string, messageId: number) {
  return playApiFetch<TTSJob>(`${ttsPath(sessionId)}/messages/${messageId}/jobs`, { method: 'POST' })
}

export function getTTSJob(sessionId: string, jobId: string) {
  return playApiFetch<TTSJob>(`${ttsPath(sessionId)}/jobs/${encodeURIComponent(jobId)}`)
}

export function retryTTSJob(sessionId: string, jobId: string) {
  return playApiFetch<TTSJob>(`${ttsPath(sessionId)}/jobs/${encodeURIComponent(jobId)}/retry`, { method: 'POST' })
}

export function ttsAudioUrl(path: string) {
  return `${getPlayApiBaseUrl()}${path}`
}
