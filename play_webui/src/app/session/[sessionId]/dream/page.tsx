import { DreamMemoryPage } from '@/features/dream/DreamMemoryPage'
import { resolveDreamReturnTarget } from '@/features/dream/dreamNavigation'

export default async function SessionDreamPage({
  params,
  searchParams,
}: {
  params: Promise<{ sessionId: string }>
  searchParams: Promise<{ returnTo?: string | string[] }>
}) {
  const { sessionId } = await params
  const { returnTo } = await searchParams
  return (
    <DreamMemoryPage
      sessionId={sessionId}
      returnTarget={resolveDreamReturnTarget(returnTo, sessionId)}
    />
  )
}
