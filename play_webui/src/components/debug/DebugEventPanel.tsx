import type { CurrentAgentStreamEvent } from '@/types/stream'

export function DebugEventPanel({ events }: { events: CurrentAgentStreamEvent[] }) {
  return (
    <details className="rounded-2xl border border-white/10 bg-black/30 p-4 text-xs text-muted">
      <summary className="cursor-pointer text-sm text-white">Debug Events ({events.length})</summary>
      <pre className="mt-3 max-h-72 overflow-auto whitespace-pre-wrap">{JSON.stringify(events, null, 2)}</pre>
    </details>
  )
}
