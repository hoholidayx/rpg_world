import Link from 'next/link'
import { ChevronLeft, ChevronRight, Sparkles, X } from 'lucide-react'
import { cn } from '@/lib/utils/cn'
import type { CharacterCard } from '@/types/characters'
import type { Scene } from '@/types/scene'
import type { StatusTable } from '@/types/statusTables'
import { SessionAvatar } from './SessionAvatar'
import { characterSummary, firstLetter, getCharacterAvatarUrl, sceneRows } from './sessionRoomHelpers'
import type { SessionSpeaker } from './sessionRoomTypes'

function Brand({ collapsed }: { collapsed: boolean }) {
  return (
    <Link href="/" className="flex min-w-0 items-center gap-3">
      <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-violet-500 to-indigo-500 text-white shadow-lg shadow-violet-200 dark:shadow-violet-950/40">
        <Sparkles size={21} fill="currentColor" />
      </span>
      <span className={cn('min-w-0 leading-tight transition lg:block', collapsed ? 'lg:hidden' : '')}>
        <strong className="block truncate text-sm font-black text-slate-950 dark:text-slate-100">RPG World Play</strong>
        <span className="block truncate text-xs font-semibold text-slate-400 dark:text-slate-300">immersive session</span>
      </span>
    </Link>
  )
}

function EmptyState({ children }: { children: string }) {
  return (
    <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 px-4 py-6 text-center text-sm font-semibold text-slate-400 dark:border-slate-700 dark:bg-slate-800/70 dark:text-slate-300">
      {children}
    </div>
  )
}

function Panel({
  title,
  meta,
  children,
  collapsed,
}: {
  title: string
  meta?: string
  children: React.ReactNode
  collapsed: boolean
}) {
  return (
    <section className={cn('overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm dark:border-slate-700 dark:bg-slate-900 dark:shadow-black/25', collapsed ? 'lg:border-0 lg:bg-transparent lg:dark:bg-transparent lg:shadow-none' : '')}>
      <header className={cn('flex items-center justify-between gap-3 border-b border-slate-200 px-4 py-3 dark:border-slate-800', collapsed ? 'lg:hidden' : '')}>
        <h2 className="text-sm font-black text-slate-950 dark:text-slate-100">{title}</h2>
        {meta ? <span className="rounded-full bg-teal-50 px-2.5 py-1 text-xs font-black text-teal-700 dark:bg-teal-500/15 dark:text-teal-200">{meta}</span> : null}
      </header>
      <div className={cn(collapsed ? 'lg:p-0' : '')}>{children}</div>
    </section>
  )
}

function ScenePanel({
  scene,
  loading,
  collapsed,
}: {
  scene?: Scene | null
  loading: boolean
  collapsed: boolean
}) {
  const rows = sceneRows(scene)

  return (
    <Panel title="当前场景" meta="scene" collapsed={collapsed}>
      {collapsed ? (
        <div className="hidden justify-center py-2 lg:flex">
          <span className="flex h-11 w-11 items-center justify-center rounded-full bg-teal-50 text-xs font-black text-teal-700 ring-4 ring-teal-100 dark:bg-teal-500/15 dark:text-teal-200 dark:ring-teal-500/20">景</span>
        </div>
      ) : (
        <div className="px-4 py-4">
          {loading ? <EmptyState>正在加载场景</EmptyState> : null}
          {!loading && rows.length === 0 ? <EmptyState>暂无场景数据</EmptyState> : null}
          {rows.length ? (
            <dl className="space-y-3 text-sm">
              {rows.map(([label, value]) => (
                <div key={`${label}-${value}`} className="grid grid-cols-[48px_minmax(0,1fr)] gap-3">
                  <dt className="text-slate-400 dark:text-slate-300">{label}</dt>
                  <dd className="min-w-0 break-words font-semibold text-slate-800 dark:text-slate-200">{value}</dd>
                </div>
              ))}
            </dl>
          ) : null}
        </div>
      )}
    </Panel>
  )
}

