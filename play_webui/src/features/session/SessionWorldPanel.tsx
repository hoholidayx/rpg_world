'use client'

import { useEffect, useMemo } from 'react'
import {
  MapPinned,
  Pin,
  PinOff,
  TableProperties,
  UserRound,
  UsersRound,
} from 'lucide-react'
import { cn } from '@/lib/utils/cn'
import type { CharacterCard } from '@/types/characters'
import type { Scene } from '@/types/scene'
import type { SessionPlayerCharacter } from '@/types/session'
import type { StatusTable } from '@/types/statusTables'
import { SessionAvatar } from './SessionAvatar'
import { SessionWorkspacePanel } from './SessionWorkspacePanel'
import {
  characterSummary,
  firstLetter,
  getCharacterAvatarUrl,
  getUiString,
} from './sessionRoomHelpers'
import {
  resolveStatusBinding,
  tableIsBoundToCharacter,
  type ResolvedStatusBinding,
} from './sessionStatusBindings'
import type { SessionSpeaker } from './sessionRoomTypes'

export type SessionWorldTab = 'characters' | 'status'

function sortedTables(tables: StatusTable[]) {
  return [...tables].sort((first, second) => (
    first.sortOrder - second.sortOrder || first.id - second.id
  ))
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
    return <span className="rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-black text-slate-500 dark:bg-slate-800 dark:text-slate-300">全局状态</span>
  }
  if (binding.kind === 'unavailable') {
    return <span className="rounded-full bg-amber-100 px-2.5 py-1 text-[11px] font-black text-amber-800 dark:bg-amber-500/15 dark:text-amber-200">角色绑定不可用</span>
  }
  return <span className="rounded-full bg-sky-100 px-2.5 py-1 text-[11px] font-black text-sky-700 dark:bg-sky-500/15 dark:text-sky-200">角色 · {binding.name}</span>
}

function EmptyState({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-2xl border border-dashed border-slate-300 bg-white/70 px-6 py-12 text-center text-sm font-semibold text-slate-400 dark:border-slate-700 dark:bg-slate-900/70 dark:text-slate-300">
      {children}
    </div>
  )
}

function CharactersView({
  characters,
  loading,
  normalTables,
  pinnedIdSet,
  playerCharacter,
  scene,
  onSelectStatus,
}: {
  characters: CharacterCard[]
  loading: boolean
  normalTables: StatusTable[]
  pinnedIdSet: Set<number>
  playerCharacter?: SessionPlayerCharacter | null
  scene?: Scene | null
  onSelectStatus: (tableId: number) => void
}) {
  const presentNames = new Set(
    (scene?.presentCharacters ?? []).map((name) => name.trim().toLocaleLowerCase()),
  )
  if (loading) return <EmptyState>正在加载故事角色…</EmptyState>
  if (!characters.length) return <EmptyState>当前故事还没有已挂载角色。</EmptyState>

  return (
    <div className="grid gap-4 xl:grid-cols-2">
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
          <article
            key={character.id}
            className="grid min-h-64 gap-5 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-950 sm:grid-cols-[132px_minmax(0,1fr)]"
          >
            <div className="flex min-h-40 items-center justify-center overflow-hidden rounded-2xl bg-gradient-to-br from-violet-600 via-indigo-500 to-cyan-600 p-4 sm:min-h-0">
              <SessionAvatar
                speaker={characterSpeaker(character, player)}
                className="h-24 w-24 rounded-3xl bg-white/20 text-2xl text-white ring-4 ring-white/15"
              />
            </div>
            <div className="min-w-0">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <h3 className="truncate text-lg font-black text-slate-950 dark:text-slate-100">{character.name}</h3>
                  <p className="mt-1 text-xs font-black text-violet-700 dark:text-violet-300">
                    {player ? '玩家角色' : '故事角色'} · {roleLabel}
                  </p>
                </div>
                <span className={cn(
                  'rounded-full px-2.5 py-1 text-[11px] font-black',
                  present
                    ? 'bg-teal-100 text-teal-700 dark:bg-teal-500/15 dark:text-teal-200'
                    : 'bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-300',
                )}>
                  {present ? '当前在场' : '未在场'}
                </span>
              </div>
              <p className="mt-4 text-sm font-semibold leading-7 text-slate-600 dark:text-slate-300">
                {characterSummary(character)}
              </p>
              <div className="mt-5 border-t border-slate-100 pt-4 dark:border-slate-800">
                <strong className="text-xs font-black text-slate-400">关联状态表 · {boundTables.length}</strong>
                <div className="mt-2 flex flex-wrap gap-2">
                  {boundTables.length ? boundTables.map((table) => (
                    <button
                      key={table.id}
                      type="button"
                      onClick={() => onSelectStatus(table.id)}
                      className={cn(
                        'rounded-lg border px-2.5 py-1.5 text-xs font-black transition hover:-translate-y-0.5',
                        pinnedIdSet.has(table.id)
                          ? 'border-violet-200 bg-violet-50 text-violet-700 dark:border-violet-500/40 dark:bg-violet-500/15 dark:text-violet-200'
                          : 'border-slate-200 bg-slate-50 text-slate-600 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300',
                      )}
                    >
                      {pinnedIdSet.has(table.id) ? '◆' : '◇'} {table.name}
                    </button>
                  )) : <span className="text-xs font-semibold text-slate-400">暂无关联状态表</span>}
                </div>
              </div>
            </div>
          </article>
        )
      })}
    </div>
  )
}

