'use client'

import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { FilePlus2, Loader2, Save, Trash2 } from 'lucide-react'
import { ConfirmDialog } from '@/components/common/Dialog'
import { AppShell, useAppShell } from '@/features/layout/AppShell'
import { listCharacters } from '@/lib/api/characters'
import { listSessions } from '@/lib/api/sessions'
import {
  createSessionStatusTable,
  createStoryStatusTable,
  deleteSessionStatusTable,
  deleteStoryStatusTable,
  listSessionStatusTables,
  listStoryStatusTables,
  updateSessionStatusTable,
  updateStoryStatusTable,
} from '@/lib/api/statusTables'
import { listStories } from '@/lib/api/stories'
import { useStorySelection } from '@/features/stories/useStorySelection'
import {
  STATUS_KIND,
  STATUS_ORIGIN,
  STATUS_UPDATE_FREQUENCY,
  type StatusKind,
  type StatusTable,
  type StatusTableInput,
} from '@/types/statusTables'
import { STATUS_TABLE_VIEW, defaultStatusTableName, originLabel, statusKindLabel, type StatusTableView } from './constants'
import { createEmptyDraft, draftFromTable, validateRows, type TableDraft } from './draft'
import { FieldLabel, Panel, PanelHead } from './components/FormBits'
import { KvEditor } from './components/KvEditor'
import { StatusTableCard } from './components/StatusTableCard'

function nextAvailableName(base: string, names: Iterable<string>) {
  const used = new Set(Array.from(names, (name) => name.trim()))
  if (!used.has(base)) return base
  let suffix = 2
  while (used.has(`${base} ${suffix}`)) suffix += 1
  return `${base} ${suffix}`
}

