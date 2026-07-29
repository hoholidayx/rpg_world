import { describe, expect, it, vi } from 'vitest'
import {
  createTimelineScrollScheduler,
  isTimelineNearBottom,
  resolveTimelineScrollBehavior,
  TIMELINE_SCROLL_TARGET,
} from './sessionTimelineScroll'

describe('sessionTimelineScroll', () => {
  it('coalesces pending scrolls and only scrolls the supplied timeline container', () => {
    const frames = new Map<number, FrameRequestCallback>()
    let nextFrame = 0
    const requestFrame = vi.fn((callback: FrameRequestCallback) => {
      nextFrame += 1
      frames.set(nextFrame, callback)
      return nextFrame
    })
    const cancelFrame = vi.fn((handle: number) => {
      frames.delete(handle)
    })
    const scrollTo = vi.fn()
    const container = { scrollHeight: 2400, scrollTo }
    const scheduler = createTimelineScrollScheduler({
      requestFrame,
      cancelFrame,
      prefersReducedMotion: () => false,
    })

    scheduler.schedule(container, TIMELINE_SCROLL_TARGET.TOP, 'auto')
    scheduler.schedule(container, TIMELINE_SCROLL_TARGET.BOTTOM, 'auto')

    expect(cancelFrame).toHaveBeenCalledWith(1)
    expect(frames.size).toBe(1)
    frames.get(2)?.(0)
    expect(scrollTo).toHaveBeenCalledTimes(1)
    expect(scrollTo).toHaveBeenCalledWith({ top: 2400, behavior: 'auto' })
  })

  it('turns smooth scrolling off when reduced motion is requested', () => {
    expect(resolveTimelineScrollBehavior('smooth', true)).toBe('auto')
    expect(resolveTimelineScrollBehavior('smooth', false)).toBe('smooth')
    expect(resolveTimelineScrollBehavior('auto', true)).toBe('auto')
  })

  it('only sticks while the reader remains near the bottom threshold', () => {
    expect(isTimelineNearBottom({
      scrollHeight: 2000,
      scrollTop: 1360,
      clientHeight: 500,
      thresholdPx: 160,
    })).toBe(true)
    expect(isTimelineNearBottom({
      scrollHeight: 2000,
      scrollTop: 900,
      clientHeight: 500,
      thresholdPx: 160,
    })).toBe(false)
  })
})
