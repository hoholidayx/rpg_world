import { useId, useMemo, useState } from 'react'
import Link from 'next/link'
import {
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Layers3,
  MapPinned,
  Pin,
  PinOff,
  Settings2,
  X,
} from 'lucide-react'
import { cn } from '@/lib/utils/cn'
import type { CharacterCard } from '@/types/characters'
import type { Scene } from '@/types/scene'
import type { SessionPlayerCharacter } from '@/types/session'
import type { StatusTable } from '@/types/statusTables'
import { SessionAvatar } from './SessionAvatar'
import { SessionRailDrawer } from './SessionRailDrawer'
import { usePinnedStatusTables } from './hooks/usePinnedStatusTables'
import {
  characterSummary,
  firstLetter,
  getCharacterAvatarUrl,
  getUiString,
} from './sessionRoomHelpers'
import type { SessionRailDrawerState, SessionSpeaker } from './sessionRoomTypes'
import {
  resolveStatusBinding,
  tableIsBoundToCharacter,
  type ResolvedStatusBinding,
} from './sessionStatusBindings'

function sortedTables(tables: StatusTable[]) {
  return [...tables].sort((first, second) => (
    first.sortOrder - second.sortOrder || first.id - second.id
  ))
}

function EmptyState({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 px-4 py-6 text-center text-sm font-semibold text-slate-400 dark:border-slate-700 dark:bg-slate-800/70 dark:text-slate-300">
      {children}
    </div>
  )
}

function characterSpeaker(character: CharacterCard, player: boolean): SessionSpeaker {
  return {
    name: character.name,
    avatarUrl: getCharacterAvatarUrl(character),
    fallback: firstLetter(character.name),
    tone: player ? 'player' : 'assistant',
  }
}

function isCurrentPlayer(
  character: CharacterCard,
  playerCharacter?: SessionPlayerCharacter | null,
) {
  if (!playerCharacter) return false
  if (character.mountId && playerCharacter.mountId) {
    return character.mountId === playerCharacter.mountId
  }
  return character.id === playerCharacter.characterId
}

function BindingBadge({ binding }: { binding: ResolvedStatusBinding }) {
  if (binding.kind === 'global') {
    return (
      <span className="inline-flex min-w-0 items-center rounded-full bg-slate-100 px-2 py-1 text-[10px] font-black text-slate-500 dark:bg-slate-800 dark:text-slate-300">
        全局状态
      </span>
    )
  }
  if (binding.kind === 'unavailable') {
    return (
      <span className="inline-flex min-w-0 items-center rounded-full bg-amber-50 px-2 py-1 text-[10px] font-black text-amber-700 dark:bg-amber-500/15 dark:text-amber-200">
        角色绑定不可用
      </span>
    )
  }
  return (
    <span className="inline-flex min-w-0 items-center gap-1.5 rounded-full bg-sky-50 py-1 pl-1 pr-2 text-[10px] font-black text-sky-700 dark:bg-sky-500/15 dark:text-sky-200">
      <SessionAvatar
        speaker={characterSpeaker(binding.character, false)}
        className="h-5 w-5 text-[8px] ring-0"
      />
      <span className="truncate">角色 · {binding.name}</span>
    </span>
  )
}

