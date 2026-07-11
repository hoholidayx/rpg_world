'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ChevronDown, Command, Loader2, Search, X } from 'lucide-react'
import { listCommands } from '@/lib/api/commands'
import { cn } from '@/lib/utils/cn'
import type { PlayCommand } from '@/types/command'

type CommandGroupId = 'play' | 'context' | 'system'

type CommandGroup = {
  id: CommandGroupId
  title: string
  commands: PlayCommand[]
}

const PLAY_COMMAND_ORDER = ['/roll', '/check_dc', '/rp_modules', '/rp_module']
const CONTEXT_COMMAND_ORDER = ['/compact', '/extract_story_memory', '/context', '/memory_reindex']

function commandGroupId(command: PlayCommand): CommandGroupId {
  if (PLAY_COMMAND_ORDER.includes(command.name) || command.name.startsWith('/rp_')) return 'play'
  if (CONTEXT_COMMAND_ORDER.includes(command.name)) return 'context'
  return 'system'
}

function commandRank(command: PlayCommand, groupId: CommandGroupId) {
  const order = groupId === 'play' ? PLAY_COMMAND_ORDER : CONTEXT_COMMAND_ORDER
  const index = order.indexOf(command.name)
  return index === -1 ? order.length : index
}

function groupCommands(commands: PlayCommand[]): CommandGroup[] {
  const groups: Record<CommandGroupId, PlayCommand[]> = {
    play: [],
    context: [],
    system: [],
  }

  commands.forEach((command) => groups[commandGroupId(command)].push(command))
  groups.play.sort((left, right) => commandRank(left, 'play') - commandRank(right, 'play'))
  groups.context.sort((left, right) => commandRank(left, 'context') - commandRank(right, 'context'))

  return [
    { id: 'play', title: '游玩工具', commands: groups.play },
    { id: 'context', title: '上下文与记忆', commands: groups.context },
    { id: 'system', title: '会话与系统', commands: groups.system },
  ]
}

function matchesSearch(command: PlayCommand, search: string) {
  const normalized = search.trim().toLocaleLowerCase()
  if (!normalized) return true
  return [command.name, command.description, command.detail]
    .some((value) => value.toLocaleLowerCase().includes(normalized))
}

