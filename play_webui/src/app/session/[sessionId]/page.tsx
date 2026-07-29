import type { Viewport } from 'next'
import { SessionRoom } from '@/features/session/SessionRoom'

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  viewportFit: 'cover',
  interactiveWidget: 'resizes-content',
}

export default async function SessionPage({
  params,
}: {
  params: Promise<{ sessionId: string }>
}) {
  const { sessionId } = await params
  // 会话页 URL 只承载全局 sessionId，workspace/story 由 Play API 反查。
  return <SessionRoom sessionId={sessionId} />
}
