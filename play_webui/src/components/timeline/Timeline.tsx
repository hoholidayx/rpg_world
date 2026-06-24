import type { TimelineItem as TimelineItemType } from '@/types/stream'
import { TimelineItem } from './TimelineItem'

export function Timeline({ items }: { items: TimelineItemType[] }) {
  if (items.length === 0) {
    return <div className="rounded-3xl border border-dashed border-white/10 p-8 text-center text-muted">等待你开启这一幕。</div>
  }
  return <div className="space-y-4">{items.map((item) => <TimelineItem key={item.id} item={item} />)}</div>
}