function StatusTableCard({
  table,
  scene,
  primary,
  binding,
  pinned,
  onTogglePinned,
}: {
  table: StatusTable
  scene?: boolean
  primary?: boolean
  binding: ResolvedStatusBinding
  pinned?: boolean
  onTogglePinned?: () => void
}) {
  return (
    <article
      id={`session-status-table-${table.id}`}
      className={cn(
        'scroll-mt-6 overflow-hidden rounded-2xl border bg-white shadow-sm transition dark:bg-slate-950',
        primary
          ? 'border-teal-300 ring-2 ring-teal-100 dark:border-teal-500/50 dark:ring-teal-500/10'
          : 'border-slate-200 dark:border-slate-800',
      )}
    >
      <header className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 px-5 py-4 dark:border-slate-800">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-base font-black text-slate-950 dark:text-slate-100">{table.name}</h3>
            {scene ? (
              <span className="rounded-full bg-teal-100 px-2.5 py-1 text-[11px] font-black text-teal-700 dark:bg-teal-500/15 dark:text-teal-200">
                {primary ? '主场景' : '场景表'}
              </span>
            ) : <BindingBadge binding={binding} />}
          </div>
          {table.description ? (
            <p className="mt-2 text-xs font-semibold leading-5 text-slate-500 dark:text-slate-300">{table.description}</p>
          ) : null}
        </div>
        {!scene && onTogglePinned ? (
          <button
            type="button"
            onClick={onTogglePinned}
            aria-pressed={pinned}
            className={cn(
              'inline-flex h-9 items-center gap-1.5 rounded-lg border px-3 text-xs font-black transition',
              pinned
                ? 'border-violet-200 bg-violet-50 text-violet-700 hover:bg-violet-100 dark:border-violet-500/40 dark:bg-violet-500/15 dark:text-violet-200'
                : 'border-slate-200 bg-white text-slate-500 hover:border-violet-200 hover:text-violet-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300',
            )}
          >
            {pinned ? <PinOff size={14} /> : <Pin size={14} />}
            {pinned ? '取消 HUD 固定' : '固定到 HUD'}
          </button>
        ) : null}
      </header>
      {table.rows.length ? (
        <dl className="divide-y divide-slate-100 dark:divide-slate-800">
          {table.rows.map((row) => (
            <div key={`${table.id}-${row.key}`} className="grid gap-1 px-5 py-3 text-sm leading-6 sm:grid-cols-[minmax(120px,0.34fr)_minmax(0,1fr)] sm:gap-5">
              <dt className="font-bold text-slate-400">{row.key}</dt>
              <dd className="min-w-0 whitespace-pre-wrap break-words font-semibold text-slate-700 dark:text-slate-200">{row.value || '—'}</dd>
            </div>
          ))}
        </dl>
      ) : <p className="px-5 py-8 text-center text-sm font-semibold text-slate-400">暂无字段</p>}
    </article>
  )
}

function SectionTitle({ icon, title, meta }: { icon: React.ReactNode; title: string; meta: string }) {
  return (
    <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
      <div className="flex items-center gap-2">
        <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-white text-violet-700 shadow-sm dark:bg-slate-900 dark:text-violet-200">{icon}</span>
        <h3 className="text-base font-black text-slate-950 dark:text-slate-100">{title}</h3>
      </div>
      <span className="text-xs font-bold text-slate-400">{meta}</span>
    </div>
  )
}

