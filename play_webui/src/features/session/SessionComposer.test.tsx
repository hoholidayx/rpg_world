// @vitest-environment jsdom

import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import React, { useState } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { SessionComposer } from './SessionComposer'

vi.mock('@/components/input/CommandPaletteDialog', () => ({
  CommandPaletteDialog: () => <button type="button">命令</button>,
}))

const quickReply = {
  id: 1,
  title: '观察',
  message: '我观察四周。',
  sortOrder: 0,
  enabled: true,
  version: 1,
}

function renderComposer({
  sending = false,
  onSend = vi.fn(),
  onStop = vi.fn(),
  onQuickReply = vi.fn(),
}: {
  sending?: boolean
  onSend?: () => void
  onStop?: () => void
  onQuickReply?: (message: string) => void
} = {}) {
  return render(
    <SessionComposer
      sessionId="session_1"
      text="测试行动"
      mode="neutral"
      narrativeStyleId={null}
      narrativeStyles={[{ id: null, label: '故事默认' }]}
      turnModes={[{ mode: 'neutral', shortName: '默认', sortOrder: 0 }]}
      quickReplies={[quickReply]}
      sending={sending}
      contextInputBlockThresholdRatio={0.9}
      onTextChange={vi.fn()}
      onModeChange={vi.fn()}
      onNarrativeStyleChange={vi.fn()}
      onMainLLMChange={vi.fn()}
      onSend={onSend}
      onQuickReply={onQuickReply}
      onStop={onStop}
    />,
  )
}

describe('SessionComposer', () => {
  beforeEach(() => {
    class TestPointerEvent extends MouseEvent {
      readonly pointerId: number

      constructor(type: string, init: PointerEventInit = {}) {
        super(type, init)
        this.pointerId = init.pointerId ?? 0
      }
    }

    vi.stubGlobal('PointerEvent', TestPointerEvent)
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
      callback(0)
      return 1
    })
    Object.defineProperty(HTMLElement.prototype, 'setPointerCapture', {
      configurable: true,
      value: vi.fn(),
    })
    Object.defineProperty(HTMLElement.prototype, 'hasPointerCapture', {
      configurable: true,
      value: () => false,
    })
  })

  afterEach(() => {
    cleanup()
    vi.useRealTimers()
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('sends with Enter while idle and stops with Enter without moving textarea focus', () => {
    const onSend = vi.fn()
    const onStop = vi.fn()
    const view = renderComposer({ onSend, onStop })
    const textarea = screen.getByRole('textbox')
    textarea.focus()

    fireEvent.keyDown(textarea, { key: 'Enter' })
    expect(onSend).toHaveBeenCalledTimes(1)
    expect(document.activeElement).toBe(textarea)

    view.rerender(
      <SessionComposer
        sessionId="session_1"
        text="测试行动"
        mode="neutral"
        narrativeStyleId={null}
        narrativeStyles={[{ id: null, label: '故事默认' }]}
        turnModes={[{ mode: 'neutral', shortName: '默认', sortOrder: 0 }]}
        quickReplies={[quickReply]}
        sending
        contextInputBlockThresholdRatio={0.9}
        onTextChange={vi.fn()}
        onModeChange={vi.fn()}
        onNarrativeStyleChange={vi.fn()}
        onMainLLMChange={vi.fn()}
        onSend={onSend}
        onQuickReply={vi.fn()}
        onStop={onStop}
      />,
    )
    const streamingTextarea = screen.getByRole('textbox')
    streamingTextarea.focus()
    fireEvent.keyDown(streamingTextarea, { key: 'Enter' })

    expect(onStop).toHaveBeenCalledTimes(1)
    expect(document.activeElement).toBe(streamingTextarea)
  })

  it('keeps focus on the same action button after a pointer stop', () => {
    let finishStop = () => undefined

    function Harness() {
      const [sending, setSending] = useState(true)
      const [stopping, setStopping] = useState(false)
      finishStop = () => {
        setSending(false)
        setStopping(false)
      }
      return (
        <SessionComposer
          sessionId="session_1"
          text=""
          mode="neutral"
          narrativeStyleId={null}
          narrativeStyles={[{ id: null, label: '故事默认' }]}
          turnModes={[{ mode: 'neutral', shortName: '默认', sortOrder: 0 }]}
          quickReplies={[]}
          sending={sending}
          stopping={stopping}
          contextInputBlockThresholdRatio={0.9}
          onTextChange={vi.fn()}
          onModeChange={vi.fn()}
          onNarrativeStyleChange={vi.fn()}
          onMainLLMChange={vi.fn()}
          onSend={vi.fn()}
          onQuickReply={vi.fn()}
          onStop={() => setStopping(true)}
        />
      )
    }

    render(<Harness />)
    const stopButton = screen.getByRole('button', { name: '停止' })
    stopButton.focus()
    fireEvent.click(stopButton)

    const stoppingButton = screen.getByRole('button', { name: '停止中' })
    expect((stoppingButton as HTMLButtonElement).disabled).toBe(true)
    stoppingButton.blur()
    act(() => finishStop())

    const sendButton = screen.getByRole('button', { name: '发送' })
    expect(document.activeElement).toBe(sendButton)
  })

  it('preserves the long-press quick reply gesture', () => {
    vi.useFakeTimers()
    const onQuickReply = vi.fn()
    renderComposer({ onQuickReply })
    const sendButton = screen.getByRole('button', { name: '发送' })

    fireEvent.pointerDown(sendButton, {
      pointerId: 1,
      button: 0,
      clientX: 20,
      clientY: 20,
    })
    act(() => {
      vi.advanceTimersByTime(400)
    })
    const option = screen.getByRole('option')
    Object.defineProperty(document, 'elementFromPoint', {
      configurable: true,
      value: vi.fn(() => option),
    })
    fireEvent.pointerMove(sendButton, {
      pointerId: 1,
      clientX: 20,
      clientY: 20,
    })
    fireEvent.pointerUp(sendButton, {
      pointerId: 1,
      clientX: 20,
      clientY: 20,
    })

    expect(onQuickReply).toHaveBeenCalledWith('我观察四周。')
  })
})
