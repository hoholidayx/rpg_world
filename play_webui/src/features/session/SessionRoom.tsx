'use client'

import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { DebugEventPanel } from '@/components/debug/DebugEventPanel'
import { StreamStatusBadge } from '@/components/debug/StreamStatusBadge'
import { CommandInput } from '@/components/input/CommandInput'
import { SceneHud } from '@/components/scene/SceneHud'
import { Timeline } from '@/components/timeline/Timeline'
import { useScene } from '@/features/scene/useScene'
import { useChatStream } from '@/features/stream/useChatStream'
import { listCommands } from '@/lib/api/commands'
import { getSessionHistory } from '@/lib/api/sessions'
import { usePlayUiStore } from '@/stores/playUiStore'
import type { TimelineItem } from '@/types/stream'

export function SessionRoom({ workspace, sessionId }: { workspace: string; sessionId: string }) {
  const { inputMode, setInputMode } = usePlayUiStore()
  const stream = useChatStream()
  const scene = useScene(workspace, sessionId)
  const history = useQuery({
    queryKey: ['play-history', workspace, sessionId],
    queryFn: () => getSessionHistory(workspace, sessionId),
  })
  const commands = useQuery({
    queryKey: ['play-commands', workspace, sessionId],
    queryFn: () => listCommands(workspace, sessionId),
  })
  const streaming = ['connecting', 'streaming', 'thinking', 'tool_running'].includes(stream.status)
  const timeline = useMemo<TimelineItem[]>(() => {
    const historyItems = (history.data ?? []).flatMap((turn) => {
      const createdAt = turn.createdAt ?? new Date().toISOString()
      const items: TimelineItem[] = [
        {
          id: `history-${turn.turnId}-user`,
          type: 'user',
          content: turn.userMessage,
          createdAt,
        },
      ]
      if (turn.assistantMessage) {
        items.push({
          id: `history-${turn.turnId}-assistant`,
          type: 'assistant',
          content: turn.assistantMessage,
          createdAt,
        })
      }
      return items
    })
    return [...historyItems, ...stream.timeline]
  }, [history.data, stream.timeline])

  return (
    <main className="grid min-h-screen gap-6 px-4 py-6 lg:grid-cols-[minmax(0,1fr)_320px] lg:px-8">
      <section className="flex min-h-[70vh] flex-col gap-4">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm text-muted">{workspace} / {sessionId}</p>
            <h1 className="text-2xl font-semibold">Play Session</h1>
          </div>
          <StreamStatusBadge status={stream.status} />
        </div>
        <div className="flex-1 overflow-y-auto rounded-3xl border border-white/10 bg-black/30 p-4">
          <Timeline items={timeline} />
        </div>
        <CommandInput
          mode={inputMode}
          disabled={streaming}
          commands={commands.data}
          onModeChange={setInputMode}
          onStop={stream.stop}
          onSend={(text) => stream.sendMessage({ workspace, sessionId, text, mode: inputMode })}
        />
      </section>
      <section className="space-y-4">
        <SceneHud scene={scene.data} />
        <aside className="rounded-3xl border border-white/10 bg-panel/80 p-5 shadow-2xl">
          <h2 className="text-lg font-semibold">快捷命令</h2>
          <div className="mt-4 space-y-3 text-sm">
            {(commands.data ?? []).map((command) => (
              <div key={command.name} className="rounded-2xl border border-white/10 bg-white/5 p-3">
                <div className="font-medium text-white">{command.name}</div>
                <div className="mt-1 text-muted">{command.description}</div>
              </div>
            ))}
          </div>
        </aside>
        <DebugEventPanel events={stream.debugEvents} />
      </section>
    </main>
  )
}