function StatusTablesView({
  sceneTables,
  sceneLoading,
  normalTables,
  normalLoading,
  characters,
  pinnedIdSet,
  onTogglePinned,
}: {
  sceneTables: StatusTable[]
  sceneLoading: boolean
  normalTables: StatusTable[]
  normalLoading: boolean
  characters: CharacterCard[]
  pinnedIdSet: Set<number>
  onTogglePinned: (tableId: number) => void
}) {
  const characterGroups = characters.map((character) => ({
    character,
    tables: normalTables.filter((table) => tableIsBoundToCharacter(table, character, characters)),
  })).filter((group) => group.tables.length)
  const groupedIds = new Set(characterGroups.flatMap((group) => group.tables.map((table) => table.id)))
  const globalTables = normalTables.filter((table) => !groupedIds.has(table.id))

  return (
    <div className="space-y-8">
      <section>
        <SectionTitle icon={<MapPinned size={17} />} title="场景状态" meta={`${sceneTables.length} 张 · 自动进入 HUD`} />
        {sceneLoading ? <EmptyState>正在加载场景表…</EmptyState> : null}
        {!sceneLoading && !sceneTables.length ? <EmptyState>当前会话暂无场景状态表。</EmptyState> : null}
        <div className="grid gap-4 xl:grid-cols-2">
          {sceneTables.map((table, index) => (
            <StatusTableCard key={table.id} table={table} scene primary={index === 0} binding={{ kind: 'global' }} />
          ))}
        </div>
      </section>

      {normalLoading ? <EmptyState>正在加载普通状态表…</EmptyState> : null}
      {!normalLoading && !normalTables.length ? <EmptyState>当前会话暂无普通状态表。</EmptyState> : null}

      {characterGroups.map(({ character, tables }) => (
        <section key={character.id}>
          <SectionTitle icon={<UserRound size={17} />} title={`${character.name} · 人物状态`} meta={`${tables.length} 张状态表`} />
          <div className="grid gap-4 xl:grid-cols-2">
            {tables.map((table) => (
              <StatusTableCard
                key={table.id}
                table={table}
                binding={resolveStatusBinding(table, characters)}
                pinned={pinnedIdSet.has(table.id)}
                onTogglePinned={() => onTogglePinned(table.id)}
              />
            ))}
          </div>
        </section>
      ))}

      {globalTables.length ? (
        <section>
          <SectionTitle icon={<TableProperties size={17} />} title="全局与其他状态" meta={`${globalTables.length} 张状态表`} />
          <div className="grid gap-4 xl:grid-cols-2">
            {globalTables.map((table) => (
              <StatusTableCard
                key={table.id}
                table={table}
                binding={resolveStatusBinding(table, characters)}
                pinned={pinnedIdSet.has(table.id)}
                onTogglePinned={() => onTogglePinned(table.id)}
              />
            ))}
          </div>
        </section>
      ) : null}
    </div>
  )
}

export function SessionWorldPanel({
  open,
  activeTab,
  focusTableId,
  sceneTables,
  sceneTablesLoading,
  normalTables,
  normalTablesLoading,
  characters,
  charactersLoading,
  scene,
  playerCharacter,
  pinnedIdSet,
  onTogglePinned,
  onTabChange,
  onClose,
}: {
  open: boolean
  activeTab: SessionWorldTab
  focusTableId?: number
  sceneTables: StatusTable[]
  sceneTablesLoading: boolean
  normalTables: StatusTable[]
  normalTablesLoading: boolean
  characters: CharacterCard[]
  charactersLoading: boolean
  scene?: Scene | null
  playerCharacter?: SessionPlayerCharacter | null
  pinnedIdSet: Set<number>
  onTogglePinned: (tableId: number) => void
  onTabChange: (tab: SessionWorldTab, focusTableId?: number) => void
  onClose: () => void
}) {
  const orderedScenes = useMemo(() => sortedTables(sceneTables), [sceneTables])
  const orderedNormal = useMemo(() => sortedTables(normalTables), [normalTables])

  useEffect(() => {
    if (!open || activeTab !== 'status' || !focusTableId) return
    const frame = window.requestAnimationFrame(() => {
      document.getElementById(`session-status-table-${focusTableId}`)?.scrollIntoView({
        behavior: 'smooth',
        block: 'start',
      })
    })
    return () => window.cancelAnimationFrame(frame)
  }, [activeTab, focusTableId, open])

  return (
    <SessionWorkspacePanel
      open={open}
      eyebrow="Session world"
      title="角色与状态"
      description="集中查看多角色关系上下文、场景表和全部人物状态；常用普通表可固定到悬浮 HUD。"
      tabs={[
        { id: 'characters', label: '角色', icon: <UsersRound size={17} />, badge: characters.length },
        { id: 'status', label: '状态表', icon: <TableProperties size={17} />, badge: orderedScenes.length + orderedNormal.length },
      ]}
      activeTab={activeTab}
      onTabChange={(tab) => onTabChange(tab)}
      onClose={onClose}
    >
      {activeTab === 'characters' ? (
        <CharactersView
          characters={characters}
          loading={charactersLoading}
          normalTables={orderedNormal}
          pinnedIdSet={pinnedIdSet}
          playerCharacter={playerCharacter}
          scene={scene}
          onSelectStatus={(tableId) => onTabChange('status', tableId)}
        />
      ) : (
        <StatusTablesView
          sceneTables={orderedScenes}
          sceneLoading={sceneTablesLoading}
          normalTables={orderedNormal}
          normalLoading={normalTablesLoading}
          characters={characters}
          pinnedIdSet={pinnedIdSet}
          onTogglePinned={onTogglePinned}
        />
      )}
    </SessionWorkspacePanel>
  )
}
