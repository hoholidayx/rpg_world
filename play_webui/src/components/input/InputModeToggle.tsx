'use client'

import type { InputMode } from '@/types/command'

const modes: InputMode[] = ['ic', 'ooc', 'gm', 'slash']

export function InputModeToggle({ value, onChange }: { value: InputMode; onChange: (mode: InputMode) => void }) {
  return (
    <div className="flex gap-2">
      {modes.map((mode) => (
        <button
          key={mode}
          type="button"
          onClick={() => onChange(mode)}
          className={`rounded-full px-3 py-1 text-xs ${value === mode ? 'bg-accent text-white' : 'bg-white/10 text-muted'}`}
        >
          {mode.toUpperCase()}
        </button>
      ))}
    </div>
  )
}
