'use client'

import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Eye, MessagesSquare, Sparkles, Trash2, type LucideIcon } from 'lucide-react'
import { listWorkspaces } from '@/lib/api/sessions'
import { ContextPreviewSettingsContainer } from './context-preview/ContextPreviewSettingsContainer'
import { DataCleanupSettingsContainer } from './cleanup/DataCleanupSettingsContainer'
import { SettingsWorkspaceSwitcher } from './SettingsWorkspaceSwitcher'
import { TurnModesSettingsContainer } from './turn-modes/TurnModesSettingsContainer'

type SettingsSection = 'turn-modes' | 'context-preview' | 'data-cleanup'

const settingsSections: Array<{
  id: SettingsSection
  label: string
  icon: LucideIcon
}> = [
  { id: 'turn-modes', label: '对话模式', icon: MessagesSquare },
  { id: 'context-preview', label: '上下文预览', icon: Eye },
  { id: 'data-cleanup', label: '数据清理', icon: Trash2 },
]

function Logo() {
  return (
    <div className="flex items-center gap-3">
      <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-violet-500 to-indigo-500 text-white shadow-lg shadow-violet-200">
        <Sparkles size={22} fill="currentColor" />
      </span>
      <span className="text-xl font-bold text-slate-950">RPG World Play</span>
    </div>
  )
}

export function SettingsPage() {
  const [currentWorkspace, setCurrentWorkspace] = useState<string | null>(null)
  const [activeSection, setActiveSection] = useState<SettingsSection>('context-preview')
  const workspacesQuery = useQuery({
    queryKey: ['play-workspaces'],
    queryFn: listWorkspaces,
  })
  const workspaceOptions = useMemo(() => workspacesQuery.data ?? [], [workspacesQuery.data])

  useEffect(() => {
    if (workspaceOptions.length === 0) {
      if (currentWorkspace !== null) setCurrentWorkspace(null)
      return
    }
    if (!currentWorkspace || !workspaceOptions.some((workspace) => workspace.id === currentWorkspace)) {
      setCurrentWorkspace(workspaceOptions[0].id)
    }
  }, [currentWorkspace, workspaceOptions])

  return (
    <main className="min-h-screen bg-[#f7f8fc] text-slate-900">
      <header className="sticky top-0 z-30 flex h-[72px] items-center justify-between border-b border-slate-200/80 bg-white/90 px-6 backdrop-blur">
        <div className="flex items-center gap-4">
          <Logo />
          <SettingsWorkspaceSwitcher
            value={currentWorkspace}
            workspaces={workspaceOptions}
            isLoading={workspacesQuery.isLoading}
            isError={workspacesQuery.isError}
            onChange={setCurrentWorkspace}
          />
        </div>
        <div className="hidden items-center gap-10 text-sm text-slate-900 md:flex">
          <span className="flex items-center gap-2">
            <span className="h-3 w-3 rounded-full bg-emerald-500" />
            Play API ready
          </span>
          <span className="flex items-center gap-2">
            <span className="h-3 w-3 rounded-full bg-emerald-500" />
            SSE ready
          </span>
        </div>
        <div className="flex items-center gap-3 rounded-full px-2 py-1 text-sm font-medium text-slate-900">
          <span className="flex h-10 w-10 items-center justify-center rounded-full bg-indigo-100 text-indigo-700">P</span>
          <span className="hidden sm:inline">Player One</span>
        </div>
      </header>

      <div className="grid min-h-[calc(100vh-72px)] lg:grid-cols-[296px_minmax(0,1fr)]">
        <aside className="hidden border-r border-slate-200 bg-white/70 px-6 py-9 lg:flex lg:flex-col lg:justify-between">
          <nav className="space-y-3">
            {settingsSections.map((section) => {
              const Icon = section.icon
              const selected = section.id === activeSection
              return (
                <button
                  key={section.id}
                  type="button"
                  onClick={() => setActiveSection(section.id)}
                  className={`flex w-full items-center gap-4 rounded-xl px-5 py-4 text-left text-base font-medium transition ${
                    selected
                      ? 'bg-violet-50 text-violet-700 shadow-sm'
                      : 'text-slate-500 hover:bg-slate-50 hover:text-slate-900'
                  }`}
                >
                  <Icon size={22} />
                  {section.label}
                </button>
              )
            })}
          </nav>

          <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <p className="mb-4 text-sm text-slate-400">系统状态</p>
            <div className="space-y-4 text-sm text-slate-600">
              <p className="flex items-center gap-3">
                <span className="h-2 w-2 rounded-full bg-emerald-500" />
                Agent Service ready
              </p>
              <p className="flex items-center gap-3">
                <span className="h-2 w-2 rounded-full bg-emerald-500" />
                Catalog DB ready
              </p>
            </div>
          </section>
        </aside>

        <div className="min-w-0 px-5 py-8 xl:px-7">
          <div className="mx-auto max-w-[1500px] space-y-6">
            <nav className="grid gap-2 rounded-lg border border-slate-200 bg-white p-2 shadow-sm sm:grid-cols-3 lg:hidden" aria-label="设置分区">
              {settingsSections.map((section) => {
                const Icon = section.icon
                const selected = section.id === activeSection
                return (
                  <button
                    key={section.id}
                    type="button"
                    onClick={() => setActiveSection(section.id)}
                    className={`flex h-11 items-center justify-center gap-2 rounded-md text-sm font-bold transition ${
                      selected ? 'bg-slate-950 text-white' : 'text-slate-500 hover:bg-slate-50 hover:text-slate-900'
                    }`}
                  >
                    <Icon size={16} />
                    {section.label}
                  </button>
                )
              })}
            </nav>
            {activeSection === 'turn-modes' ? (
              <TurnModesSettingsContainer workspaceId={currentWorkspace} />
            ) : activeSection === 'context-preview' ? (
              <ContextPreviewSettingsContainer workspaceId={currentWorkspace} />
            ) : (
              <DataCleanupSettingsContainer workspaceId={currentWorkspace} />
            )}
          </div>
        </div>
      </div>
    </main>
  )
}