export function CommandPaletteDialog({
  sessionId,
  disabled = false,
  onSelectCommand,
}: {
  sessionId: string
  disabled?: boolean
  onSelectCommand: (command: string) => void
}) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const [systemOpen, setSystemOpen] = useState(false)
  const triggerRef = useRef<HTMLButtonElement | null>(null)
  const titleId = `command-palette-title-${sessionId}`
  const descriptionId = `command-palette-description-${sessionId}`
  const commandsQuery = useQuery({
    queryKey: ['play-session-commands', sessionId],
    queryFn: () => listCommands(sessionId),
    enabled: open && !disabled,
  })

  useEffect(() => {
    if (!open) return
    const handleKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key !== 'Escape') return
      setOpen(false)
      requestAnimationFrame(() => triggerRef.current?.focus())
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [open])

  useEffect(() => {
    if (!disabled || !open) return
    setOpen(false)
  }, [disabled, open])

  const groupedCommands = useMemo(() => {
    const filtered = (commandsQuery.data ?? []).filter((command) => matchesSearch(command, search))
    return groupCommands(filtered)
  }, [commandsQuery.data, search])
  const visibleCommandCount = groupedCommands.reduce((total, group) => total + group.commands.length, 0)
  const hasSearch = Boolean(search.trim())

  const openDialog = () => {
    setSearch('')
    setSystemOpen(false)
    setOpen(true)
  }

  const closeDialog = () => {
    setOpen(false)
    requestAnimationFrame(() => triggerRef.current?.focus())
  }

  const selectCommand = (command: string) => {
    onSelectCommand(command)
    setOpen(false)
  }

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        data-session-id={sessionId}
        disabled={disabled}
        onClick={openDialog}
        className={cn(
          'flex h-9 items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 text-xs font-black text-slate-600 shadow-sm transition hover:border-violet-200 hover:bg-violet-50 hover:text-violet-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:shadow-black/30 dark:hover:border-violet-500/60 dark:hover:bg-violet-500/10 dark:hover:text-violet-100',
          disabled ? 'cursor-not-allowed opacity-60' : '',
        )}
      >
        <Command size={14} />
        命令
      </button>

      {open ? (
        <div
          className="fixed inset-0 z-50 flex items-end justify-center bg-slate-950/35 px-3 py-4 sm:items-center sm:px-4"
          onClick={closeDialog}
        >
          <section
            role="dialog"
            aria-modal="true"
            aria-labelledby={titleId}
            aria-describedby={descriptionId}
            data-session-id={sessionId}
            onClick={(event) => event.stopPropagation()}
            className="flex max-h-[min(78vh,680px)] w-full max-w-2xl flex-col overflow-hidden rounded-xl border border-slate-200 bg-white shadow-2xl shadow-slate-950/20 dark:border-slate-700 dark:bg-slate-950 dark:shadow-black/50"
          >
            <header className="flex items-start justify-between gap-4 border-b border-slate-200 px-5 py-4 dark:border-slate-800">
              <div>
                <h2 id={titleId} className="text-lg font-black text-slate-950 dark:text-slate-100">命令</h2>
                <p id={descriptionId} className="mt-1 text-xs font-semibold text-slate-500 dark:text-slate-300">
                  选择后填入输入框，不会立即执行
                </p>
              </div>
              <button
                type="button"
                onClick={closeDialog}
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-slate-400 transition hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800 dark:hover:text-slate-100"
                aria-label="关闭命令面板"
              >
                <X size={17} />
              </button>
            </header>

            <div className="border-b border-slate-200 px-5 py-3 dark:border-slate-800">
              <div className="flex h-10 items-center gap-3 rounded-lg border border-slate-200 bg-slate-50 px-3 focus-within:border-violet-300 focus-within:bg-white dark:border-slate-700 dark:bg-slate-900 dark:focus-within:border-violet-500 dark:focus-within:bg-slate-950">
                <Search size={15} className="shrink-0 text-slate-400" />
                <input
                  autoFocus
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  className="min-w-0 flex-1 border-0 bg-transparent text-sm font-semibold text-slate-950 outline-none placeholder:text-slate-400 dark:text-slate-100 dark:placeholder:text-slate-500"
                  placeholder="搜索命令或用途"
                  aria-label="搜索命令"
                />
                {search ? (
                  <button
                    type="button"
                    onClick={() => setSearch('')}
                    className="flex h-6 w-6 items-center justify-center rounded text-slate-400 hover:bg-slate-200 hover:text-slate-700 dark:hover:bg-slate-800 dark:hover:text-slate-100"
                    aria-label="清空搜索"
                  >
                    <X size={14} />
                  </button>
                ) : null}
              </div>
            </div>

            <div className="min-h-40 overflow-y-auto px-3 py-3 sm:px-5">
              {commandsQuery.isLoading ? (
                <div role="status" className="flex min-h-36 flex-col items-center justify-center gap-3 text-sm font-semibold text-slate-500 dark:text-slate-300">
                  <Loader2 size={20} className="animate-spin text-violet-500" />
                  正在加载当前会话的命令…
                </div>
              ) : commandsQuery.isError ? (
                <div role="alert" className="flex min-h-36 flex-col items-center justify-center gap-3 px-4 text-center">
                  <p className="text-sm font-bold text-slate-700 dark:text-slate-200">命令加载失败</p>
                  <p className="text-xs font-semibold text-slate-500 dark:text-slate-400">
                    {commandsQuery.error instanceof Error ? commandsQuery.error.message : '请稍后重试'}
                  </p>
                  <button
                    type="button"
                    onClick={() => void commandsQuery.refetch()}
                    className="rounded-lg bg-violet-600 px-3 py-2 text-xs font-black text-white transition hover:bg-violet-700"
                  >
                    重新加载
                  </button>
                </div>
              ) : visibleCommandCount === 0 ? (
                <div role="status" className="flex min-h-36 items-center justify-center px-4 text-center text-sm font-semibold text-slate-500 dark:text-slate-300">
                  {hasSearch ? '没有匹配的命令' : '当前会话没有可用命令'}
                </div>
              ) : (
                <div className="space-y-4">
                  {groupedCommands.map((group) => {
                    if (group.commands.length === 0) return null
                    const collapsible = group.id === 'system'
                    const expanded = !collapsible || systemOpen || hasSearch
                    return (
                      <section key={group.id}>
                        {collapsible ? (
                          <button
                            type="button"
                            aria-expanded={expanded}
                            onClick={() => setSystemOpen((current) => !current)}
                            className="mb-1 flex w-full items-center justify-between rounded-lg px-2 py-1.5 text-left text-xs font-black text-slate-500 transition hover:bg-slate-50 hover:text-slate-800 dark:text-slate-300 dark:hover:bg-slate-900 dark:hover:text-slate-100"
                          >
                            <span>{group.title} · {group.commands.length}</span>
                            <ChevronDown size={14} className={cn('transition', expanded ? 'rotate-180' : '')} />
                          </button>
                        ) : (
                          <h3 className="mb-1 px-2 py-1 text-xs font-black text-violet-600 dark:text-violet-300">
                            {group.title}
                          </h3>
                        )}

                        {expanded ? (
                          <div className="space-y-1">
                            {group.commands.map((command) => (
                              <button
                                key={command.name}
                                type="button"
                                onClick={() => selectCommand(command.name)}
                                className="w-full rounded-lg px-3 py-2.5 text-left transition hover:bg-violet-50 focus-visible:bg-violet-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-300 dark:hover:bg-violet-500/10 dark:focus-visible:bg-violet-500/10 dark:focus-visible:ring-violet-500"
                                aria-label={`选择命令 ${command.name}`}
                              >
                                <span className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                                  <code className="font-mono text-sm font-black text-violet-700 dark:text-violet-200">{command.name}</code>
                                  <span className="text-sm font-bold text-slate-700 dark:text-slate-200">{command.description}</span>
                                </span>
                                {command.detail ? (
                                  <span className="mt-1 block text-xs font-semibold leading-5 text-slate-500 dark:text-slate-400">
                                    {command.detail}
                                  </span>
                                ) : null}
                              </button>
                            ))}
                          </div>
                        ) : null}
                      </section>
                    )
                  })}
                </div>
              )}
            </div>
          </section>
        </div>
      ) : null}
    </>
  )
}
