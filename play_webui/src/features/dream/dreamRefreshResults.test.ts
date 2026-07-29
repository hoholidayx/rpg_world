import { describe, expect, it } from 'vitest'
import { firstDreamRefreshError } from './dreamRefreshResults'

describe('firstDreamRefreshError', () => {
  it('returns the first query failure from a manual refresh batch', () => {
    const failure = new Error('dream service unavailable')
    expect(firstDreamRefreshError([
      { isError: false, data: [] },
      { isError: true, error: failure },
      { isError: true, error: new Error('later') },
    ])).toBe(failure)
  })

  it('does not invent a failure when every query refresh succeeds', () => {
    expect(firstDreamRefreshError([
      { isError: false, data: [] },
      { isError: false, data: {} },
    ])).toBeNull()
  })
})
