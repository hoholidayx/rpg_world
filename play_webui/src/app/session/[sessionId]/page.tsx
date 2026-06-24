import { SessionRoom } from '@/features/session/SessionRoom'

export default async function SessionPage({
  params,
  searchParams,
}: {
  params: Promise<{ sessionId: string }>
  searchParams: Promise<{ workspace?: string }>
}) {
  const { sessionId } = await params
  const { workspace = 'default' } = await searchParams
  return <SessionRoom workspace={workspace} sessionId={sessionId} />
}
