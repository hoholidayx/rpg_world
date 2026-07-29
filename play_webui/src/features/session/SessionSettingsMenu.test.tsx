// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import React from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { SessionSettingsMenu } from './SessionSettingsMenu'

function stubViewport(mobile: boolean) {
  vi.stubGlobal('matchMedia', vi.fn((query: string) => ({
    matches: query === '(max-width: 639px)' ? mobile : false,
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })))
}

function renderMenu(onToggleOpen = vi.fn()) {
  return {
    onToggleOpen,
    ...render(
      <SessionSettingsMenu
        open
        fontScale={100}
        showThinking
        showTools
        onToggleOpen={onToggleOpen}
        onFontScaleChange={vi.fn()}
        onResetFontScale={vi.fn()}
        onShowThinkingChange={vi.fn()}
        onShowToolsChange={vi.fn()}
        onOpenRoleDialog={vi.fn()}
        onOpenRPModulesDialog={vi.fn()}
        onOpenDreamMemory={vi.fn()}
        onDeleteSession={vi.fn()}
      />,
    ),
  }
}

describe('SessionSettingsMenu responsive presentation', () => {
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

  it('keeps the desktop panel anchored and restores its trigger on Escape', async () => {
    stubViewport(false)
    const { onToggleOpen } = renderMenu()
    const menu = await screen.findByLabelText('会话设置菜单')
    expect(menu.getAttribute('role')).toBeNull()
    expect(screen.queryByRole('dialog')).toBeNull()

    screen.getByRole('button', { name: /^删除会话/ }).focus()
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onToggleOpen).toHaveBeenCalledTimes(1)
    expect(document.activeElement).toBe(screen.getByRole('button', { name: '设置' }))
  })

  it('uses a modal bottom drawer on mobile', async () => {
    stubViewport(true)
    renderMenu()

    const dialog = await screen.findByRole('dialog', { name: '会话设置' })
    expect(dialog.className).toContain('rounded-t-2xl')
    expect(document.activeElement).toBe(
      screen.getByRole('button', { name: '关闭会话设置' }),
    )
  })
})
