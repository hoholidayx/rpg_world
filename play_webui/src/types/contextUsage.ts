import type { ContextPreviewPayload } from './contextPreview'

export type ContextUsageSource = 'provider_usage' | 'context_preview' | 'fallback_estimate' | 'unavailable'
export type ContextUsageAccuracy = 'accurate' | 'estimated' | 'unknown'
export type ContextUsageStatus = 'normal' | 'warning' | 'danger' | 'unknown'

export type RawTurnUsage = {
  prompt_tokens?: number
  completion_tokens?: number
  total_tokens?: number
  cached_tokens?: number
  promptTokens?: number
  completionTokens?: number
  totalTokens?: number
  cachedTokens?: number
  source?: ContextUsageSource
  accuracy?: ContextUsageAccuracy
  model?: string
  finishReason?: string
  durationMs?: number
  createdAt?: string
  [key: string]: unknown
}

export type ContextUsageSnapshot = {
  usedTokens: number | null
  promptTokens: number | null
  completionTokens: number
  totalTokens: number | null
  cachedTokens: number
  contextLimit: number | null
  ratio: number | null
  source: ContextUsageSource
  accuracy: ContextUsageAccuracy
  status: ContextUsageStatus
  model?: string | null
  finishReason?: string | null
  durationMs?: number | null
  createdAt?: string | null
  errorReason?: string | null
}

function optionalNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function statusFromRatio(ratio: number | null): ContextUsageStatus {
  if (ratio === null) return 'unknown'
  if (ratio >= 0.9) return 'danger'
  if (ratio >= 0.7) return 'warning'
  return 'normal'
}

function ratioFrom(usedTokens: number | null, contextLimit: number | null): number | null {
  if (usedTokens === null || contextLimit === null || contextLimit <= 0) return null
  return usedTokens / contextLimit
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === 'object' && !Array.isArray(value))
}

function estimateSource(value: unknown): ContextUsageSource {
  if (value === 'fallback_estimate' || value === 'unavailable') return value
  return 'context_preview'
}

function estimateAccuracy(value: unknown): ContextUsageAccuracy {
  return value === 'unknown' ? 'unknown' : 'estimated'
}

export function fromContextPreviewEstimate(preview: ContextPreviewPayload | undefined): ContextUsageSnapshot | null {
  if (!preview) return null
  const estimate = isRecord(preview.usageEstimate) ? preview.usageEstimate : null
  const usedTokens = optionalNumber(estimate?.usedTokens) ?? preview.totals.tokenCount
  const contextLimit = optionalNumber(estimate?.contextLimit)
  const ratio = ratioFrom(usedTokens, contextLimit)
  const source = estimateSource(estimate?.source)
  const accuracy = estimateAccuracy(estimate?.accuracy)
  return {
    usedTokens,
    promptTokens: optionalNumber(estimate?.promptTokens) ?? usedTokens,
    completionTokens: optionalNumber(estimate?.completionTokens) ?? 0,
    totalTokens: optionalNumber(estimate?.totalTokens) ?? usedTokens,
    cachedTokens: optionalNumber(estimate?.cachedTokens) ?? 0,
    contextLimit,
    ratio,
    source,
    accuracy,
    status: statusFromRatio(ratio),
    model: typeof estimate?.model === 'string' ? estimate.model : null,
    finishReason: typeof estimate?.finishReason === 'string' ? estimate.finishReason : null,
    durationMs: optionalNumber(estimate?.durationMs),
    createdAt: typeof estimate?.createdAt === 'string' ? estimate.createdAt : null,
    errorReason: typeof estimate?.errorReason === 'string' ? estimate.errorReason : null,
  }
}

export function fromTurnUsage(
  usage: unknown,
  base?: ContextUsageSnapshot | null,
  metadata?: { model?: string; finishReason?: string; durationMs?: number },
): ContextUsageSnapshot | null {
  if (!isRecord(usage)) return null
  const promptTokens = optionalNumber(usage.prompt_tokens) ?? optionalNumber(usage.promptTokens)
  if (promptTokens === null || promptTokens <= 0) return null
  const completionTokens = optionalNumber(usage.completion_tokens) ?? optionalNumber(usage.completionTokens) ?? 0
  const totalTokens = optionalNumber(usage.total_tokens) ?? optionalNumber(usage.totalTokens) ?? promptTokens + completionTokens
  const cachedTokens = optionalNumber(usage.cached_tokens) ?? optionalNumber(usage.cachedTokens) ?? 0
  const contextLimit = base?.contextLimit ?? null
  const ratio = ratioFrom(promptTokens, contextLimit)
  return {
    usedTokens: promptTokens,
    promptTokens,
    completionTokens,
    totalTokens,
    cachedTokens,
    contextLimit,
    ratio,
    source: 'provider_usage',
    accuracy: 'accurate',
    status: statusFromRatio(ratio),
    model: typeof usage.model === 'string' ? usage.model : metadata?.model ?? base?.model ?? null,
    finishReason: typeof usage.finishReason === 'string' ? usage.finishReason : metadata?.finishReason ?? null,
    durationMs: optionalNumber(usage.durationMs) ?? metadata?.durationMs ?? null,
    createdAt: typeof usage.createdAt === 'string' ? usage.createdAt : new Date().toISOString(),
    errorReason: null,
  }
}
