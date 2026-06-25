'use client'

import { useState } from 'react'
import { Plane, Square } from 'lucide-react'

export function SendStopButton({ workspace, storyId, sessionId }: { workspace: string; storyId: number; sessionId: string }) {
  const [isSending, setIsSending] = useState(false)
  const Icon = isSending ? Square : Plane
  const label = isSending ? '停止' : '发送'

  return (
    <button
      type="button"
      data-workspace={workspace}
      data-story-id={storyId}
      data-session-id={sessionId}
      aria-pressed={isSending}
      onClick={() => setIsSending((current) => !current)}
      className={`my-1 flex min-h-24 w-full items-center justify-center gap-2 rounded-2xl px-6 text-base font-bold text-white shadow-lg transition ${
        isSending
          ? 'bg-rose-500 shadow-rose-100 hover:bg-rose-600'
          : 'bg-violet-600 shadow-violet-200 hover:bg-violet-700'
      }`}
    >
      <Icon size={17} fill="currentColor" />
      {label}
    </button>
  )
}
