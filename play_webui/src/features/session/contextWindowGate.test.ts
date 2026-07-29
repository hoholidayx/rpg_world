import { describe, expect, it } from 'vitest'
import type { ContextUsageSnapshot } from '@/types/contextUsage'
import {
  isContextInputBlocked,
  isSlashCommandInput,
} from './contextWindowGate'

function usage(
  usedTokens: number | null,
  contextLimit: number | null,
): ContextUsageSnapshot {
  return {
    usedTokens,
    promptTokens: usedTokens,
    completionTokens: 0,
    totalTokens: usedTokens,
    cachedTokens: 0,
    contextLimit,
    ratio: null,
    source: 'context_preview',
    accuracy: 'estimated',
    status: 'normal',
    createdAt: null,
    model: null,
    finishReason: null,
    durationMs: null,
    errorReason: null,
  }
}

describe('isSlashCommandInput', () => {
  it.each([
    ['/compact', true],
    ['   /compact', true],
    ['\n\t/roll 1d20', true],
    ['say /compact', false],
    ['', false],
  ])('maps %j to %s', (text, expected) => {
    expect(isSlashCommandInput(text)).toBe(expected)
  })
})

describe('isContextInputBlocked', () => {
  it('blocks at the configured threshold', () => {
    expect(isContextInputBlocked(usage(900, 1000), 0.9)).toBe(true)
  })

  it('allows input immediately below the threshold', () => {
    expect(isContextInputBlocked(usage(899, 1000), 0.9)).toBe(false)
  })

  it.each([
    [null, 1000],
    [900, null],
    [900, 0],
    [900, -1],
  ])('allows input when usage is unavailable (%s/%s)', (used, limit) => {
    expect(isContextInputBlocked(usage(used, limit), 0.9)).toBe(false)
  })

  it('allows input when no usage snapshot exists', () => {
    expect(isContextInputBlocked(null, 0.9)).toBe(false)
    expect(isContextInputBlocked(undefined, 0.9)).toBe(false)
  })
})