function StatusTableCard({
  table,
  binding,
  scene,
  activeScene,
  defaultOpen,
}: {
  table: StatusTable
  binding: ResolvedStatusBinding
  scene?: boolean
  activeScene?: boolean
  defaultOpen: boolean
}) {
  const [open, setOpen] = useState(defaultOpen)
  const contentId = useId()
  return (
    <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-700 dark:bg-slate-900 dark:shadow-black/25">
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        className="flex w-full items-center gap-3 px-3 py-3 text-left transition hover:bg-slate-50 dark:hover:bg-slate-800/70"
        aria-expanded={open}
        aria-controls={contentId}
      >
        <span className={cn(
          'flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-xs font-black',
          scene
            ? 'bg-teal-50 text-teal-700 dark:bg-teal-500/15 dark:text-teal-200'
            : 'bg-violet-50 text-violet-700 dark:bg-violet-500/15 dark:text-violet-200',
        )}>
          {firstLetter(table.name)}
        </span>
        <span className="min-w-0 flex-1">
          <strong className="block truncate text-sm font-black text-slate-950 dark:text-slate-100">
            {table.name}
          </strong>
          <span className="mt-1 flex min-w-0 flex-wrap items-center gap-1.5">
            {scene ? (
              <>
                <span className="rounded-full bg-teal-50 px-2 py-1 text-[10px] font-black text-teal-700 dark:bg-teal-500/15 dark:text-teal-200">
                  {activeScene ? '主场景' : '场景表'}
                </span>
                <span className="rounded-full bg-slate-100 px-2 py-1 text-[10px] font-black text-slate-500 dark:bg-slate-800 dark:text-slate-300">
                  不参与 pin
                </span>
              </>
            ) : <BindingBadge binding={binding} />}
          </span>
        </span>
        <ChevronDown
          size={16}
          className={cn('shrink-0 text-slate-400 transition', open ? 'rotate-180' : '')}
          aria-hidden="true"
        />
      </button>
      <div id={contentId} hidden={!open} className="border-t border-slate-100 dark:border-slate-800">
        {table.description ? (
          <p className="border-b border-slate-100 bg-slate-50/70 px-3 py-2 text-xs font-semibold leading-5 text-slate-500 dark:border-slate-800 dark:bg-slate-950/40 dark:text-slate-300">
            {table.description}
          </p>
        ) : null}
        {table.rows.length ? (
          <dl className="divide-y divide-slate-100 dark:divide-slate-800">
            {table.rows.map((row) => (
              <div key={`${table.id}-${row.key}`} className="grid grid-cols-[82px_minmax(0,1fr)] gap-3 px-3 py-2 text-xs leading-5">
                <dt className="truncate text-slate-400 dark:text-slate-400">{row.key}</dt>
                <dd className="min-w-0 break-words font-semibold text-slate-700 dark:text-slate-200">{row.value}</dd>
              </div>
            ))}
          </dl>
        ) : (
          <p className="px-3 py-4 text-xs font-semibold text-slate-400 dark:text-slate-300">暂无行</p>
        )}
      </div>
    </section>
  )
}

function CharacterLauncher({
  characters,
  loading,
  expanded,
  onOpen,
}: {
  characters: CharacterCard[]
  loading: boolean
  expanded: boolean
  onOpen: () => void
}) {
  return (
    <button
      type="button"
      onClick={onOpen}
      className="flex w-full items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white px-3 py-3 text-left shadow-sm transition hover:border-violet-200 hover:bg-violet-50/40 dark:border-slate-700 dark:bg-slate-900 dark:hover:border-violet-500/60 dark:hover:bg-violet-500/10"
      aria-haspopup="dialog"
      aria-expanded={expanded}
    >
      <span className="min-w-0">
        <strong className="block text-sm font-black text-slate-950 dark:text-slate-100">故事角色</strong>
        <span className="mt-1 block truncate text-xs font-semibold text-slate-400 dark:text-slate-300">
          {loading ? '正在加载角色' : `${characters.length} 位已挂载角色 · 点击展开卡片`}
        </span>
      </span>
      <span className="flex shrink-0 items-center pl-2" aria-hidden="true">
        {characters.slice(0, 3).map((character, index) => (
          <SessionAvatar
            key={character.id}
            speaker={characterSpeaker(character, false)}
            className={cn('h-8 w-8 border-2 border-white text-[10px] ring-0 dark:border-slate-900', index ? '-ml-2' : '')}
          />
        ))}
        {!loading && !characters.length ? (
          <span className="flex h-8 w-8 items-center justify-center rounded-full bg-slate-100 text-[10px] font-black text-slate-400 dark:bg-slate-800 dark:text-slate-300">空</span>
        ) : null}
        <ChevronRight size={16} className="ml-2 text-slate-400" />
      </span>
    </button>
  )
}