function CharacterPanel({
  characters,
  loading,
  collapsed,
}: {
  characters: CharacterCard[]
  loading: boolean
  collapsed: boolean
}) {
  if (collapsed) {
    return (
      <Panel title="在场角色" meta="story mounts" collapsed={collapsed}>
        <div className="hidden space-y-3 py-2 lg:block">
          {characters.slice(0, 5).map((character) => {
            const speaker: SessionSpeaker = {
              name: character.name,
              avatarUrl: getCharacterAvatarUrl(character),
              fallback: firstLetter(character.name),
              tone: 'assistant',
            }
            return <SessionAvatar key={character.id} speaker={speaker} className="mx-auto" />
          })}
          {!characters.length ? <span className="mx-auto flex h-11 w-11 items-center justify-center rounded-full bg-slate-100 text-xs font-black text-slate-400 dark:bg-slate-800 dark:text-slate-300">空</span> : null}
        </div>
      </Panel>
    )
  }

  return (
    <Panel title="在场角色" meta="story mounts" collapsed={collapsed}>
      <div className="space-y-3 px-4 py-4">
        {loading ? <EmptyState>正在加载角色</EmptyState> : null}
        {!loading && characters.length === 0 ? <EmptyState>暂无已挂载角色</EmptyState> : null}
        {characters.map((character, index) => {
          const speaker: SessionSpeaker = {
            name: character.name,
            avatarUrl: getCharacterAvatarUrl(character),
            fallback: firstLetter(character.name),
            tone: index === 0 ? 'player' : 'assistant',
          }

          return (
            <article key={character.id} className="flex gap-3 rounded-lg border border-slate-200 bg-white px-3 py-3 dark:border-slate-700 dark:bg-slate-950/50">
              <SessionAvatar speaker={speaker} className="h-12 w-12 rounded-lg ring-0" />
              <div className="min-w-0">
                <h3 className="truncate text-sm font-black text-slate-950 dark:text-slate-100">{character.name}</h3>
                <p className="mt-1 line-clamp-2 text-xs font-semibold leading-5 text-slate-500 dark:text-slate-300">{characterSummary(character)}</p>
              </div>
            </article>
          )
        })}
      </div>
    </Panel>
  )
}

function StatusTableCard({ table }: { table: StatusTable }) {
  return (
    <section className="overflow-hidden rounded-lg border border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-950/50">
      <header className="border-b border-slate-100 bg-slate-50 px-3 py-2 dark:border-slate-800 dark:bg-slate-900">
        <h3 className="truncate text-sm font-black text-slate-950 dark:text-slate-100">{table.name}</h3>
        {table.description ? <p className="mt-1 line-clamp-2 text-xs font-semibold text-slate-400 dark:text-slate-300">{table.description}</p> : null}
      </header>
      <div className="divide-y divide-slate-100 dark:divide-slate-800">
        {table.rows.length ? table.rows.map((row) => (
          <dl key={`${table.id}-${row.key}`} className="grid grid-cols-[82px_minmax(0,1fr)] gap-3 px-3 py-2 text-sm leading-5">
            <dt className="truncate text-slate-400 dark:text-slate-300">{row.key}</dt>
            <dd className="min-w-0 break-words font-semibold text-slate-700 dark:text-slate-200">{row.value}</dd>
          </dl>
        )) : (
          <p className="px-3 py-4 text-sm font-semibold text-slate-400 dark:text-slate-300">暂无行</p>
        )}
      </div>
    </section>
  )
}

function StatusTablesPanel({
  tables,
  loading,
  collapsed,
}: {
  tables: StatusTable[]
  loading: boolean
  collapsed: boolean
}) {
  if (collapsed) {
    return (
      <section className="hidden py-2 lg:flex lg:justify-center">
        <span className="flex h-11 w-11 items-center justify-center rounded-full bg-sky-50 text-xs font-black text-sky-700 ring-4 ring-sky-100 dark:bg-sky-500/15 dark:text-sky-200 dark:ring-sky-500/20">表</span>
      </section>
    )
  }

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-700 dark:bg-slate-900 dark:shadow-black/25">
      <h2 className="text-sm font-black text-slate-950 dark:text-slate-100">状态表</h2>
      <div className="mt-4 space-y-3">
        {loading ? <EmptyState>正在加载状态表</EmptyState> : null}
        {!loading && tables.length === 0 ? <EmptyState>暂无状态表</EmptyState> : null}
        {tables.map((table) => <StatusTableCard key={table.id} table={table} />)}
      </div>
    </section>
  )
}

