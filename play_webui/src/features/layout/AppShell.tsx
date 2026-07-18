'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  BookOpen,
  Check,
  ChevronDown,
  Clock3,
  FolderOpen,
  Globe2,
  Home,
  Images,
  Menu,
  Settings,
  Sparkles,
  TableProperties,
  UsersRound,
  WandSparkles,
  X,
} from 'lucide-react'
import { ThemeSwitcher } from '@/components/theme/ThemeSwitcher'
import { NotificationCenter } from '@/features/notifications/NotificationCenter'
import { listWorkspaces } from '@/lib/api/sessions'
import type { WorkspaceSummary } from '@/types/session'

type AppShellState = {
  currentWorkspace: string | null
  workspaces: WorkspaceSummary[]
}

type AppShellProps = {
  children: ReactNode | ((state: AppShellState) => ReactNode)
}

const AppShellContext = createContext<AppShellState | null>(null)

const navItems = [
  { label: '首页', icon: Home, href: '/' },
  { label: '会话中心', icon: Clock3, href: '/sessions' },
  { label: '故事库', icon: BookOpen, href: '/stories' },
  { label: '媒体库', icon: Images, href: '/media' },
  { label: '叙事风格库', icon: WandSparkles, href: '/narrative-styles' },
  { label: '角色库', icon: UsersRound, href: '/characters' },
  { label: '世界设定', icon: Globe2, href: '/worldbook' },
  { label: '状态表', icon: TableProperties, href: '/status-tables' },
  { label: '设置', icon: Settings, href: '/settings', target: '_blank', rel: 'noreferrer' },
]

function Logo({ compact = false }: { compact?: boolean }) {
  return (
    <Link href="/" className="flex items-center gap-3">
      <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-violet-500 to-indigo-500 text-white shadow-lg shadow-violet-200">
        <Sparkles size={22} fill="currentColor" />
      </span>
      <span className={`text-xl font-bold text-slate-950 ${compact ? 'hidden sm:inline' : ''}`}>RPG World Play</span>
    </Link>
  )
}

