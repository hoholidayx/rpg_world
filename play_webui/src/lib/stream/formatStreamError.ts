import type { PlayStreamErrorPayload } from '@/types/stream'

export const DEFAULT_STREAM_ERROR_MESSAGE = '流式请求失败'
const ERROR_CODE_LABEL = '错误码'
const ERROR_MESSAGE_LABEL = '错误内容'

export function formatStreamErrorText(payload: PlayStreamErrorPayload): string {
  const message = payload.message?.trim() || DEFAULT_STREAM_ERROR_MESSAGE
  const errorCode = payload.errorCode?.trim()
  if (!errorCode) return message
  return `${ERROR_CODE_LABEL}：${errorCode}\n${ERROR_MESSAGE_LABEL}：${message}`
}
