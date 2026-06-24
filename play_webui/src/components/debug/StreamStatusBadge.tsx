import type { StreamStatus } from '@/types/stream'

export function StreamStatusBadge({ status }: { status: StreamStatus }) {
  return <span className="rounded-full border border-white/10 bg-white/10 px-3 py-1 text-xs text-muted">{status}</span>
}
