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
  const imageUrl = mediaAssetContentUrl(sessionId, background.assetId)

  return (
    <div className="pointer-events-none absolute inset-0 z-0 overflow-hidden bg-slate-950" aria-hidden="true">
      <img
        src={imageUrl}
        alt=""
        className="absolute inset-0 h-full w-full scale-110 object-cover object-center opacity-80 blur-xl"
      />
      <img
        src={imageUrl}
        alt=""
        className="absolute inset-0 h-full w-full object-contain object-center"
      />
      <div className="absolute inset-0 bg-slate-950/55" />
    </div>
  )
}