function StatusTablesContent() {
  const { currentWorkspace } = useAppShell()
  const queryClient = useQueryClient()
  const [view, setView] = useState<StatusTableView>(STATUS_TABLE_VIEW.STORY)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [storyTableId, setStoryTableId] = useState<number | null>(null)
  const [runtimeTableId, setRuntimeTableId] = useState<number | null>(null)
  const [draft, setDraft] = useState<TableDraft>(createEmptyDraft())
  const [kind, setKind] = useState<StatusKind>(STATUS_KIND.NORMAL)
  const [storyCharacterId, setStoryCharacterId] = useState<number | null>(null)
  const [sortOrder, setSortOrder] = useState(0)
  const [formError, setFormError] = useState<string | null>(null)
  const [deleteOpen, setDeleteOpen] = useState(false)

  const storiesQuery = useQuery({
    queryKey: ['play-stories', currentWorkspace],
    queryFn: () => listStories(currentWorkspace ?? ''),
    enabled: Boolean(currentWorkspace),
  })
  const stories = storiesQuery.data ?? []
  const [storyId, setStoryId] = useStorySelection(stories)

  const charactersQuery = useQuery({
    queryKey: ['play-story-characters', currentWorkspace, storyId],
    queryFn: () => listCharacters(currentWorkspace ?? '', storyId ?? 0),
    enabled: Boolean(currentWorkspace && storyId),
  })
  const characters = charactersQuery.data ?? []

  const storyTablesQuery = useQuery({
    queryKey: ['play-story-status-tables', currentWorkspace, storyId],
    queryFn: () => listStoryStatusTables(currentWorkspace ?? '', storyId ?? 0),
    enabled: Boolean(currentWorkspace && storyId),
  })
  const storyTables = storyTablesQuery.data ?? []

  const sessionsQuery = useQuery({
    queryKey: ['play-sessions', currentWorkspace, storyId],
    queryFn: () => listSessions(currentWorkspace ?? '', storyId ?? 0),
    enabled: Boolean(currentWorkspace && storyId),
  })
  const sessions = sessionsQuery.data ?? []

  useEffect(() => {
    setStoryTableId(null)
    setRuntimeTableId(null)
    setSessionId(null)
    setFormError(null)
  }, [storyId])

  useEffect(() => {
    if (!storyTables.length) {
      setStoryTableId(null)
      return
    }
    if (storyTableId === null || !storyTables.some((table) => table.id === storyTableId)) {
      setStoryTableId(storyTables[0].id)
    }
  }, [storyTableId, storyTables])

  useEffect(() => {
    if (!sessions.length) {
      setSessionId(null)
      return
    }
    if (!sessionId || !sessions.some((session) => session.id === sessionId)) {
      setSessionId(sessions[0].id)
    }
  }, [sessionId, sessions])

  const runtimeTablesQuery = useQuery({
    queryKey: ['play-session-status-tables', sessionId],
    queryFn: () => listSessionStatusTables(sessionId ?? ''),
    enabled: Boolean(sessionId),
  })
  const runtimeTables = runtimeTablesQuery.data ?? []

  useEffect(() => {
    if (!runtimeTables.length) {
      setRuntimeTableId(null)
      return
    }
    if (runtimeTableId === null || !runtimeTables.some((table) => table.id === runtimeTableId)) {
      setRuntimeTableId(runtimeTables[0].id)
    }
  }, [runtimeTableId, runtimeTables])

  const selected = view === STATUS_TABLE_VIEW.STORY
    ? storyTables.find((table) => table.id === storyTableId) ?? null
    : runtimeTables.find((table) => table.id === runtimeTableId) ?? null

  useEffect(() => {
    setDraft(draftFromTable(selected))
    setKind(selected?.statusKind ?? STATUS_KIND.NORMAL)
    setStoryCharacterId(selected?.storyCharacterId ?? null)
    setSortOrder(selected?.sortOrder ?? 0)
    setFormError(null)
  }, [selected, view])

  const sourceStoryTable = useMemo(() => (
    selected?.sourceStoryStatusTableId
      ? storyTables.find((table) => table.id === selected.sourceStoryStatusTableId) ?? null
      : null
  ), [selected, storyTables])

  function invalidateStoryTables() {
    return queryClient.invalidateQueries({
      queryKey: ['play-story-status-tables', currentWorkspace, storyId],
    })
  }

  function invalidateRuntimeTables() {
    return queryClient.invalidateQueries({
      queryKey: ['play-session-status-tables', sessionId],
    })
  }

  const createStoryMutation = useMutation({
    mutationFn: () => {
      if (!currentWorkspace || !storyId) throw new Error('请先选择 Story')
      const input: StatusTableInput = {
        name: nextAvailableName(
          defaultStatusTableName(STATUS_KIND.NORMAL),
          storyTables.map((table) => table.name),
        ),
        statusKind: STATUS_KIND.NORMAL,
        description: '',
        keyColumn: '属性',
        valueColumn: '值',
        rows: [],
        metadata: { ui: {} },
        sortOrder: storyTables.length ? Math.max(...storyTables.map((table) => table.sortOrder)) + 10 : 0,
      }
      return createStoryStatusTable(currentWorkspace, storyId, input)
    },
    onSuccess: async (table) => {
      await invalidateStoryTables()
      setStoryTableId(table.id)
    },
    onError: (reason) => setFormError(reason instanceof Error ? reason.message : '新建 Story 状态表失败'),
  })

  const createRuntimeMutation = useMutation({
    mutationFn: () => {
      if (!sessionId) throw new Error('请先选择 Session')
      return createSessionStatusTable(sessionId, {
        name: nextAvailableName(
          defaultStatusTableName(STATUS_KIND.NORMAL),
          runtimeTables.map((table) => table.name),
        ),
        statusKind: STATUS_KIND.NORMAL,
        description: '',
        keyColumn: '属性',
        valueColumn: '值',
        rows: [],
        metadata: { ui: {} },
        sortOrder: runtimeTables.length ? Math.max(...runtimeTables.map((table) => table.sortOrder)) + 10 : 0,
      })
    },
    onSuccess: async (table) => {
      await invalidateRuntimeTables()
      setRuntimeTableId(table.id)
    },
    onError: (reason) => setFormError(reason instanceof Error ? reason.message : '新建 Session 状态表失败'),
  })

  const saveMutation = useMutation({
    mutationFn: () => {
      if (!selected) throw new Error('未选择状态表')
      if (!draft.name.trim()) throw new Error('状态表名不能为空')
      const validated = validateRows(draft.rows)
      if (validated.error) throw new Error(validated.error)
      const rows = kind === STATUS_KIND.SCENE
        ? validated.rows.map((row) => ({
            ...row,
            updateFrequency: STATUS_UPDATE_FREQUENCY.REALTIME,
            updateRule: '',
            deferredIntervalTurns: null,
          }))
        : validated.rows
      if (view === STATUS_TABLE_VIEW.STORY) {
        if (!currentWorkspace || !storyId) throw new Error('Story 不可用')
        return updateStoryStatusTable(currentWorkspace, storyId, selected.id, {
          name: draft.name.trim(),
          statusKind: kind,
          storyCharacterId: kind === STATUS_KIND.NORMAL ? storyCharacterId : null,
          description: draft.description,
          keyColumn: draft.keyColumn,
          valueColumn: draft.valueColumn,
          rows,
          sortOrder,
        })
      }
      if (!sessionId) throw new Error('Session 不可用')
      return updateSessionStatusTable(sessionId, selected.id, {
        name: draft.name.trim(),
        description: draft.description,
        keyColumn: draft.keyColumn,
        valueColumn: draft.valueColumn,
        rows,
        sortOrder,
      })
    },
    onSuccess: async () => {
      setFormError(null)
      if (view === STATUS_TABLE_VIEW.STORY) await invalidateStoryTables()
      else await invalidateRuntimeTables()
    },
    onError: (reason) => setFormError(reason instanceof Error ? reason.message : '保存状态表失败'),
  })

  const deleteMutation = useMutation({
    mutationFn: () => {
      if (!selected) throw new Error('未选择状态表')
      if (view === STATUS_TABLE_VIEW.STORY) {
        if (!currentWorkspace || !storyId) throw new Error('Story 不可用')
        return deleteStoryStatusTable(currentWorkspace, storyId, selected.id)
      }
      if (!sessionId) throw new Error('Session 不可用')
      return deleteSessionStatusTable(sessionId, selected.id)
    },
    onSuccess: async () => {
      setDeleteOpen(false)
      if (view === STATUS_TABLE_VIEW.STORY) {
        setStoryTableId(null)
        await invalidateStoryTables()
      } else {
        setRuntimeTableId(null)
        await invalidateRuntimeTables()
      }
    },
    onError: (reason) => setFormError(reason instanceof Error ? reason.message : '删除状态表失败'),
  })

  const visibleTables = view === STATUS_TABLE_VIEW.STORY ? storyTables : runtimeTables
  const loading = view === STATUS_TABLE_VIEW.STORY ? storyTablesQuery.isLoading : runtimeTablesQuery.isLoading

  return (
    <div className="min-w-0 px-5 py-7 lg:px-8">
      <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-slate-950">状态表</h1>
          <p className="mt-2 text-sm text-slate-500">Story 直接拥有状态表定义；Session 在创建时复制定义，并可保留自己的运行时表。</p>
        </div>
        <label className="grid min-w-72 gap-2 text-xs font-black uppercase text-slate-500">
          当前 Story
          <select value={storyId ?? ''} onChange={(event) => setStoryId(event.target.value ? Number(event.target.value) : null)} className="h-11 rounded-xl border border-slate-200 bg-white px-3 text-sm font-bold normal-case text-slate-900 outline-none focus:border-violet-300 focus:ring-4 focus:ring-violet-100">
            {!stories.length ? <option value="">暂无 Story</option> : null}
            {stories.map((story) => <option key={story.id} value={story.id}>{story.title}</option>)}
          </select>
        </label>
      </header>

      <div className="mb-5 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-white p-2 shadow-sm">
        <div className="flex gap-2">
          <button type="button" onClick={() => setView(STATUS_TABLE_VIEW.STORY)} className={`h-10 rounded-xl px-4 text-sm font-black transition ${view === STATUS_TABLE_VIEW.STORY ? 'bg-violet-600 text-white' : 'text-slate-500 hover:bg-slate-100'}`}>Story 定义</button>
          <button type="button" onClick={() => setView(STATUS_TABLE_VIEW.RUNTIME)} className={`h-10 rounded-xl px-4 text-sm font-black transition ${view === STATUS_TABLE_VIEW.RUNTIME ? 'bg-violet-600 text-white' : 'text-slate-500 hover:bg-slate-100'}`}>Session 运行时</button>
        </div>
        {view === STATUS_TABLE_VIEW.RUNTIME ? (
          <label className="flex items-center gap-2 px-2 text-xs font-black text-slate-500">SESSION
            <select value={sessionId ?? ''} onChange={(event) => { setSessionId(event.target.value || null); setRuntimeTableId(null) }} className="h-10 min-w-60 rounded-lg border border-slate-200 bg-white px-3 text-sm font-bold normal-case text-slate-900">
              {!sessions.length ? <option value="">暂无 Session</option> : null}
              {sessions.map((session) => <option key={session.id} value={session.id}>{session.title || session.id}</option>)}
            </select>
          </label>
        ) : null}
      </div>

      {formError ? <p className="mb-4 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-bold text-rose-700">{formError}</p> : null}

      <section className="grid gap-5 xl:grid-cols-[350px_minmax(0,1fr)]">
        <Panel>
          <PanelHead title={view === STATUS_TABLE_VIEW.STORY ? 'Story 状态表' : '运行时状态表'} description={view === STATUS_TABLE_VIEW.STORY ? '新建 Session 时按当前定义复制；已有 Session 不跟随修改。' : '同时展示 Story 副本与 Session 原生表。'} />
          <div className="p-4">
            <button type="button" onClick={() => view === STATUS_TABLE_VIEW.STORY ? createStoryMutation.mutate() : createRuntimeMutation.mutate()} disabled={(view === STATUS_TABLE_VIEW.STORY ? !storyId || createStoryMutation.isPending : !sessionId || createRuntimeMutation.isPending)} className="mb-4 inline-flex h-10 w-full items-center justify-center gap-2 rounded-lg bg-violet-600 px-4 text-sm font-bold text-white disabled:opacity-50">
              {(createStoryMutation.isPending || createRuntimeMutation.isPending) ? <Loader2 size={16} className="animate-spin" /> : <FilePlus2 size={16} />}
              {view === STATUS_TABLE_VIEW.STORY ? '新建 Story 状态表' : '新建 Session 原生表'}
            </button>
            <div className="max-h-[720px] space-y-3 overflow-y-auto pr-1">
              {loading ? <p className="py-10 text-center text-sm text-slate-400">加载中…</p> : null}
              {!loading && !visibleTables.length ? <p className="py-10 text-center text-sm text-slate-400">暂无状态表</p> : null}
              {visibleTables.map((table) => (
                <StatusTableCard key={table.id} table={table} active={table.id === selected?.id} extraChips={view === STATUS_TABLE_VIEW.STORY && table.storyCharacterId ? <span className="rounded-full border border-sky-200 bg-sky-50 px-2 text-xs font-bold text-sky-700">角色 #{table.storyCharacterId}</span> : undefined} onClick={() => view === STATUS_TABLE_VIEW.STORY ? setStoryTableId(table.id) : setRuntimeTableId(table.id)} />
              ))}
            </div>
          </div>
        </Panel>

        <Panel>
          <div className="flex flex-wrap items-start justify-between gap-4 border-b border-slate-100 px-5 py-4">
            <div><h2 className="text-lg font-bold text-slate-950">{selected?.name ?? '状态表编辑'}</h2><p className="mt-1 text-sm text-slate-500">{selected ? `${statusKindLabel(selected.statusKind)} · #${selected.id}` : '请先选择或新建状态表。'}</p></div>
            <div className="flex gap-2"><button type="button" onClick={() => setDeleteOpen(true)} disabled={!selected} className="inline-flex h-10 items-center gap-2 rounded-lg border border-rose-200 px-3 text-sm font-bold text-rose-700 disabled:opacity-40"><Trash2 size={16} />删除</button><button type="button" onClick={() => saveMutation.mutate()} disabled={!selected || saveMutation.isPending} className="inline-flex h-10 items-center gap-2 rounded-lg bg-violet-600 px-4 text-sm font-bold text-white disabled:opacity-50">{saveMutation.isPending ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}保存</button></div>
          </div>
          {selected ? (
            <div className="space-y-5 p-5">
              <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_180px_130px]">
                <label><FieldLabel label="状态表名" note="必填" /><input value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} className="h-10 w-full rounded-lg border border-slate-200 px-3 text-sm outline-none focus:border-violet-300" /></label>
                <label><FieldLabel label="状态种类" note={view === STATUS_TABLE_VIEW.RUNTIME ? '只读' : '定义'} /><select disabled={view === STATUS_TABLE_VIEW.RUNTIME} value={kind} onChange={(event) => setKind(event.target.value as StatusKind)} className="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm disabled:bg-slate-100"><option value={STATUS_KIND.NORMAL}>普通状态</option><option value={STATUS_KIND.SCENE}>场景</option></select></label>
                <label><FieldLabel label="排序" /><input type="number" value={sortOrder} onChange={(event) => setSortOrder(Number(event.target.value) || 0)} className="h-10 w-full rounded-lg border border-slate-200 px-3 text-sm" /></label>
              </div>
              {view === STATUS_TABLE_VIEW.STORY ? (
                <label className="block"><FieldLabel label="绑定角色" note="一张表最多一个角色" /><select disabled={kind === STATUS_KIND.SCENE} value={storyCharacterId ?? ''} onChange={(event) => setStoryCharacterId(event.target.value ? Number(event.target.value) : null)} className="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm disabled:bg-slate-100"><option value="">不绑定角色</option>{characters.map((character) => <option key={character.id} value={character.id}>{character.name} · #{character.id}</option>)}</select></label>
              ) : (
                <div className="grid gap-4 md:grid-cols-2"><div><FieldLabel label="来源" note="只读" /><div className="flex h-10 items-center rounded-lg border border-slate-200 bg-slate-50 px-3 text-sm font-bold text-slate-600">{originLabel(selected.origin)}</div></div><div><FieldLabel label="Story 源定义" note="删除源后可为空" /><div className="flex h-10 items-center rounded-lg border border-slate-200 bg-slate-50 px-3 text-sm font-bold text-slate-600">{selected.origin === STATUS_ORIGIN.STORY_COPY ? sourceStoryTable ? `${sourceStoryTable.name} · #${sourceStoryTable.id}` : `已删除的源 #${selected.sourceStoryStatusTableId ?? '?'}` : '无'}</div></div></div>
              )}
              <label className="block"><FieldLabel label="用途与更新规则" note="可选" /><textarea value={draft.description} onChange={(event) => setDraft({ ...draft, description: event.target.value })} className="min-h-24 w-full rounded-lg border border-slate-200 px-3 py-3 text-sm leading-6 outline-none focus:border-violet-300" /></label>
              <div className="grid gap-4 md:grid-cols-2"><label><FieldLabel label="Key 列名" /><input value={draft.keyColumn} onChange={(event) => setDraft({ ...draft, keyColumn: event.target.value })} className="h-10 w-full rounded-lg border border-slate-200 px-3 text-sm" /></label><label><FieldLabel label="Value 列名" /><input value={draft.valueColumn} onChange={(event) => setDraft({ ...draft, valueColumn: event.target.value })} className="h-10 w-full rounded-lg border border-slate-200 px-3 text-sm" /></label></div>
              <KvEditor draft={draft} onChange={setDraft} toolbarTitle="状态字段" isScene={kind === STATUS_KIND.SCENE} />
            </div>
          ) : <p className="px-6 py-20 text-center text-sm text-slate-400">请选择或新建状态表。</p>}
        </Panel>
      </section>

      {deleteOpen && selected ? <ConfirmDialog title={view === STATUS_TABLE_VIEW.STORY ? '删除 Story 状态表' : '删除运行时状态表'} heading={`确定删除「${selected.name}」？`} body={view === STATUS_TABLE_VIEW.STORY ? '只删除 Story 定义；已经复制到现有 Session 的运行时表保留，并失去源外键。' : '只删除当前 Session 内的状态表。'} pending={deleteMutation.isPending} onClose={() => setDeleteOpen(false)} onConfirm={() => deleteMutation.mutate()} /> : null}
    </div>
  )
}

export function StatusTablesPage() {
  return <AppShell><StatusTablesContent /></AppShell>
}
