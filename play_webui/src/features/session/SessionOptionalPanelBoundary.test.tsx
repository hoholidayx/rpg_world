// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import React from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { SessionOptionalPanelBoundary } from './SessionOptionalPanelBoundary'

vi.mock('@/components/common/SideDrawer', async () => {
  const react = await import('react')
  return {
    SideDrawer: ({
      open,
      title,
      onClose,
      children,
    }: {
      open: boolean
      title: string
      onClose: () => void
      children: React.ReactNode
    }) => open
      ? react.createElement(
          'section',
          null,
          react.createElement('h2', null, title),
          react.createElement('button', { type: 'button', 'aria-label': '关闭', onClick: onClose }, '关闭'),
          children,
        )
      : null,
  }
})

function BrokenPanel({ broken }: { broken: boolean }) {
  if (broken) throw new Error('panel failed')
  return <p>panel ready</p>
}

describe('SessionOptionalPanelBoundary', () => {
  beforeEach(() => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined)
  })

  afterEach(() => {
    cleanup()
  })

  it('contains a panel render failure and can recover after a reset key change', () => {
    const onClose = vi.fn()
    const { rerender } = render(
      <div>
        <p>chat remains</p>
        <SessionOptionalPanelBoundary
          open
          title="剧情故事"
          resetKey="session_1"
          onClose={onClose}
        >
          <BrokenPanel broken />
        </SessionOptionalPanelBoundary>
      </div>,
    )

    expect(screen.getByText('chat remains')).toBeTruthy()
    expect(screen.getByRole('alert').textContent).toContain('panel failed')

    rerender(
      <div>
        <p>chat remains</p>
        <SessionOptionalPanelBoundary
          open
          title="剧情故事"
          resetKey="session_2"
          onClose={onClose}
        >
          <BrokenPanel broken={false} />
        </SessionOptionalPanelBoundary>
      </div>,
    )

    expect(screen.getByText('panel ready')).toBeTruthy()
  })

  it('closes only the failed panel', () => {
    const onClose = vi.fn()
    render(
      <SessionOptionalPanelBoundary
        open
        title="图像工作室"
        resetKey="session_1"
        onClose={onClose}
      >
        <BrokenPanel broken />
      </SessionOptionalPanelBoundary>,
    )

    fireEvent.click(screen.getByRole('button', { name: '关闭' }))
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})
