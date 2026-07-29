// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import React from 'react'
import { useRef, useState } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ModalFocusScope, ModalPortal } from './ModalFocusScope'

function BasicModal({
  dismissible = true,
  suspended = false,
  onDismiss,
}: {
  dismissible?: boolean
  suspended?: boolean
  onDismiss?: () => void
}) {
  const [open, setOpen] = useState(false)
  const dialogRef = useRef<HTMLElement>(null)
  const firstRef = useRef<HTMLButtonElement>(null)

  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>打开弹层</button>
      {open ? (
        <ModalPortal>
          <ModalFocusScope
            containerRef={dialogRef}
            dismissible={dismissible}
            suspended={suspended}
            initialFocusRef={firstRef}
            onDismiss={() => {
              onDismiss?.()
              setOpen(false)
            }}
          >
            <section ref={dialogRef} role="dialog" tabIndex={-1}>
              <button ref={firstRef} type="button">第一个</button>
              <button type="button">最后一个</button>
            </section>
          </ModalFocusScope>
        </ModalPortal>
      ) : null}
    </>
  )
}

function NestedModal() {
  const [outerOpen, setOuterOpen] = useState(false)
  const [innerOpen, setInnerOpen] = useState(false)
  const outerRef = useRef<HTMLElement>(null)
  const outerInitialRef = useRef<HTMLButtonElement>(null)
  const innerRef = useRef<HTMLElement>(null)
  const innerInitialRef = useRef<HTMLButtonElement>(null)

  return (
    <>
      <button type="button" onClick={() => setOuterOpen(true)}>打开外层</button>
      {outerOpen ? (
        <ModalPortal>
          <ModalFocusScope
            containerRef={outerRef}
            dismissible
            initialFocusRef={outerInitialRef}
            onDismiss={() => setOuterOpen(false)}
          >
            <section ref={outerRef} role="dialog" aria-label="外层弹层" tabIndex={-1}>
              <button
                ref={outerInitialRef}
                type="button"
                onClick={() => setInnerOpen(true)}
              >
                打开内层
              </button>
            </section>
          </ModalFocusScope>
        </ModalPortal>
      ) : null}
      {innerOpen ? (
        <ModalPortal>
          <ModalFocusScope
            containerRef={innerRef}
            dismissible
            initialFocusRef={innerInitialRef}
            onDismiss={() => setInnerOpen(false)}
          >
            <section ref={innerRef} role="dialog" aria-label="内层弹层" tabIndex={-1}>
              <button ref={innerInitialRef} type="button">内层操作</button>
            </section>
          </ModalFocusScope>
        </ModalPortal>
      ) : null}
    </>
  )
}

function DeferredInitialModal({ ready }: { ready: boolean }) {
  const dialogRef = useRef<HTMLElement>(null)
  const initialRef = useRef<HTMLButtonElement>(null)

  return (
    <ModalPortal>
      <ModalFocusScope
        containerRef={dialogRef}
        dismissible={false}
        initialFocusRef={initialRef}
        onDismiss={() => undefined}
      >
        <section ref={dialogRef} role="dialog" aria-label="延迟内容弹层" tabIndex={-1}>
          <p>正在加载</p>
          {ready ? <button ref={initialRef} type="button">加载后的首选操作</button> : null}
        </section>
      </ModalFocusScope>
    </ModalPortal>
  )
}

describe('ModalFocusScope', () => {
  beforeEach(() => {
    document.body.innerHTML = '<div id="modal-root"></div>'
    let frameId = 0
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
      callback(0)
      frameId += 1
      return frameId
    })
    vi.stubGlobal('cancelAnimationFrame', vi.fn())
  })

  afterEach(() => {
    cleanup()
    document.body.innerHTML = ''
    vi.unstubAllGlobals()
  })

  it('sets initial focus, loops Tab, hides the background, and restores the trigger', async () => {
    render(<BasicModal />)
    const trigger = screen.getByRole('button', { name: '打开弹层' })
    trigger.focus()
    fireEvent.click(trigger)

    const first = await screen.findByRole('button', { name: '第一个' })
    const last = screen.getByRole('button', { name: '最后一个' })
    expect(document.activeElement).toBe(first)
    expect(trigger.closest('div')?.hasAttribute('inert')).toBe(true)

    last.focus()
    fireEvent.keyDown(document, { key: 'Tab' })
    expect(document.activeElement).toBe(first)

    fireEvent.keyDown(document, { key: 'Tab', shiftKey: true })
    expect(document.activeElement).toBe(last)

    fireEvent.keyDown(document, { key: 'Escape' })
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(document.activeElement).toBe(trigger)
    expect(trigger.closest('div')?.hasAttribute('inert')).toBe(false)
  })

  it('does not dismiss a required or suspended modal', async () => {
    const onDismiss = vi.fn()
    const view = render(<BasicModal dismissible={false} onDismiss={onDismiss} />)
    fireEvent.click(screen.getByRole('button', { name: '打开弹层' }))
    await screen.findByRole('dialog')
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onDismiss).not.toHaveBeenCalled()
    expect(screen.getByRole('dialog')).not.toBeNull()

    view.rerender(<BasicModal suspended onDismiss={onDismiss} />)
    const hiddenDialog = screen.getByRole('dialog', { hidden: true })
    expect(hiddenDialog.hasAttribute('inert')).toBe(true)
    expect(hiddenDialog.getAttribute('aria-hidden')).toBe('true')
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onDismiss).not.toHaveBeenCalled()
  })

  it('moves fallback container focus to a requested target that loads later', async () => {
    const view = render(<DeferredInitialModal ready={false} />)
    const dialog = await screen.findByRole('dialog', { name: '延迟内容弹层' })
    expect(document.activeElement).toBe(dialog)

    view.rerender(<DeferredInitialModal ready />)
    const action = await screen.findByRole('button', { name: '加载后的首选操作' })
    await waitFor(() => expect(document.activeElement).toBe(action))
  })

  it('keeps only the top nested modal interactive and restores the lower focus', async () => {
    render(<NestedModal />)
    fireEvent.click(screen.getByRole('button', { name: '打开外层' }))
    const openInner = await screen.findByRole('button', { name: '打开内层' })
    expect(document.activeElement).toBe(openInner)

    fireEvent.click(openInner)
    const innerAction = await screen.findByRole('button', { name: '内层操作' })
    const outerDialog = document.querySelector<HTMLElement>('[aria-label="外层弹层"]')
    expect(document.activeElement).toBe(innerAction)
    expect(outerDialog?.hasAttribute('inert')).toBe(true)

    fireEvent.keyDown(document, { key: 'Escape' })
    await waitFor(() => {
      expect(screen.queryByRole('dialog', { name: '内层弹层' })).toBeNull()
    })
    expect(screen.getByRole('dialog', { name: '外层弹层' }).hasAttribute('inert')).toBe(false)
    expect(document.activeElement).toBe(openInner)

    fireEvent.keyDown(document, { key: 'Escape' })
    await waitFor(() => {
      expect(screen.queryByRole('dialog', { name: '外层弹层' })).toBeNull()
    })
  })
})
