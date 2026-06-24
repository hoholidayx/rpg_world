'use client'

import { DebugEventPanel } from '@/components/debug/DebugEventPanel'
import { StreamStatusBadge } from '@/components/debug/StreamStatusBadge'
import { CommandInput } from '@/components/input/CommandInput'
import { SceneHud } from '@/components/scene/SceneHud'
import { Timeline } from '@/components/timeline/Timeline'
import { useScene } from '@/features/scene/useScene'
import { useChatStream } from '@/features/stream/useChatStream'
import { usePlayUiStore } from '@/stores/playUiStore'

export function SessionRoom({ workspace, sessionId }: { workspace: string; sessionId: string }) {
  const { inputMode, setInputMode } = usePlayUiStore()
  const stream = useChatStream()
  const scene = useScene(workspace, sessionId)
  const streaming = ['connecting', 'streaming', 'thinking', 'tool_running'].includes(stream.status)

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
          <Timeline items={stream.timeline} />
        </div>
        <CommandInput
          mode={inputMode}
          disabled={streaming}
          onModeChange={setInputMode}
          onStop={stream.stop}
          onSend={(text) => stream.sendMessage({ workspace, sessionId, text, mode: inputMode })}
        />
      </section>
      <section className="space-y-4">
        <SceneHud scene={scene.data} />
        <DebugEventPanel events={stream.debugEvents} />
      </section>
    </main>
  )
}
