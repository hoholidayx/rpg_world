// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import React from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ConfirmDialog } from './Dialog'

describe('ConfirmDialog', () => {
  beforeEach(() => {
    document.body.innerHTML = '<div id="modal-root"></div>'
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
      callback(0)
      return 1
    })
    vi.stubGlobal('cancelAnimationFrame', vi.fn())
  })

  afterEach(() => {
    cleanup()
    document.body.innerHTML = ''
    vi.unstubAllGlobals()
  })

  it('focuses cancel first and allows Escape while idle', async () => {
    const onClose = vi.fn()
    render(
      <ConfirmDialog
        title="确认操作"
        heading="真的执行？"
        body="测试"
        pending={false}
        onClose={onClose}
        onConfirm={vi.fn()}
      />,
    )

    const cancel = await screen.findByRole('button', { name: '取消' })
    expect(document.activeElement).toBe(cancel)
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('does not close with Escape while pending', async () => {
    const onClose = vi.fn()
    render(
      <ConfirmDialog
        title="确认操作"
        heading="真的执行？"
        body="测试"
        pending
        onClose={onClose}
        onConfirm={vi.fn()}
      />,
    )

    await screen.findByRole('dialog')
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onClose).not.toHaveBeenCalled()
  })
})
