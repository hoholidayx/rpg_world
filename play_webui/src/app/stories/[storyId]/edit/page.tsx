import { StoryEditPage } from '@/features/stories/StoryEditPage'

export default async function Page({
  params,
}: {
  params: Promise<{ storyId: string }>
}) {
  const { storyId } = await params
  return <StoryEditPage storyId={Number(storyId)} />
}
