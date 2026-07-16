export type TTSJobStatus = 'queued' | 'running' | 'succeeded' | 'failed' | 'interrupted'

export type TTSAudioPart = {
  partIndex: number
  audioUrl: string
}

export type TTSJob = {
  jobId: string
  sessionId: string
  messageId: number
  status: TTSJobStatus
  partCount: number
  parts: TTSAudioPart[]
  errorCode: string
  errorMessage: string
  createdAt: string
  updatedAt: string
}
