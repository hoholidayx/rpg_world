export const TIMELINE_SCROLL_TARGET = {
  TOP: 'top',
  BOTTOM: 'bottom',
} as const

export type TimelineScrollTarget = (
  typeof TIMELINE_SCROLL_TARGET[keyof typeof TIMELINE_SCROLL_TARGET]
)

type ScrollContainer = Pick<HTMLDivElement, 'scrollHeight' | 'scrollTo'>

export function resolveTimelineScrollBehavior(
  behavior: ScrollBehavior,
  prefersReducedMotion: boolean,
): ScrollBehavior {
  return behavior === 'smooth' && prefersReducedMotion ? 'auto' : behavior
}

export function isTimelineNearBottom({
  scrollHeight,
  scrollTop,
  clientHeight,
  thresholdPx,
}: {
  scrollHeight: number
  scrollTop: number
  clientHeight: number
  thresholdPx: number
}) {
  return scrollHeight - scrollTop - clientHeight < thresholdPx
}

export function createTimelineScrollScheduler({
  requestFrame,
  cancelFrame,
  prefersReducedMotion,
}: {
  requestFrame: (callback: FrameRequestCallback) => number
  cancelFrame: (handle: number) => void
  prefersReducedMotion: () => boolean
}) {
  let pendingFrame: number | null = null

  return {
    schedule(
      container: ScrollContainer,
      target: TimelineScrollTarget,
      behavior: ScrollBehavior,
    ) {
      if (pendingFrame !== null) cancelFrame(pendingFrame)
      pendingFrame = requestFrame(() => {
        pendingFrame = null
        container.scrollTo({
          top: target === TIMELINE_SCROLL_TARGET.BOTTOM ? container.scrollHeight : 0,
          behavior: resolveTimelineScrollBehavior(behavior, prefersReducedMotion()),
        })
      })
    },
    cancel() {
      if (pendingFrame === null) return
      cancelFrame(pendingFrame)
      pendingFrame = null
    },
  }
}
