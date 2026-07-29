// @vitest-environment jsdom

import { act, cleanup, render, screen } from '@testing-library/react'
import React from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { SideDrawer } from './SideDrawer'

describe('SideDrawer', () => {
  beforeEach(() => {
    document.body.innerHTML = '<div id="modal-root"></div>'
    vi.useFakeTimers()
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
      callback(0)
      return 1
    })
    vi.stubGlobal('cancelAnimationFrame', vi.fn())
  })

  afterEach(() => {
    cleanup()
    document.body.innerHTML = ''
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('makes exiting content inert until the close animation unmounts it', () => {
    const view = render(
      <SideDrawer
        open
        side="right"
        eyebrow="测试"
        title="工作台"
        onClose={vi.fn()}
      >
        <button type="button">内部操作</button>
      </SideDrawer>,
    )

    screen.getByRole('dialog', { name: '工作台' })
    view.rerender(
      <SideDrawer
        open={false}
        side="right"
        eyebrow="测试"
        title="工作台"
        onClose={vi.fn()}
      >
        <button type="button">内部操作</button>
      </SideDrawer>,
    )

    const exitingDialog = document.querySelector<HTMLElement>('[role="dialog"]')
    expect(exitingDialog?.hasAttribute('inert')).toBe(true)
    expect(exitingDialog?.getAttribute('aria-hidden')).toBe('true')

    act(() => {
      vi.advanceTimersByTime(200)
    })
    expect(document.querySelector('[role="dialog"]')).toBeNull()
  })
})
