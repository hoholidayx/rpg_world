import { DreamMemoryPage } from '@/features/dream/DreamMemoryPage'

export default async function SessionDreamPage({
  params,
}: {
  params: Promise<{ sessionId: string }>
}) {
  const { sessionId } = await params
  return <DreamMemoryPage sessionId={sessionId} />
}
