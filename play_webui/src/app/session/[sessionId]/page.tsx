import { SessionRoom } from '@/features/session/SessionRoom'

export default async function SessionPage({
  params,
}: {
  params: Promise<{ sessionId: string }>
}) {
  const { sessionId } = await params
  // 会话页 URL 只承载全局 sessionId，workspace/story 由 Play API 反查。
  return <SessionRoom sessionId={sessionId} />
}