function CharacterCards({
  characters,
  loading,
  normalTables,
  pinnedIdSet,
  playerCharacter,
  scene,
}: {
  characters: CharacterCard[]
  loading: boolean
  normalTables: StatusTable[]
  pinnedIdSet: Set<number>
  playerCharacter?: SessionPlayerCharacter | null
  scene?: Scene | null
}) {
  const presentNames = new Set(
    (scene?.presentCharacters ?? []).map((name) => name.trim().toLocaleLowerCase()),
  )
  if (loading) return <EmptyState>正在加载角色</EmptyState>
  if (!characters.length) return <EmptyState>当前故事暂无已挂载角色</EmptyState>

  return (
    <div className="space-y-3">
      <p className="rounded-lg border border-violet-100 bg-violet-50/70 px-3 py-2 text-xs font-semibold leading-5 text-violet-700 dark:border-violet-500/30 dark:bg-violet-500/10 dark:text-violet-200">
        角色卡只展示状态表绑定关系；完整 KV 仍在左侧状态表中查看。
      </p>
      {characters.map((character) => {
        const player = isCurrentPlayer(character, playerCharacter)
        const present = presentNames.has(character.name.trim().toLocaleLowerCase())
        const boundTables = normalTables.filter((table) => (
          tableIsBoundToCharacter(table, character, characters)
        ))
        const roleLabel = player
          ? playerCharacter?.roleLabel || '当前扮演角色'
          : getUiString(character.metadata, 'roleLabel') || '故事角色'
        return (
          <article key={character.id} className="grid grid-cols-[104px_minmax(0,1fr)] gap-4 rounded-xl border border-slate-200 bg-white p-3 shadow-sm dark:border-slate-700 dark:bg-slate-900 max-[520px]:grid-cols-[82px_minmax(0,1fr)]">
            <div className="flex min-h-32 items-center justify-center overflow-hidden rounded-xl bg-gradient-to-br from-violet-600 via-indigo-500 to-cyan-600 p-3">
              <SessionAvatar
                speaker={characterSpeaker(character, player)}
                className="h-20 w-20 rounded-2xl bg-white/20 text-xl text-white ring-0"
              />
            </div>
            <div className="min-w-0 py-1">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <h3 className="truncate text-base font-black text-slate-950 dark:text-slate-100">{character.name}</h3>
                  <span className="mt-1 block text-[10px] font-black text-violet-700 dark:text-violet-300">
                    {player ? '玩家角色' : '故事角色'} · {roleLabel}
                  </span>
                </div>
                <span className={cn(
                  'shrink-0 rounded-full px-2 py-1 text-[10px] font-black',
                  present
                    ? 'bg-teal-50 text-teal-700 dark:bg-teal-500/15 dark:text-teal-200'
                    : 'bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-300',
                )}>
                  {present ? '在场' : '未在场'}
                </span>
              </div>
              <p className="mt-3 text-xs font-semibold leading-5 text-slate-500 dark:text-slate-300">
                {characterSummary(character)}
              </p>
              <div className="mt-3">
                <strong className="block text-[10px] font-black text-slate-400 dark:text-slate-400">绑定状态表</strong>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {boundTables.length ? boundTables.map((table) => (
                    <span
                      key={table.id}
                      className={cn(
                        'rounded-full border px-2 py-1 text-[10px] font-black',
                        pinnedIdSet.has(table.id)
                          ? 'border-violet-200 bg-violet-50 text-violet-700 dark:border-violet-500/40 dark:bg-violet-500/15 dark:text-violet-200'
                          : 'border-slate-200 bg-slate-50 text-slate-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300',
                      )}
                      title={pinnedIdSet.has(table.id) ? '已固定到左侧栏' : '未固定到左侧栏'}
                    >
                      {pinnedIdSet.has(table.id) ? '◆' : '◇'} {table.name}
                    </span>
                  )) : (
                    <span className="text-xs font-semibold text-slate-400 dark:text-slate-400">暂无绑定表</span>
                  )}
                </div>
              </div>
            </div>
          </article>
        )
      })}
    </div>
  )
}

