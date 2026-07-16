import { useEffect, useRef, useState } from 'react'
import { MediaImageFrame } from '@/components/common/MediaImageFrame'
import { mediaAssetContentUrl } from '@/lib/api/media'
import { sessionMediaConfig } from '@/lib/config/appConfig'
import type { MediaDisplayAsset } from '@/types/media'

type SceneLayer = {
  key: string
  asset: MediaDisplayAsset
  url: string
}

function layerFor(
  sessionId: string,
  background: MediaDisplayAsset | null,
  revisionToken: string,
): SceneLayer | null {
  if (!background) return null
  return {
    key: `${sessionId}:${revisionToken}:${background.assetId}`,
    asset: background,
    url: mediaAssetContentUrl(sessionId, background.assetId),
  }
}

function BackgroundLayer({ layer, opacity }: { layer: SceneLayer; opacity: number }) {
  return (
    <MediaImageFrame
      src={layer.url}
      alt={layer.asset.title}
      decorative
      loading="eager"
      className="absolute inset-0 overflow-hidden bg-slate-950 transition-opacity ease-in-out"
      style={{ opacity, transitionDuration: `${sessionMediaConfig.backgroundCrossfadeMs}ms` }}
    >
      <div className="absolute inset-0 bg-slate-950/55" />
    </MediaImageFrame>
  )
}

export function SessionMediaBackground({
  sessionId,
  background,
  revisionToken,
}: {
  sessionId: string
  background: MediaDisplayAsset | null
  revisionToken: string
}) {
  const initial = layerFor(sessionId, background, revisionToken)
  const [front, setFront] = useState<SceneLayer | null>(initial)
  const [back, setBack] = useState<SceneLayer | null>(null)
  const [frontOpacity, setFrontOpacity] = useState(initial ? 1 : 0)
  const currentRef = useRef<SceneLayer | null>(initial)
  const cleanupTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    const next = layerFor(sessionId, background, revisionToken)
    if (next?.key === currentRef.current?.key || (!next && !currentRef.current)) return
    let cancelled = false

    const reveal = (prepared: SceneLayer | null) => {
      if (cancelled) return
      if (cleanupTimerRef.current) clearTimeout(cleanupTimerRef.current)
      setBack(currentRef.current)
      setFront(prepared)
      currentRef.current = prepared
      setFrontOpacity(prepared ? 0 : 1)
      requestAnimationFrame(() => requestAnimationFrame(() => {
        if (!cancelled) setFrontOpacity(prepared ? 1 : 0)
      }))
      cleanupTimerRef.current = setTimeout(() => {
        if (!cancelled) setBack(null)
      }, sessionMediaConfig.backgroundCrossfadeMs)
    }

    if (!next) {
      reveal(null)
    } else {
      const image = new window.Image()
      image.onload = () => reveal(next)
      image.src = next.url
    }
    return () => {
      cancelled = true
    }
  }, [background, revisionToken, sessionId])

  useEffect(() => () => {
    if (cleanupTimerRef.current) clearTimeout(cleanupTimerRef.current)
  }, [])

  if (!front && !back) return null
  return (
    <div className="pointer-events-none absolute inset-0 z-0 overflow-hidden bg-slate-950" aria-hidden="true">
      {back ? <BackgroundLayer layer={back} opacity={front ? 1 : frontOpacity} /> : null}
      {front ? <BackgroundLayer layer={front} opacity={frontOpacity} /> : null}
    </div>
  )
}
