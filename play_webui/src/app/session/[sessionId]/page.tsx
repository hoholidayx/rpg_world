import { SessionRoom } from '@/features/session/SessionRoom'

export default async function SessionPage({
  params,
  searchParams,
}: {
  params: Promise<{ sessionId: string }>
  searchParams: Promise<{ workspace?: string; story_id?: string }>
}) {
  const { sessionId } = await params
  const { workspace, story_id: storyIdParam } = await searchParams
  const storyId = Number(storyIdParam)
  if (!workspace || !Number.isInteger(storyId) || storyId <= 0) return <MissingSessionLocatorState />
  return <SessionRoom workspace={workspace} storyId={storyId} sessionId={sessionId} />
}

function MissingSessionLocatorState() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-[#f7f7fa] px-6 text-slate-900">
      <section className="w-full max-w-md rounded-xl border border-slate-200 bg-white p-6 text-center shadow-sm">
        <h1 className="text-lg font-bold">缺少会话定位信息</h1>
        <p className="mt-2 text-sm leading-6 text-slate-500">请从首页选择 workspace 与 story 后进入会话。</p>
      </section>
    </main>
  )
}