function StatusManager({
  tables,
  loading,
  characters,
  pinnedIdSet,
  onToggle,
}: {
  tables: StatusTable[]
  loading: boolean
  characters: CharacterCard[]
  pinnedIdSet: Set<number>
  onToggle: (tableId: number) => void
}) {
  if (loading) return <EmptyState>正在加载状态表</EmptyState>
  if (!tables.length) return <EmptyState>当前会话暂无普通状态表</EmptyState>
  return (
    <div className="space-y-3">
      <p className="rounded-lg border border-violet-100 bg-violet-50/70 px-3 py-2 text-xs font-semibold leading-5 text-violet-700 dark:border-violet-500/30 dark:bg-violet-500/10 dark:text-violet-200">
        固定偏好保存在当前浏览器，并按 session 隔离；场景表始终展示，不参与 pin。
      </p>
      {tables.map((table) => {
        const pinned = pinnedIdSet.has(table.id)
        const binding = resolveStatusBinding(table, characters)
        return (
          <article key={table.id} className="flex items-center gap-3 rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-900">
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-violet-50 text-xs font-black text-violet-700 dark:bg-violet-500/15 dark:text-violet-200">
              {firstLetter(table.name)}
            </span>
            <span className="min-w-0 flex-1">
              <strong className="block truncate text-sm font-black text-slate-950 dark:text-slate-100">{table.name}</strong>
              <span className="mt-1 flex min-w-0"><BindingBadge binding={binding} /></span>
            </span>
            <button
              type="button"
              onClick={() => onToggle(table.id)}
              aria-pressed={pinned}
              aria-label={`${pinned ? '取消固定' : '固定'}${table.name}`}
              className={cn(
                'flex h-9 shrink-0 items-center gap-1.5 rounded-lg border px-3 text-xs font-black transition',
                pinned
                  ? 'border-violet-200 bg-violet-50 text-violet-700 hover:bg-violet-100 dark:border-violet-500/40 dark:bg-violet-500/15 dark:text-violet-200'
                  : 'border-slate-200 bg-white text-slate-500 hover:border-violet-200 hover:text-violet-700 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-300',
              )}
            >
              {pinned ? <PinOff size={14} /> : <Pin size={14} />}
              {pinned ? '已固定' : '固定'}
            </button>
          </article>
        )
      })}
    </div>
  )
}

