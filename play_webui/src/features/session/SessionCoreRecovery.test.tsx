// @vitest-environment jsdom

import { fireEvent, render, screen } from '@testing-library/react'
import React from 'react'
import { describe, expect, it, vi } from 'vitest'
import {
  resolveSessionCoreRecovery,
  SessionCoreRecovery,
} from './SessionCoreRecovery'

describe('SessionCoreRecovery', () => {
  it('blocks on initial history failure but keeps cached history ready', () => {
    expect(resolveSessionCoreRecovery({
      session: { available: true, isError: false, error: null },
      history: { available: false, isError: true, error: new Error('history down') },
    })).toEqual({
      kind: 'error',
      source: 'history',
      message: 'history down',
    })

    expect(resolveSessionCoreRecovery({
      session: { available: true, isError: false, error: null },
      history: { available: true, isError: true, error: new Error('refresh down') },
    })).toEqual({ kind: 'ready' })
  })

  it('offers retry without turning the recovery action into navigation', () => {
    const onRetry = vi.fn()
    render(
      <SessionCoreRecovery
        state={{ kind: 'error', source: 'session', message: 'session down' }}
        retrying={false}
        onRetry={onRetry}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: '重试' }))
    expect(onRetry).toHaveBeenCalledTimes(1)
    expect(screen.getByRole('link', { name: '返回会话中心' }).getAttribute('href')).toBe('/sessions')
  })
})
