import { mediaAssetContentUrl } from '@/lib/api/media'
import type { MediaGalleryItem } from '@/types/media'

export function SessionMediaBackground({
  sessionId,
  background,
}: {
  sessionId: string
  background: MediaGalleryItem | null
}) {
  if (!background) return null

  return (
    <div className="pointer-events-none absolute inset-0 z-0 overflow-hidden" aria-hidden="true">
      <img
        src={mediaAssetContentUrl(sessionId, background.assetId)}
        alt=""
        className="absolute -inset-2 h-[calc(100%+1rem)] w-[calc(100%+1rem)] scale-[1.02] object-cover blur-[2px]"
      />
      <div className="absolute inset-0 bg-slate-950/55" />
    </div>
  )
}
