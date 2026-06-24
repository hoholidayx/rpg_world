'use client'

import { FormEvent, useState } from 'react'
import { Button } from '@/components/common/Button'
import type { InputMode, PlayCommand } from '@/types/command'
import { InputModeToggle } from './InputModeToggle'

export function CommandInput({ mode, disabled, commands, onModeChange, onSend, onStop }: {
  mode: InputMode
  disabled: boolean
  commands?: PlayCommand[]
  onModeChange: (mode: InputMode) => void
  onSend: (text: string) => void
  onStop: () => void
}) {
  const [text, setText] = useState('')
  const submit = (event: FormEvent) => {
    event.preventDefault()
    if (!text.trim() || disabled) return
    onSend(text.trim())
    setText('')
  }
  return (
    <form onSubmit={submit} className="rounded-3xl border border-white/10 bg-black/50 p-4 backdrop-blur">
      <div className="mb-3 flex items-center justify-between gap-3">
        <InputModeToggle value={mode} onChange={onModeChange} />
        {disabled ? <Button type="button" onClick={onStop}>停止</Button> : <Button type="submit">发送</Button>}
      </div>
      {commands?.length ? (
        <div className="mb-3 flex flex-wrap gap-2">
          {commands.map((command) => (
            <button
              key={command.name}
              type="button"
              onClick={() => setText(command.name)}
              className="rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 text-xs text-muted transition hover:border-accent/60 hover:text-white"
              title={command.description}
            >
              {command.name}
            </button>
          ))}
        </div>
      ) : null}
      <textarea
        value={text}
        onChange={(event) => setText(event.target.value)}
        placeholder="输入你的行动、台词或 GM 指令..."
        className="min-h-24 w-full resize-none rounded-2xl border border-white/10 bg-white/5 p-3 outline-none focus:border-accent"
      />
    </form>
  )
}
