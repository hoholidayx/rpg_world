import type { ContextUsageSnapshot } from '@/types/contextUsage'

export const MAIN_CONTEXT_WINDOW_THRESHOLD_EXCEEDED_ERROR_CODE = (
  'MAIN_CONTEXT_WINDOW_THRESHOLD_EXCEEDED'
)

export function isSlashCommandInput(text: string) {
  return text.trimStart().startsWith('/')
}

export function isContextInputBlocked(
  usage: ContextUsageSnapshot | null | undefined,
  thresholdRatio: number,
) {
  if (
    !usage
    || usage.usedTokens === null
    || usage.contextLimit === null
    || usage.contextLimit <= 0
  ) return false
  return usage.usedTokens / usage.contextLimit >= thresholdRatio
}
