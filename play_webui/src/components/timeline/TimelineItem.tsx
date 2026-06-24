import type { TimelineItem as TimelineItemType } from '@/types/stream'

export function TimelineItem({ item }: { item: TimelineItemType }) {
  const tone = {
    user: 'border-accent/40 bg-accent/10',
    assistant: 'border-white/10 bg-white/5',
    thinking: 'border-blue-400/30 bg-blue-400/10 text-blue-100',
    tool: 'border-amber-400/30 bg-amber-400/10 text-amber-100',
    error: 'border-red-400/40 bg-red-400/10 text-red-100',
    system: 'border-white/10 bg-white/5 text-muted',
  }[item.type]
  return <article className={`rounded-2xl border p-4 leading-7 ${tone}`}>{item.content}</article>
}