function WorkspaceSwitcher({
  value,
  workspaces,
  isLoading,
  isError,
  onChange,
}: {
  value: string | null
  workspaces: WorkspaceSummary[]
  isLoading: boolean
  isError: boolean
  onChange: (workspace: string | null) => void
}) {
  const [open, setOpen] = useState(false)
  const selectedWorkspace = value ? workspaces.find((workspace) => workspace.id === value) : null
  const label = selectedWorkspace?.name ?? (isLoading ? '加载中' : isError ? '加载失败' : '暂无 workspace')

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((isOpen) => !isOpen)}
        className="flex h-10 items-center gap-1.5 rounded-full border border-slate-200 bg-white px-2 text-sm font-medium text-slate-900 shadow-sm transition hover:border-violet-200 hover:bg-violet-50/70 hover:text-violet-700 sm:gap-2 sm:px-3"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="切换 workspace"
      >
        <FolderOpen size={16} className="text-slate-400" />
        <span className="hidden text-slate-500 sm:inline">Workspace</span>
        <span className="max-w-16 truncate font-semibold sm:max-w-28">{label}</span>
        <ChevronDown size={16} className={`text-slate-400 transition ${open ? 'rotate-180 text-violet-500' : ''}`} />
      </button>
      {open ? (
        <div className="absolute left-0 top-full z-40 mt-2 w-56 overflow-hidden rounded-xl border border-slate-200 bg-white p-1 shadow-xl shadow-slate-200/70" role="menu">
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

function isActivePath(pathname: string, href: string) {
  if (href === '/') return pathname === '/'
  return pathname.startsWith(href)
}

function NavigationLinks({
  pathname,
  onNavigate,
}: {
  pathname: string
  onNavigate?: () => void
}) {
  return (
    <nav className="space-y-3">
      {navItems.map((item) => {
        const active = isActivePath(pathname, item.href)
        return (
          <Link
            key={item.label}
            className={`flex items-center gap-4 rounded-xl px-5 py-4 text-base font-medium transition ${
              active
                ? 'bg-violet-50 text-violet-700 shadow-sm'
                : 'text-slate-500 hover:bg-slate-100 hover:text-slate-900'
            }`}
            href={item.href}
            target={item.target}
            rel={item.rel}
            onClick={onNavigate}
          >
            <item.icon size={22} />
            {item.label}
          </Link>
        )
      })}
    </nav>
  )
}

export function AppShell({ children }: AppShellProps) {
  const pathname = usePathname()
  const [currentWorkspace, setCurrentWorkspace] = useState<string | null>(null)
  const [mobileNavOpen, setMobileNavOpen] = useState(false)
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

  const shellState = useMemo(
    () => ({ currentWorkspace, workspaces: workspaceOptions }),
    [currentWorkspace, workspaceOptions],
  )

  useEffect(() => {
    setMobileNavOpen(false)
  }, [pathname])

  return (
    <main className="min-h-screen bg-[#f7f8fc] text-slate-900">
      <header className="sticky top-0 z-30 flex h-[72px] items-center justify-between gap-3 border-b border-slate-200/80 bg-white/90 px-4 backdrop-blur md:px-6">
        <div className="flex min-w-0 items-center gap-3 md:gap-4">
          <button
            type="button"
            onClick={() => setMobileNavOpen(true)}
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-slate-200 bg-white text-slate-600 shadow-sm transition hover:border-violet-200 hover:bg-violet-50 hover:text-violet-700 lg:hidden"
            aria-label="打开导航"
            aria-haspopup="dialog"
            aria-expanded={mobileNavOpen}
          >
            <Menu size={20} />
          </button>
          <Logo compact />
          <WorkspaceSwitcher
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
        <div className="flex shrink-0 items-center gap-2">
          <NotificationCenter />
          <button className="flex shrink-0 items-center gap-1 rounded-full px-1 py-1 text-sm font-medium text-slate-900 transition hover:bg-slate-100 sm:gap-3 sm:px-2">
            <span className="flex h-10 w-10 items-center justify-center rounded-full bg-indigo-100 text-indigo-700">P</span>
            <span className="hidden sm:inline">Player One</span>
            <ChevronDown size={16} className="hidden text-slate-400 sm:block" />
          </button>
        </div>
      </header>

      {mobileNavOpen ? (
        <div className="fixed inset-0 z-50 lg:hidden" role="dialog" aria-modal="true" aria-label="移动端导航">
          <button
            type="button"
            className="absolute inset-0 bg-slate-950/30"
            aria-label="关闭导航"
            onClick={() => setMobileNavOpen(false)}
          />
          <aside className="relative flex h-full w-[min(320px,86vw)] flex-col border-r border-slate-200 bg-white px-5 py-5 shadow-2xl shadow-slate-950/20">
            <div className="min-h-0 flex-1 overflow-y-auto pr-1">
              <div className="mb-6 flex items-center justify-between gap-3">
                <Logo />
                <button
                  type="button"
                  onClick={() => setMobileNavOpen(false)}
                  className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl text-slate-500 transition hover:bg-slate-100 hover:text-slate-900"
                  aria-label="关闭导航"
                >
                  <X size={20} />
                </button>
              </div>
              <NavigationLinks pathname={pathname} onNavigate={() => setMobileNavOpen(false)} />
            </div>

            <div className="shrink-0 space-y-4 pt-6">
              <section className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                <p className="mb-3 text-sm text-slate-400">系统状态</p>
                <div className="space-y-3 text-sm text-slate-600">
                  <p className="flex items-center gap-3">
                    <span className="h-2 w-2 rounded-full bg-emerald-500" />
                    Play API ready
                  </p>
                  <p className="flex items-center gap-3">
                    <span className="h-2 w-2 rounded-full bg-emerald-500" />
                    SSE ready
                  </p>
                </div>
              </section>
              <div className="flex justify-end">
                <ThemeSwitcher menuAlign="right" />
              </div>
            </div>
          </aside>
        </div>
      ) : null}

      <div className="grid min-h-[calc(100vh-72px)] lg:grid-cols-[296px_minmax(0,1fr)]">
        <aside className="hidden border-r border-slate-200 bg-white/70 px-6 py-9 lg:flex lg:flex-col lg:justify-between">
          <NavigationLinks pathname={pathname} />

          <div className="space-y-4">
            <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
              <p className="mb-4 text-sm text-slate-400">系统状态</p>
              <div className="space-y-4 text-sm text-slate-600">
                <p className="flex items-center gap-3">
                  <span className="h-2 w-2 rounded-full bg-emerald-500" />
                  Play API ready
                </p>
                <p className="flex items-center gap-3">
                  <span className="h-2 w-2 rounded-full bg-emerald-500" />
                  SSE ready
                </p>
              </div>
            </section>
            <div className="flex justify-end">
              <ThemeSwitcher menuAlign="right" />
            </div>
          </div>
        </aside>

        <AppShellContext.Provider value={shellState}>
          {typeof children === 'function' ? children(shellState) : children}
        </AppShellContext.Provider>
      </div>
    </main>
  )
}

export function useAppShell() {
  const value = useContext(AppShellContext)
  if (value === null) {
    throw new Error('useAppShell must be used inside AppShell')
  }
  return value
}