export function SessionLeftRail({
  sessionId,
  sceneTables,
  sceneTablesLoading,
  normalTables,
  normalTablesLoading,
  normalTablesReady,
  characters,
  charactersLoading,
  scene,
  playerCharacter,
  collapsed,
  mobileOpen,
  activeDrawer,
  onCloseMobile,
  onToggleCollapsed,
  onOpenDrawer,
  onCloseDrawer,
}: {
  sessionId: string
  sceneTables: StatusTable[]
  sceneTablesLoading: boolean
  normalTables: StatusTable[]
  normalTablesLoading: boolean
  normalTablesReady: boolean
  characters: CharacterCard[]
  charactersLoading: boolean
  scene?: Scene | null
  playerCharacter?: SessionPlayerCharacter | null
  collapsed: boolean
  mobileOpen: boolean
  activeDrawer: SessionRailDrawerState
  onCloseMobile: () => void
  onToggleCollapsed: () => void
  onOpenDrawer: (drawer: Exclude<SessionRailDrawerState, null>) => void
  onCloseDrawer: () => void
}) {
  const orderedScenes = useMemo(() => sortedTables(sceneTables), [sceneTables])
  const orderedNormalTables = useMemo(() => sortedTables(normalTables), [normalTables])
  const pins = usePinnedStatusTables({
    sessionId,
    tables: orderedNormalTables,
    ready: normalTablesReady,
  })
  const pinnedTables = orderedNormalTables.filter((table) => pins.pinnedIdSet.has(table.id))
  const charactersOpen = activeDrawer?.kind === 'characters'
  const managerOpen = activeDrawer?.kind === 'status-manager'

  return (
    <>
      <aside
        aria-label="状态与角色侧栏"
        className={cn(
          'fixed inset-y-0 left-0 z-40 flex w-[min(340px,88vw)] flex-col border-r border-slate-200 bg-white/95 shadow-2xl shadow-slate-950/10 backdrop-blur transition-transform dark:border-slate-800 dark:bg-slate-950/95 dark:shadow-black/40 lg:static lg:z-auto lg:h-screen lg:w-auto lg:translate-x-0 lg:shadow-none',
          mobileOpen ? 'translate-x-0' : '-translate-x-full',
          collapsed ? 'lg:px-3' : '',
        )}
      >
        <header className={cn('flex h-[73px] shrink-0 items-center justify-between gap-3 border-b border-slate-200 px-5 dark:border-slate-800', collapsed ? 'lg:justify-center lg:px-0' : '')}>
          <Link href="/" className="flex min-w-0 items-center gap-3" aria-label="返回 RPG World Play 首页">
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-violet-500 to-indigo-600 text-sm font-black text-white shadow-lg shadow-violet-200 dark:shadow-violet-950/40">
              R
            </span>
            <span className={cn('min-w-0 leading-tight', collapsed ? 'lg:hidden' : '')}>
              <strong className="block truncate text-sm font-black text-slate-950 dark:text-slate-100">状态与角色</strong>
              <span className="block truncate text-xs font-semibold text-slate-400 dark:text-slate-300">session context</span>
            </span>
          </Link>
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
              aria-label="关闭场景与固定状态栏"
            >
              <X size={17} />
            </button>
          </div>
        </header>

        {collapsed ? (
          <div className="hidden min-h-0 flex-1 flex-col items-center gap-3 overflow-y-auto py-4 lg:flex">
            <button
              type="button"
              onClick={onToggleCollapsed}
              className="flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200 text-slate-500 transition hover:border-violet-200 hover:bg-violet-50 hover:text-violet-700 dark:border-slate-700 dark:text-slate-300"
              aria-label="展开左侧栏"
              title="展开左侧栏"
            >
              <ChevronRight size={17} />
            </button>
            <button
              type="button"
              onClick={() => onOpenDrawer({ kind: 'characters' })}
              className="flex h-11 w-11 items-center justify-center rounded-full bg-violet-50 text-xs font-black text-violet-700 ring-4 ring-violet-100 dark:bg-violet-500/15 dark:text-violet-200 dark:ring-violet-500/20"
              aria-label="展开故事角色"
              aria-haspopup="dialog"
              title="故事角色"
            >
              角
            </button>
            <span className="flex h-11 w-11 items-center justify-center rounded-full bg-teal-50 text-xs font-black text-teal-700 ring-4 ring-teal-100 dark:bg-teal-500/15 dark:text-teal-200 dark:ring-teal-500/20" title={`${orderedScenes.length} 张场景表`}>
              景{orderedScenes.length || ''}
            </span>
            <button
              type="button"
              onClick={() => onOpenDrawer({ kind: 'status-manager' })}
              className="flex h-11 w-11 items-center justify-center rounded-full bg-sky-50 text-xs font-black text-sky-700 ring-4 ring-sky-100 dark:bg-sky-500/15 dark:text-sky-200 dark:ring-sky-500/20"
              aria-label="管理固定状态表"
              aria-haspopup="dialog"
              title={`${pinnedTables.length} 张已固定状态表`}
            >
              表{pinnedTables.length || ''}
            </button>
          </div>
        ) : null}

        <div className={cn('min-h-0 flex-1 space-y-5 overflow-y-auto px-5 py-5', collapsed ? 'lg:hidden' : '')}>
          <CharacterLauncher
            characters={characters}
            loading={charactersLoading}
            expanded={charactersOpen}
            onOpen={() => onOpenDrawer({ kind: 'characters' })}
          />

          <section aria-labelledby="session-scene-tables-title">
            <div className="mb-2 flex min-h-8 items-center justify-between gap-3 px-0.5">
              <span className="flex min-w-0 items-center gap-2">
                <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-teal-50 text-teal-700 dark:bg-teal-500/15 dark:text-teal-200"><MapPinned size={14} /></span>
                <strong id="session-scene-tables-title" className="text-sm font-black text-slate-950 dark:text-slate-100">场景状态</strong>
              </span>
              <span className="text-[10px] font-black text-slate-400 dark:text-slate-400">{orderedScenes.length} 张 · 始终显示</span>
            </div>
            <div className="space-y-3">
              {sceneTablesLoading ? <EmptyState>正在加载场景表</EmptyState> : null}
              {!sceneTablesLoading && !orderedScenes.length ? <EmptyState>暂无场景状态表</EmptyState> : null}
              {orderedScenes.map((table, index) => (
                <StatusTableCard
                  key={table.id}
                  table={table}
                  binding={{ kind: 'global' }}
                  scene
                  activeScene={index === 0}
                  defaultOpen={index === 0}
                />
              ))}
            </div>
          </section>

          <section aria-labelledby="session-pinned-tables-title">
            <div className="mb-2 flex min-h-8 items-center justify-between gap-3 px-0.5">
              <span className="flex min-w-0 items-center gap-2">
                <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-violet-50 text-violet-700 dark:bg-violet-500/15 dark:text-violet-200"><Layers3 size={14} /></span>
                <strong id="session-pinned-tables-title" className="text-sm font-black text-slate-950 dark:text-slate-100">已固定状态 · {pinnedTables.length}</strong>
              </span>
              <button
                type="button"
                onClick={() => onOpenDrawer({ kind: 'status-manager' })}
                className="flex items-center gap-1 text-xs font-black text-violet-700 transition hover:text-violet-900 dark:text-violet-300 dark:hover:text-violet-100"
                aria-haspopup="dialog"
                aria-expanded={managerOpen}
              >
                管理 <Settings2 size={13} />
              </button>
            </div>
            <div className="space-y-3">
              {normalTablesLoading || !pins.initialized ? <EmptyState>正在加载状态表</EmptyState> : null}
              {!normalTablesLoading && pins.initialized && !pinnedTables.length ? (
                <EmptyState>
                  尚未固定普通状态表。<br />点击“管理”将常用表加入侧栏。
                </EmptyState>
              ) : null}
              {pins.initialized ? pinnedTables.map((table, index) => (
                <StatusTableCard
                  key={table.id}
                  table={table}
                  binding={resolveStatusBinding(table, characters)}
                  defaultOpen={index === 0}
                />
              )) : null}
            </div>
          </section>
        </div>
      </aside>

      <SessionRailDrawer
        open={charactersOpen}
        side="left"
        eyebrow="Story characters"
        title="故事角色"
        description="集中浏览角色卡；图片区域为后续图文混排预留。"
        onClose={onCloseDrawer}
      >
        <CharacterCards
          characters={characters}
          loading={charactersLoading}
          normalTables={orderedNormalTables}
          pinnedIdSet={pins.pinnedIdSet}
          playerCharacter={playerCharacter}
          scene={scene}
        />
      </SessionRailDrawer>

      <SessionRailDrawer
        open={managerOpen}
        side="left"
        eyebrow="Pinned tables"
        title="管理状态表"
        description="只有固定的普通状态表进入左侧栏；场景表始终单独展示。"
        onClose={onCloseDrawer}
      >
        <StatusManager
          tables={orderedNormalTables}
          loading={normalTablesLoading}
          characters={characters}
          pinnedIdSet={pins.pinnedIdSet}
          onToggle={pins.togglePinned}
        />
      </SessionRailDrawer>
    </>
  )
}
