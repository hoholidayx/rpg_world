'use client'

import { useState } from 'react'
import { Check, ChevronDown, FolderOpen } from 'lucide-react'
import type { WorkspaceSummary } from '@/types/session'

type SettingsWorkspaceSwitcherProps = {
  value: string | null
  workspaces: WorkspaceSummary[]
  isLoading: boolean
  isError: boolean
  onChange: (workspace: string | null) => void
}

export function SettingsWorkspaceSwitcher({
  value,
  workspaces,
  isLoading,
  isError,
  onChange,
}: SettingsWorkspaceSwitcherProps) {
  const [open, setOpen] = useState(false)
  const selectedWorkspace = value ? workspaces.find((workspace) => workspace.id === value) : null
  const label = selectedWorkspace?.name ?? (isLoading ? '加载中' : isError ? '加载失败' : '暂无 workspace')

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((isOpen) => !isOpen)}
        className="flex h-10 items-center gap-2 rounded-full border border-slate-200 bg-white px-3 text-sm font-medium text-slate-900 shadow-sm transition hover:border-violet-200 hover:bg-violet-50/70 hover:text-violet-700"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="切换 workspace"
      >
        <FolderOpen size={16} className="text-slate-400" />
        <span className="hidden text-slate-500 sm:inline">Workspace</span>
        <span className="max-w-36 truncate font-semibold">{label}</span>
        <ChevronDown size={16} className={`text-slate-400 transition ${open ? 'rotate-180 text-violet-500' : ''}`} />
      </button>
      {open ? (
        <div className="absolute left-0 top-full z-40 mt-2 w-64 overflow-hidden rounded-xl border border-slate-200 bg-white p-1 shadow-xl shadow-slate-200/70" role="menu">
          {workspaces.length ? workspaces.map((workspace) => {
            const selected = workspace.id === value

            return (
              <button
                key={workspace.id}
                type="button"
                onClick={() => {
                  onChange(workspace.id)
                  setOpen(false)
                }}
                className={`flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm transition ${
                  selected ? 'bg-violet-50 text-violet-700' : 'text-slate-700 hover:bg-slate-50 hover:text-slate-950'
                }`}
                role="menuitem"
              >
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-slate-500">
                  <FolderOpen size={16} />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-semibold">{workspace.name}</span>
                  {workspace.description ? <span className="mt-0.5 block truncate text-xs text-slate-500">{workspace.description}</span> : null}
                </span>
                {selected ? <Check size={16} className="shrink-0 text-violet-600" /> : null}
              </button>
            )
          }) : (
            <div className="px-3 py-2.5 text-sm text-slate-500">
              {isError ? 'workspace 加载失败' : '暂无 workspace'}
            </div>
          )}
        </div>
      ) : null}
    </div>
  )
}
