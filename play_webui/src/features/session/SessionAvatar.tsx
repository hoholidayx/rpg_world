import { cn } from '@/lib/utils/cn'
import type { SessionSpeaker } from './sessionRoomTypes'

const toneClass = {
  player: 'bg-violet-100 text-violet-700 ring-violet-100 dark:bg-violet-500/20 dark:text-violet-100 dark:ring-violet-500/20',
  assistant: 'bg-slate-200 text-slate-700 ring-slate-100 dark:bg-slate-700 dark:text-slate-100 dark:ring-slate-800',
  tool: 'bg-sky-100 text-sky-700 ring-sky-100 dark:bg-sky-500/20 dark:text-sky-100 dark:ring-sky-500/20',
  system: 'bg-slate-100 text-slate-500 ring-slate-100 dark:bg-slate-800 dark:text-slate-300 dark:ring-slate-700',
  thinking: 'bg-amber-100 text-amber-700 ring-amber-100 dark:bg-amber-500/20 dark:text-amber-100 dark:ring-amber-500/20',
  error: 'bg-rose-100 text-rose-700 ring-rose-100 dark:bg-rose-500/20 dark:text-rose-100 dark:ring-rose-500/20',
}

export function SessionAvatar({ speaker, className }: { speaker: SessionSpeaker; className?: string }) {
  return (
    <span
      className={cn(
        'flex h-11 w-11 shrink-0 items-center justify-center overflow-hidden rounded-full text-sm font-black ring-4',
        toneClass[speaker.tone],
        className,
      )}
      aria-label={`${speaker.name}头像`}
    >
      {speaker.avatarUrl ? (
        <img src={speaker.avatarUrl} alt="" className="h-full w-full object-cover" />
      ) : (
        speaker.fallback
      )}
    </span>
  )
}
