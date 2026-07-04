'use client'

import { KeyboardEvent, useState } from 'react'
import { Command, Search, X } from 'lucide-react'

type CommandItem = {
  command: string
  signature: string
  description: string
  shortcut: string
  active?: boolean
}

type CommandGroup = {
  title: string
  commands: CommandItem[]
}

const commandGroups: CommandGroup[] = [
  {
    title: '场景相关',
    commands: [
      {
        command: '/scene',
        signature: '[名称] [描述]',
        description: '切换或创建当前场景，设置场景描述与氛围。',
        shortcut: 'Enter',
        active: true,
      },
    ],
  },
  {
    title: '角色与互动',
    commands: [
      {
        command: '/npc',
        signature: '[名称] [操作]',
        description: '与 NPC 互动、查询或管理 NPC 信息。',
        shortcut: 'Ctrl+2',
      },
    ],
  },
  {
    title: '状态与信息',
    commands: [
      {
        command: '/status',
        signature: '',
        description: '查看角色状态、属性、装备与资源。',
        shortcut: 'Ctrl+3',
      },
    ],
  },
  {
    title: '检定与骰子',
    commands: [
      {
        command: '/roll 1d20',
        signature: '[修正值] [标签]',
        description: '进行骰子检定，支持任意骰子表达式。',
        shortcut: 'Ctrl+R',
      },
    ],
  },
]

export function CommandPaletteDialog({ sessionId }: { sessionId: string }) {
  const [open, setOpen] = useState(false)

  const closeOnEscape = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Escape') {
      setOpen(false)
    }
  }

  return (
    <>
      <button
        type="button"
        data-session-id={sessionId}
        onClick={() => setOpen(true)}
        className="flex items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 text-sm font-bold text-slate-600 transition hover:border-violet-200 hover:text-violet-700 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:border-violet-500/60 dark:hover:text-violet-200"
      >
        <Command size={15} />
        命令面板
      </button>

      {open ? (
        <div className="fixed inset-0 z-50 flex items-end justify-center bg-slate-950/10 px-4 py-6 backdrop-blur-[1px] dark:bg-slate-950/60 sm:items-center">
          <section
            role="dialog"
            aria-modal="true"
            aria-label="命令面板"
            tabIndex={-1}
            data-session-id={sessionId}
            onKeyDown={closeOnEscape}
            className="flex max-h-[92vh] w-full max-w-5xl flex-col overflow-hidden rounded-[28px] border border-slate-200 bg-white shadow-2xl shadow-slate-300/70 dark:border-slate-700 dark:bg-slate-950 dark:shadow-black/50"
          >
            <header className="flex items-center justify-between border-b border-slate-200 px-7 py-6 dark:border-slate-800">
              <h2 className="text-2xl font-bold text-slate-950 dark:text-slate-100">命令面板 / Composer 局部</h2>
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="flex h-10 w-10 items-center justify-center rounded-xl text-slate-400 transition hover:bg-slate-100 hover:text-slate-700 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100"
                aria-label="关闭命令面板"
              >
                <X size={18} />
              </button>
            </header>

            <div className="mx-7 mt-5 overflow-hidden rounded-2xl border border-slate-200 dark:border-slate-700">
              <div className="flex items-center justify-between gap-4 border-b border-slate-200 bg-white px-4 py-3 dark:border-slate-800 dark:bg-slate-900">
                <div className="flex min-w-0 flex-1 items-center gap-3">
                  <Search size={16} className="shrink-0 text-slate-500 dark:text-slate-300" />
                  <input
                    autoFocus
                    defaultValue="/sc"
                    className="min-w-0 flex-1 border-0 bg-transparent text-lg text-slate-950 outline-none dark:text-slate-100"
                    aria-label="搜索命令"
                  />
                </div>
                <span className="text-sm text-slate-500 dark:text-slate-300">ESC 关闭</span>
              </div>

              <div className="max-h-[48vh] overflow-y-auto px-4 py-5">
                {commandGroups.map((group) => (
                  <section key={group.title} className="mb-5 last:mb-0">
                    <h3 className="mb-2 text-sm font-bold text-violet-600 dark:text-violet-300">{group.title}</h3>
                    <div className="space-y-2">
                      {group.commands.map((item) => (
                        <button
                          key={item.command}
                          type="button"
                          className={`flex w-full items-center justify-between rounded-xl px-4 py-3 text-left transition ${
                            item.active ? 'bg-slate-50 dark:bg-slate-900' : 'hover:bg-slate-50 dark:hover:bg-slate-900'
                          }`}
                        >
                          <span className="min-w-0">
                            <span className="mr-2 rounded-md bg-violet-100 px-2 py-1 font-bold text-violet-700 dark:bg-violet-500/15 dark:text-violet-200">{item.command}</span>
                            {item.signature ? <span className="font-bold text-slate-950 dark:text-slate-100">{item.signature}</span> : null}
                            <span className="mt-2 block text-sm text-slate-500 dark:text-slate-300">{item.description}</span>
                          </span>
                          <span className="ml-4 shrink-0 text-sm text-slate-400 dark:text-slate-300">{item.shortcut}</span>
                        </button>
                      ))}
                    </div>
                  </section>
                ))}
              </div>

              <footer className="flex flex-wrap items-center justify-end gap-3 border-t border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-500 dark:border-slate-800 dark:bg-slate-900/80 dark:text-slate-300">
                <span className="rounded-lg border border-slate-200 bg-white px-2 py-1 font-semibold text-slate-600 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-300">↑</span>
                <span className="rounded-lg border border-slate-200 bg-white px-2 py-1 font-semibold text-slate-600 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-300">↓</span>
                <span>选择</span>
                <span className="rounded-lg border border-slate-200 bg-white px-2 py-1 font-semibold text-slate-600 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-300">Enter</span>
                <span>执行</span>
                <span className="rounded-lg border border-slate-200 bg-white px-2 py-1 font-semibold text-slate-600 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-300">Esc</span>
                <span>取消</span>
              </footer>
            </div>

            <div className="grid grid-cols-[minmax(0,1fr)_116px] gap-4 px-7 py-5">
              <textarea
                className="min-h-20 resize-none rounded-2xl border border-slate-200 bg-white px-4 py-4 text-base text-slate-900 outline-none placeholder:text-slate-400 focus:border-violet-300 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 dark:placeholder:text-slate-500 dark:focus:border-violet-500"
                placeholder="输入你的行动、台词或 GM 指令..."
              />
              <button
                type="button"
                className="flex items-center justify-center rounded-2xl bg-violet-600 px-5 text-base font-bold text-white shadow-lg shadow-violet-200 transition hover:bg-violet-700 dark:shadow-violet-950/40"
              >
                发送
              </button>
            </div>
          </section>
        </div>
      ) : null}
    </>
  )
}