export function SessionLeftRail({
  scene,
  sceneLoading,
  characters,
  charactersLoading,
  collapsed,
  mobileOpen,
  onCloseMobile,
  onToggleCollapsed,
}: {
  scene?: Scene | null
  sceneLoading: boolean
  characters: CharacterCard[]
  charactersLoading: boolean
  collapsed: boolean
  mobileOpen: boolean
  onCloseMobile: () => void
  onToggleCollapsed: () => void
}) {
  return (
    <aside
      className={cn(
        'fixed inset-y-0 left-0 z-40 flex w-[min(340px,88vw)] flex-col border-r border-slate-200 bg-white/95 shadow-2xl shadow-slate-950/10 backdrop-blur transition-transform dark:border-slate-800 dark:bg-slate-950/95 dark:shadow-black/40 lg:static lg:z-auto lg:h-screen lg:w-auto lg:translate-x-0 lg:shadow-none',
        mobileOpen ? 'translate-x-0' : '-translate-x-full',
        collapsed ? 'lg:px-3' : '',
      )}
    >
      <header className={cn('flex h-[73px] shrink-0 items-center justify-between gap-3 border-b border-slate-200 px-5 dark:border-slate-800', collapsed ? 'lg:px-0 lg:justify-center' : '')}>
        <Brand collapsed={collapsed} />
        <div className={cn('flex items-center gap-2', collapsed ? 'lg:hidden' : '')}>
          <button
            type="button"
            onClick={onToggleCollapsed}
            className="hidden h-9 w-9 items-center justify-center rounded-lg border border-slate-200 text-slate-500 transition hover:border-violet-200 hover:bg-violet-50 hover:text-violet-700 dark:border-slate-700 dark:text-slate-300 dark:hover:border-violet-500/60 dark:hover:bg-violet-500/10 dark:hover:text-violet-200 lg:flex"
            aria-label="收起左侧栏"
            title="收起左侧栏"
          >
            <ChevronLeft size={17} />
          </button>
          <button
            type="button"
            onClick={onCloseMobile}
            className="flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200 text-slate-500 transition hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800 lg:hidden"
            aria-label="关闭场景栏"
          >
            <X size={17} />
          </button>
        </div>
      </header>
      {collapsed ? (
        <button
          type="button"
          onClick={onToggleCollapsed}
          className="mx-auto mt-4 hidden h-9 w-9 items-center justify-center rounded-lg border border-slate-200 text-slate-500 transition hover:border-violet-200 hover:bg-violet-50 hover:text-violet-700 dark:border-slate-700 dark:text-slate-300 dark:hover:border-violet-500/60 dark:hover:bg-violet-500/10 dark:hover:text-violet-200 lg:flex"
          aria-label="展开左侧栏"
          title="展开左侧栏"
        >
          <ChevronRight size={17} />
        </button>
      ) : null}
      <div className={cn('min-h-0 flex-1 space-y-4 overflow-y-auto px-5 py-5', collapsed ? 'lg:px-0' : '')}>
        <ScenePanel scene={scene} loading={sceneLoading} collapsed={collapsed} />
        <CharacterPanel characters={characters} loading={charactersLoading} collapsed={collapsed} />
      </div>
    </aside>
  )
}

export function SessionRightRail({
  tables,
  loading,
  collapsed,
  mobileOpen,
  onCloseMobile,
  onToggleCollapsed,
}: {
  tables: StatusTable[]
  loading: boolean
  collapsed: boolean
  mobileOpen: boolean
  onCloseMobile: () => void
  onToggleCollapsed: () => void
}) {
  return (
    <aside
      className={cn(
        'fixed inset-y-0 right-0 z-40 flex w-[min(360px,88vw)] flex-col border-l border-slate-200 bg-white/95 shadow-2xl shadow-slate-950/10 backdrop-blur transition-transform dark:border-slate-800 dark:bg-slate-950/95 dark:shadow-black/40 lg:static lg:z-auto lg:h-screen lg:w-auto lg:translate-x-0 lg:shadow-none',
        mobileOpen ? 'translate-x-0' : 'translate-x-full',
        collapsed ? 'lg:px-3' : '',
      )}
    >
      <header className={cn('flex h-[73px] shrink-0 items-center justify-between gap-3 border-b border-slate-200 px-5 dark:border-slate-800', collapsed ? 'lg:px-0 lg:justify-center' : '')}>
        <div className={cn('min-w-0', collapsed ? 'lg:hidden' : '')}>
          <strong className="block truncate text-sm font-black text-slate-950 dark:text-slate-100">状态表</strong>
          <span className="mt-1 block truncate text-xs font-semibold text-slate-400 dark:text-slate-300">runtime tables</span>
        </div>
        <div className={cn('flex items-center gap-2', collapsed ? 'lg:hidden' : '')}>
          <button
            type="button"
            onClick={onToggleCollapsed}
            className="hidden h-9 w-9 items-center justify-center rounded-lg border border-slate-200 text-slate-500 transition hover:border-violet-200 hover:bg-violet-50 hover:text-violet-700 dark:border-slate-700 dark:text-slate-300 dark:hover:border-violet-500/60 dark:hover:bg-violet-500/10 dark:hover:text-violet-200 lg:flex"
            aria-label="收起右侧栏"
            title="收起右侧栏"
          >
            <ChevronRight size={17} />
          </button>
          <button
            type="button"
            onClick={onCloseMobile}
            className="flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200 text-slate-500 transition hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800 lg:hidden"
            aria-label="关闭状态栏"
          >
            <X size={17} />
          </button>
        </div>
      </header>
      {collapsed ? (
        <button
          type="button"
          onClick={onToggleCollapsed}
          className="mx-auto mt-4 hidden h-9 w-9 items-center justify-center rounded-lg border border-slate-200 text-slate-500 transition hover:border-violet-200 hover:bg-violet-50 hover:text-violet-700 dark:border-slate-700 dark:text-slate-300 dark:hover:border-violet-500/60 dark:hover:bg-violet-500/10 dark:hover:text-violet-200 lg:flex"
          aria-label="展开右侧栏"
          title="展开右侧栏"
        >
          <ChevronLeft size={17} />
        </button>
      ) : null}
      <div className={cn('min-h-0 flex-1 overflow-y-auto px-5 py-5', collapsed ? 'lg:px-0' : '')}>
        <StatusTablesPanel tables={tables} loading={loading} collapsed={collapsed} />
      </div>
    </aside>
  )
}
