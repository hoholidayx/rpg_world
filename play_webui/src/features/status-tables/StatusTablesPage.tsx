'use client'

import { useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Check,
  Copy,
  FilePlus2,
  Loader2,
  Plus,
  Save,
  TableProperties,
  Trash2,
  X,
} from 'lucide-react'
import { AppShell, useAppShell } from '@/features/layout/AppShell'
import { listSessions } from '@/lib/api/sessions'
import {
  createSessionStatusTable,
  createStatusTemplate,
  deleteSessionStatusTable,
  deleteStatusTemplate,
  listSessionStatusTables,
  listStatusTemplates,
  listStoryStatusMounts,
  mountStatusTemplate,
  unmountStatusTemplate,
  updateSessionStatusTable,
  updateStatusTemplate,
} from '@/lib/api/statusTables'
import { listStories } from '@/lib/api/stories'
import type { SessionSummary } from '@/types/session'
import type { StorySummary } from '@/types/story'
import type { StatusKind, StatusOrigin, StatusRow, StatusTable, StoryStatusMount } from '@/types/statusTables'

type ViewMode = 'templates' | 'runtime'

type TableDraft = {
  name: string
  description: string
  keyColumn: string
  valueColumn: string
  rows: StatusRow[]
}

const DEFAULT_KEY_COLUMN = '属性'
const DEFAULT_VALUE_COLUMN = '值'

const emptyDraft: TableDraft = {
  name: '',
  description: '',
  keyColumn: DEFAULT_KEY_COLUMN,
  valueColumn: DEFAULT_VALUE_COLUMN,
  rows: [],
}

function formatDate(value?: string | null) {
  if (!value) return '暂无'
  return value.replace('T', ' ').slice(0, 16)
}

function statusKindLabel(kind: StatusKind) {
  return kind === 'scene' ? '场景' : '普通状态'
}

function statusKindHint(kind: StatusKind) {
  return kind === 'scene' ? '场景前缀' : '结构化上下文'
}

function originLabel(origin?: StatusOrigin | null) {
  if (origin === 'template_copy') return '模板副本'
  if (origin === 'session_native') return '会话新建'
  return '未知来源'
}

function draftFromTable(table: StatusTable | null): TableDraft {
  if (!table) return emptyDraft
  return {
    name: table.name,
    description: table.description,
    keyColumn: table.keyColumn || DEFAULT_KEY_COLUMN,
    valueColumn: table.valueColumn || DEFAULT_VALUE_COLUMN,
    rows: table.rows.map((row) => ({
      key: row.key,
      value: row.value,
      runtimeKeyLocked: row.runtimeKeyLocked,
      metadata: row.metadata ?? {},
    })),
  }
}

function validateRows(rows: StatusRow[]) {
  const seen = new Set<string>()
  const normalized: StatusRow[] = []

  for (const row of rows) {
    const key = row.key.trim()
    if (!key) return { error: 'Key 不能为空', rows: [] as StatusRow[] }
    if (seen.has(key)) return { error: `Key 不能重复：${key}`, rows: [] as StatusRow[] }
    seen.add(key)
    normalized.push({
      key,
      value: row.value,
      runtimeKeyLocked: row.runtimeKeyLocked,
      metadata: row.metadata ?? {},
    })
  }

  return { error: null, rows: normalized }
}

function uniqueStatusTableName(baseName: string, tables: StatusTable[]) {
  const names = new Set(tables.map((table) => table.name))
  if (!names.has(baseName)) return baseName

  const firstCopy = `${baseName} 副本`
  if (!names.has(firstCopy)) return firstCopy

  for (let index = 2; index < 1000; index += 1) {
    const candidate = `${firstCopy} ${index}`
    if (!names.has(candidate)) return candidate
  }

  return `${firstCopy} ${Date.now()}`
}

function ModalShell({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/20 px-4 py-8 backdrop-blur-sm">
      <section className="w-full max-w-xl overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl shadow-slate-300/70">
        <header className="flex items-center justify-between border-b border-slate-200 px-6 py-5">
          <h2 className="text-xl font-bold text-slate-950">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            className="flex h-9 w-9 items-center justify-center rounded-lg text-slate-500 transition hover:bg-slate-100 hover:text-slate-900"
            aria-label="关闭"
          >
            <X size={18} />
          </button>
        </header>
        {children}
      </section>
    </div>
  )
}

function Chip({ children, tone = 'violet' }: { children: ReactNode; tone?: 'violet' | 'green' | 'amber' | 'sky' | 'gray' }) {
  const classes = {
    violet: 'border-violet-200 bg-violet-50 text-violet-700',
    green: 'border-emerald-200 bg-emerald-50 text-emerald-700',
    amber: 'border-amber-200 bg-amber-50 text-amber-700',
    sky: 'border-sky-200 bg-sky-50 text-sky-700',
    gray: 'border-slate-200 bg-slate-50 text-slate-500',
  }

  return (
    <span className={`inline-flex min-h-6 items-center rounded-full border px-2 text-xs font-bold ${classes[tone]}`}>
      {children}
    </span>
  )
}

function KindField({ kind, hint }: { kind: StatusKind; hint?: string }) {
  return (
    <div className="grid min-h-10 grid-cols-[10px_auto_minmax(0,1fr)] items-center gap-2 rounded-[10px] border border-slate-200 bg-slate-50 px-3">
      <span className={`h-2.5 w-2.5 rounded-full ${kind === 'scene' ? 'bg-sky-600' : 'bg-violet-600'}`} />
      <strong className="text-sm text-slate-950">{statusKindLabel(kind)}</strong>
      <em className="truncate text-right text-xs not-italic text-slate-500">{hint ?? statusKindHint(kind)}</em>
    </div>
  )
}

function ReadOnlyField({ dotClass, title, hint }: { dotClass: string; title: string; hint: string }) {
  return (
    <div className="grid min-h-10 grid-cols-[10px_auto_minmax(0,1fr)] items-center gap-2 rounded-[10px] border border-slate-200 bg-slate-50 px-3">
      <span className={`h-2.5 w-2.5 rounded-full ${dotClass}`} />
      <strong className="text-sm text-slate-950">{title}</strong>
      <em className="truncate text-right text-xs not-italic text-slate-500">{hint}</em>
    </div>
  )
}

function FieldLabel({ label, note }: { label: string; note?: string }) {
  return (
    <div className="mb-2 flex items-center justify-between text-sm font-extrabold text-slate-950">
      <span>{label}</span>
      {note ? <span className="text-xs font-bold text-slate-400">{note}</span> : null}
    </div>
  )
}

function Panel({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <section className={`overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm ${className}`}>
      {children}
    </section>
  )
}

function PanelHead({ title, description }: { title: string; description: string }) {
  return (
    <header className="border-b border-slate-100 px-5 py-4">
      <h2 className="text-lg font-bold text-slate-950">{title}</h2>
      <p className="mt-1 text-sm leading-5 text-slate-500">{description}</p>
    </header>
  )
}

function StatusTableCard({
  table,
  active,
  mounted,
  onClick,
}: {
  table: StatusTable
  active: boolean
  mounted?: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`relative w-full rounded-xl border bg-white p-3 text-left transition hover:border-violet-300 hover:bg-violet-50/30 hover:shadow-md dark:hover:border-violet-400/40 dark:hover:bg-violet-500/[0.08] ${
        active
          ? 'border-violet-300 bg-gradient-to-r from-violet-50 to-white shadow-[0_0_0_3px_rgba(124,58,237,0.10)] dark:border-violet-400/50 dark:bg-violet-500/[0.08] dark:bg-none dark:shadow-[0_0_0_1px_rgba(167,139,250,0.14)]'
          : 'border-slate-200'
      }`}
    >
      {active ? <span className="absolute bottom-3 left-0 top-3 w-1 rounded-r-full bg-violet-600" /> : null}
      <div className="flex items-start justify-between gap-3">
        <h3 className="min-w-0 truncate text-sm font-bold text-slate-950">{table.name}</h3>
        <Chip tone={table.statusKind === 'scene' ? 'sky' : 'violet'}>{statusKindLabel(table.statusKind)}</Chip>
      </div>
      <p className="mt-2 line-clamp-2 min-h-10 text-sm leading-5 text-slate-500">
        {table.description || (table.statusKind === 'scene' ? '场景状态表。' : '普通状态表进入结构化上下文。')}
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        {typeof mounted === 'boolean' ? <Chip tone={mounted ? 'green' : 'gray'}>{mounted ? '已挂载' : '未挂载'}</Chip> : null}
        {table.origin ? <Chip tone={table.origin === 'template_copy' ? 'amber' : 'green'}>{originLabel(table.origin)}</Chip> : null}
        <Chip tone="gray">{table.rows.length} key</Chip>
      </div>
    </button>
  )
}

function KvEditor({
  draft,
  onChange,
  toolbarTitle,
}: {
  draft: TableDraft
  onChange: (draft: TableDraft) => void
  toolbarTitle: string
}) {
  function updateRow(index: number, patch: Partial<StatusRow>) {
    onChange({
      ...draft,
      rows: draft.rows.map((row, rowIndex) => (rowIndex === index ? { ...row, ...patch } : row)),
    })
  }

  function addRow() {
    onChange({
      ...draft,
      rows: [...draft.rows, { key: '', value: '', runtimeKeyLocked: false, metadata: {} }],
    })
  }

  function deleteRow(index: number) {
    onChange({
      ...draft,
      rows: draft.rows.filter((_, rowIndex) => rowIndex !== index),
    })
  }

  return (
    <div>
      <div className="flex items-center justify-between rounded-t-xl border border-slate-200 bg-slate-50 px-3 py-2">
        <strong className="text-sm text-slate-950">{toolbarTitle}</strong>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={addRow}
            className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-extrabold text-slate-600 transition hover:border-violet-200 hover:text-violet-700"
          >
            + Key
          </button>
          <button
            type="button"
            onClick={() => deleteRow(draft.rows.length - 1)}
            disabled={!draft.rows.length}
            className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-extrabold text-slate-600 transition hover:border-rose-200 hover:text-rose-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            删除
          </button>
        </div>
      </div>
      <div className="overflow-x-auto rounded-b-xl border-x border-b border-slate-200">
        <div className="min-w-[650px]">
          <div className="grid grid-cols-[180px_minmax(0,1fr)_126px_60px] items-center gap-3 border-b border-slate-100 bg-slate-50 px-3 py-3 text-xs font-extrabold text-slate-600">
            <span>Key</span>
            <span>Value</span>
            <span>运行时锁定 key</span>
            <span />
          </div>
          {draft.rows.length ? draft.rows.map((row, index) => (
            <div key={index} className="grid grid-cols-[180px_minmax(0,1fr)_126px_60px] items-center gap-3 border-b border-slate-100 bg-white px-3 py-3 last:border-b-0">
              <input
                value={row.key}
                onChange={(event) => updateRow(index, { key: event.target.value })}
                className="h-9 min-w-0 rounded-lg border border-slate-200 px-3 text-sm text-slate-950 outline-none transition focus:border-violet-300 focus:ring-4 focus:ring-violet-100"
              />
              <input
                value={row.value}
                onChange={(event) => updateRow(index, { value: event.target.value })}
                className="h-9 min-w-0 rounded-lg border border-slate-200 px-3 text-sm text-slate-950 outline-none transition focus:border-violet-300 focus:ring-4 focus:ring-violet-100"
              />
              <label className="flex items-center justify-center">
                <input
                  type="checkbox"
                  checked={row.runtimeKeyLocked}
                  onChange={(event) => updateRow(index, { runtimeKeyLocked: event.target.checked })}
                  className="peer sr-only"
                />
                <span className="grid h-6 w-6 place-items-center rounded-md border border-slate-300 bg-white transition peer-checked:border-violet-600 peer-checked:bg-violet-600">
                  {row.runtimeKeyLocked ? <Check size={14} className="text-white" /> : null}
                </span>
              </label>
              <button
                type="button"
                onClick={() => deleteRow(index)}
                className="h-9 rounded-lg bg-slate-50 text-xs font-extrabold text-slate-500 transition hover:bg-rose-50 hover:text-rose-700"
              >
                删除
              </button>
            </div>
          )) : (
            <div className="px-3 py-8 text-center text-sm text-slate-400">暂无 key，点击 + Key 添加。</div>
          )}
        </div>
      </div>
      <p className="mt-2 text-xs leading-5 text-slate-400">
        勾选后，LLM 运行时不能删除或重命名该 key；value 仍可更新，管理端仍可编辑。
      </p>
    </div>
  )
}

function StatusKindCreateDialog({
  title = '新增模板',
  pending,
  onClose,
  onCreate,
}: {
  title?: string
  pending: boolean
  onClose: () => void
  onCreate: (kind: StatusKind) => void
}) {
  const [kind, setKind] = useState<StatusKind>('normal')

  return (
    <ModalShell title={title} onClose={onClose}>
      <div className="space-y-5 px-6 py-5">
        <label>
          <FieldLabel label="状态种类" note="创建后只读" />
          <select
            value={kind}
            onChange={(event) => setKind(event.target.value as StatusKind)}
            className="h-10 w-full rounded-[10px] border border-slate-200 bg-white px-3 text-sm text-slate-950 outline-none transition focus:border-violet-300 focus:ring-4 focus:ring-violet-100"
          >
            <option value="normal">普通状态</option>
            <option value="scene">场景</option>
          </select>
        </label>
      </div>
      <footer className="flex justify-end gap-3 border-t border-slate-100 px-6 py-4">
        <button type="button" onClick={onClose} className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-bold text-slate-600">
          取消
        </button>
        <button
          type="button"
          onClick={() => onCreate(kind)}
          disabled={pending}
          className="inline-flex items-center gap-2 rounded-lg bg-violet-600 px-4 py-2 text-sm font-bold text-white shadow-lg shadow-violet-200 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {pending ? <Loader2 size={16} className="animate-spin" /> : <FilePlus2 size={16} />}
          创建
        </button>
      </footer>
    </ModalShell>
  )
}

function DeleteDialog({
  title,
  heading,
  body,
  pending,
  onClose,
  onDelete,
}: {
  title: string
  heading: string
  body: string
  pending: boolean
  onClose: () => void
  onDelete: () => void
}) {
  return (
    <ModalShell title={title} onClose={onClose}>
      <div className="px-6 py-5">
        <div className="rounded-2xl border border-rose-100 bg-rose-50 px-4 py-4">
          <h3 className="text-sm font-bold text-rose-700">{heading}</h3>
          <p className="mt-2 text-sm leading-6 text-rose-700/80">{body}</p>
        </div>
      </div>
      <footer className="flex items-center justify-end gap-2 border-t border-slate-200 bg-slate-50 px-6 py-4">
        <button
          type="button"
          onClick={onClose}
          className="h-10 rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700 transition hover:border-violet-200 hover:text-violet-700"
        >
          取消
        </button>
        <button
          type="button"
          onClick={onDelete}
          disabled={pending}
          className="flex h-10 items-center gap-2 rounded-lg bg-rose-600 px-4 text-sm font-semibold text-white shadow-lg shadow-rose-100 transition hover:bg-rose-700 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {pending ? <Loader2 size={16} className="animate-spin" /> : <Trash2 size={16} />}
          删除
        </button>
      </footer>
    </ModalShell>
  )
}

function MountDialog({
  stories,
  selectedTemplate,
  selectedTemplateMounts,
  pending,
  onClose,
  onMount,
}: {
  stories: StorySummary[]
  selectedTemplate: StatusTable | null
  selectedTemplateMounts: { story: StorySummary; mount: StoryStatusMount }[]
  pending: boolean
  onClose: () => void
  onMount: (storyId: number) => void
}) {
  return (
    <ModalShell title="添加故事挂载" onClose={onClose}>
      <div className="border-b border-slate-200 bg-slate-50/70 px-6 py-4">
        <p className="text-sm text-slate-500">
          {selectedTemplate ? `将「${selectedTemplate.name}」添加到故事。` : '请先选择一个状态表模板。'}
        </p>
      </div>
      <div className="max-h-[520px] overflow-y-auto px-5 py-5">
        <div className="rounded-2xl border border-slate-200 bg-white">
          {stories.length ? stories.map((story) => {
            const alreadyMountedInStory = selectedTemplateMounts.some((mount) => mount.story.id === story.id)
            return (
              <article
                key={story.id}
                className="grid gap-3 border-b border-slate-100 px-4 py-4 last:border-b-0 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center"
              >
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="truncate text-sm font-bold text-slate-950">{story.title}</h3>
                    {alreadyMountedInStory ? (
                      <span className="rounded-md bg-emerald-100 px-2 py-0.5 text-[11px] font-bold text-emerald-700">已挂载</span>
                    ) : null}
                  </div>
                  <p className="mt-1 line-clamp-2 text-xs leading-5 text-slate-500">{story.summary || '暂无故事摘要'}</p>
                </div>
                <button
                  type="button"
                  onClick={() => onMount(story.id)}
                  disabled={!selectedTemplate || alreadyMountedInStory || pending}
                  className="flex h-10 items-center justify-center gap-2 rounded-lg bg-violet-600 px-4 text-sm font-semibold text-white shadow-lg shadow-violet-100 transition hover:bg-violet-700 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-500 disabled:shadow-none"
                >
                  {pending ? <Loader2 size={16} className="animate-spin" /> : alreadyMountedInStory ? <Check size={16} /> : <Plus size={16} />}
                  {alreadyMountedInStory ? '已添加' : '添加'}
                </button>
              </article>
            )
          }) : (
            <div className="px-4 py-10 text-center text-sm text-slate-500">暂无故事</div>
          )}
        </div>
      </div>
      <footer className="flex items-center justify-between border-t border-slate-200 bg-slate-50 px-6 py-4 text-xs text-slate-500">
        <span>添加后右侧会显示当前模板的故事挂载。</span>
        <button
          type="button"
          onClick={onClose}
          className="h-9 rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700 transition hover:border-violet-200 hover:text-violet-700"
        >
          完成
        </button>
      </footer>
    </ModalShell>
  )
}

function CopyTemplateToSessionDialog({
  selectedTemplate,
  story,
  sessions,
  selectedSessionId,
  loading,
  pending,
  onSelectSession,
  onClose,
  onCopy,
}: {
  selectedTemplate: StatusTable | null
  story: StorySummary
  sessions: SessionSummary[]
  selectedSessionId: string | null
  loading: boolean
  pending: boolean
  onSelectSession: (sessionId: string) => void
  onClose: () => void
  onCopy: () => void
}) {
  return (
    <ModalShell title="复制到会话" onClose={onClose}>
      <div className="border-b border-slate-200 bg-slate-50/70 px-6 py-4">
        <p className="text-sm text-slate-500">
          {selectedTemplate ? `将「${selectedTemplate.name}」复制到「${story.title}」的一个会话运行时。` : '请先选择一个状态表模板。'}
        </p>
      </div>
      <div className="space-y-4 px-6 py-5">
        <label className="block">
          <FieldLabel label="会话" note="单选" />
          <select
            value={selectedSessionId ?? ''}
            onChange={(event) => onSelectSession(event.target.value)}
            disabled={loading || !sessions.length}
            className="h-10 w-full rounded-[10px] border border-slate-200 bg-white px-3 text-sm text-slate-950 outline-none transition focus:border-violet-300 focus:ring-4 focus:ring-violet-100 disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-slate-400"
          >
            {sessions.map((session) => (
              <option key={session.id} value={session.id}>{session.title || session.id}</option>
            ))}
          </select>
        </label>
        <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-xs leading-5 text-slate-500">
          复制后会在目标会话里新增一张运行时状态表；如果标题重复，会自动添加“副本”后缀。
        </div>
        {loading ? <div className="text-sm text-slate-400">加载会话中...</div> : null}
        {!loading && !sessions.length ? <div className="text-sm text-slate-500">该故事暂无会话。</div> : null}
      </div>
      <footer className="flex items-center justify-end gap-2 border-t border-slate-200 bg-slate-50 px-6 py-4">
        <button
          type="button"
          onClick={onClose}
          className="h-10 rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700 transition hover:border-violet-200 hover:text-violet-700"
        >
          取消
        </button>
        <button
          type="button"
          onClick={onCopy}
          disabled={!selectedTemplate || !selectedSessionId || pending}
          className="flex h-10 items-center gap-2 rounded-lg bg-violet-600 px-4 text-sm font-semibold text-white shadow-lg shadow-violet-100 transition hover:bg-violet-700 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-500 disabled:shadow-none"
        >
          {pending ? <Loader2 size={16} className="animate-spin" /> : <Copy size={16} />}
          复制
        </button>
      </footer>
    </ModalShell>
  )
}

function StatusTablesContent() {
  const { currentWorkspace } = useAppShell()
  const queryClient = useQueryClient()
  const [view, setView] = useState<ViewMode>('templates')
  const [selectedTemplateId, setSelectedTemplateId] = useState<number | null>(null)
  const [selectedStoryId, setSelectedStoryId] = useState<number | null>(null)
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null)
  const [selectedRuntimeTableId, setSelectedRuntimeTableId] = useState<number | null>(null)
  const [templateDraft, setTemplateDraft] = useState<TableDraft>(emptyDraft)
  const [runtimeDraft, setRuntimeDraft] = useState<TableDraft>(emptyDraft)
  const [formError, setFormError] = useState('')
  const [createTemplateOpen, setCreateTemplateOpen] = useState(false)
  const [createRuntimeOpen, setCreateRuntimeOpen] = useState(false)
  const [mountDialogOpen, setMountDialogOpen] = useState(false)
  const [copyTargetStory, setCopyTargetStory] = useState<StorySummary | null>(null)
  const [copySessionId, setCopySessionId] = useState<string | null>(null)
  const [deleteTemplateOpen, setDeleteTemplateOpen] = useState(false)
  const [deleteRuntimeOpen, setDeleteRuntimeOpen] = useState(false)

  const storiesQuery = useQuery({
    queryKey: ['play-stories', currentWorkspace],
    queryFn: () => listStories(currentWorkspace ?? ''),
    enabled: Boolean(currentWorkspace),
  })
  const templatesQuery = useQuery({
    queryKey: ['play-status-templates', currentWorkspace],
    queryFn: () => listStatusTemplates(currentWorkspace ?? ''),
    enabled: Boolean(currentWorkspace),
  })
  const sessionsQuery = useQuery({
    queryKey: ['play-sessions', currentWorkspace, selectedStoryId],
    queryFn: () => listSessions(currentWorkspace ?? '', selectedStoryId ?? 0),
    enabled: Boolean(currentWorkspace && selectedStoryId),
  })
  const runtimeTablesQuery = useQuery({
    queryKey: ['play-session-status-tables', selectedSessionId],
    queryFn: () => listSessionStatusTables(selectedSessionId ?? ''),
    enabled: Boolean(selectedSessionId),
  })
  const copySessionsQuery = useQuery({
    queryKey: ['play-sessions', currentWorkspace, copyTargetStory?.id],
    queryFn: () => listSessions(currentWorkspace ?? '', copyTargetStory?.id ?? 0),
    enabled: Boolean(currentWorkspace && copyTargetStory),
  })

  const stories = storiesQuery.data ?? []
  const templates = templatesQuery.data ?? []
  const sessions = sessionsQuery.data ?? []
  const runtimeTables = runtimeTablesQuery.data ?? []
  const copySessions = copySessionsQuery.data ?? []

  const storyMountQueries = useQueries({
    queries: stories.map((story) => ({
      queryKey: ['play-story-status-mounts', currentWorkspace, story.id],
      queryFn: () => listStoryStatusMounts(currentWorkspace ?? '', story.id),
      enabled: Boolean(currentWorkspace),
    })),
  })

  const storyMountGroups = useMemo(
    () => stories.map((story, index) => ({ story, mounts: storyMountQueries[index]?.data ?? [] })),
    [stories, storyMountQueries],
  )
  const mountedTemplateIds = useMemo(() => {
    const ids = new Set<number>()
    storyMountGroups.forEach((group) => {
      group.mounts.forEach((mount) => ids.add(mount.statusTableId))
    })
    return ids
  }, [storyMountGroups])
  const selectedTemplate = templates.find((table) => table.id === selectedTemplateId) ?? null
  const selectedTemplateMounts = useMemo(
    () => storyMountGroups.flatMap((group) => (
      group.mounts
        .filter((mount) => selectedTemplate && mount.statusTableId === selectedTemplate.id)
        .map((mount) => ({ story: group.story, mount }))
    )),
    [selectedTemplate, storyMountGroups],
  )
  const selectedRuntimeTable = runtimeTables.find((table) => table.id === selectedRuntimeTableId) ?? null
  const selectedSession = sessions.find((session) => session.id === selectedSessionId) ?? null
  useEffect(() => {
    if (!selectedTemplateId && templates.length) setSelectedTemplateId(templates[0].id)
    if (selectedTemplateId && templates.length && !templates.some((table) => table.id === selectedTemplateId)) {
      setSelectedTemplateId(templates[0].id)
    }
  }, [selectedTemplateId, templates])

  useEffect(() => {
    setTemplateDraft(draftFromTable(selectedTemplate))
    setFormError('')
  }, [selectedTemplate])

  useEffect(() => {
    if (!selectedStoryId && stories.length) setSelectedStoryId(stories[0].id)
    if (selectedStoryId && stories.length && !stories.some((story) => story.id === selectedStoryId)) {
      setSelectedStoryId(stories[0].id)
    }
  }, [selectedStoryId, stories])

  useEffect(() => {
    if (!selectedSessionId && sessions.length) setSelectedSessionId(sessions[0].id)
    if (selectedSessionId && sessions.length && !sessions.some((session) => session.id === selectedSessionId)) {
      setSelectedSessionId(sessions[0].id)
    }
    if (!sessions.length) setSelectedSessionId(null)
  }, [selectedSessionId, sessions])

  useEffect(() => {
    if (!selectedRuntimeTableId && runtimeTables.length) setSelectedRuntimeTableId(runtimeTables[0].id)
    if (selectedRuntimeTableId && runtimeTables.length && !runtimeTables.some((table) => table.id === selectedRuntimeTableId)) {
      setSelectedRuntimeTableId(runtimeTables[0].id)
    }
    if (!runtimeTables.length) setSelectedRuntimeTableId(null)
  }, [runtimeTables, selectedRuntimeTableId])

  useEffect(() => {
    setRuntimeDraft(draftFromTable(selectedRuntimeTable))
    setFormError('')
  }, [selectedRuntimeTable])

  useEffect(() => {
    if (!copyTargetStory) {
      if (copySessionId !== null) setCopySessionId(null)
      return
    }
    if (!copySessions.length) {
      if (copySessionId !== null) setCopySessionId(null)
      return
    }
    if (!copySessionId || !copySessions.some((session) => session.id === copySessionId)) {
      setCopySessionId(copySessions[0].id)
    }
  }, [copyTargetStory, copySessionId, copySessions])

  const invalidateTemplates = () => {
    queryClient.invalidateQueries({ queryKey: ['play-status-templates', currentWorkspace] })
    storyMountGroups.forEach((group) => {
      queryClient.invalidateQueries({ queryKey: ['play-story-status-mounts', currentWorkspace, group.story.id] })
    })
  }

  const invalidateRuntimeTables = () => {
    queryClient.invalidateQueries({ queryKey: ['play-session-status-tables', selectedSessionId] })
  }

  const upsertTemplateCache = (table: StatusTable) => {
    if (!currentWorkspace) return
    queryClient.setQueryData<StatusTable[]>(['play-status-templates', currentWorkspace], (current) => {
      if (!current) return [table]
      if (current.some((item) => item.id === table.id)) {
        return current.map((item) => (item.id === table.id ? table : item))
      }
      return [...current, table]
    })
  }

  const createTemplateMutation = useMutation({
    mutationFn: (kind: StatusKind) => {
      if (!currentWorkspace) throw new Error('workspace missing')
      return createStatusTemplate(currentWorkspace, {
        name: kind === 'scene' ? '未命名场景' : '未命名状态表',
        statusKind: kind,
        description: '',
        keyColumn: DEFAULT_KEY_COLUMN,
        valueColumn: DEFAULT_VALUE_COLUMN,
        rows: [],
        metadata: { ui: {} },
      })
    },
    onSuccess: (table) => {
      upsertTemplateCache(table)
      setSelectedTemplateId(table.id)
      setCreateTemplateOpen(false)
      invalidateTemplates()
    },
    onError: (error) => setFormError(error instanceof Error ? error.message : '新增模板失败'),
  })

  const saveTemplateMutation = useMutation({
    mutationFn: () => {
      if (!currentWorkspace || !selectedTemplate) throw new Error('template missing')
      const result = validateRows(templateDraft.rows)
      if (result.error) throw new Error(result.error)
      return updateStatusTemplate(currentWorkspace, selectedTemplate.id, {
        name: templateDraft.name.trim(),
        description: templateDraft.description,
        keyColumn: templateDraft.keyColumn.trim() || DEFAULT_KEY_COLUMN,
        valueColumn: templateDraft.valueColumn.trim() || DEFAULT_VALUE_COLUMN,
        rows: result.rows,
      })
    },
    onSuccess: (table) => {
      upsertTemplateCache(table)
      setSelectedTemplateId(table.id)
      setFormError('')
      invalidateTemplates()
    },
    onError: (error) => setFormError(error instanceof Error ? error.message : '保存模板失败'),
  })

  const deleteTemplateMutation = useMutation({
    mutationFn: () => {
      if (!currentWorkspace || !selectedTemplate) throw new Error('template missing')
      return deleteStatusTemplate(currentWorkspace, selectedTemplate.id)
    },
    onSuccess: () => {
      setDeleteTemplateOpen(false)
      setSelectedTemplateId(null)
      invalidateTemplates()
    },
    onError: (error) => setFormError(error instanceof Error ? error.message : '删除模板失败'),
  })

  const mountMutation = useMutation({
    mutationFn: (storyId: number) => {
      if (!currentWorkspace || !selectedTemplate) throw new Error('template missing')
      return mountStatusTemplate(currentWorkspace, storyId, selectedTemplate.id, selectedTemplateMounts.length * 10)
    },
    onSuccess: () => {
      setMountDialogOpen(false)
      invalidateTemplates()
    },
    onError: (error) => setFormError(error instanceof Error ? error.message : '挂载失败'),
  })

  const copyTemplateToSessionMutation = useMutation({
    mutationFn: async () => {
      if (!selectedTemplate || !copyTargetStory || !copySessionId) throw new Error('copy target missing')
      const targetSessionId = copySessionId
      const targetTables = await queryClient.fetchQuery({
        queryKey: ['play-session-status-tables', targetSessionId],
        queryFn: () => listSessionStatusTables(targetSessionId),
      })
      const nextSortOrder = targetTables.reduce((max, table) => Math.max(max, table.sortOrder), 0) + 10
      return createSessionStatusTable(targetSessionId, {
        name: uniqueStatusTableName(selectedTemplate.name, targetTables),
        statusKind: selectedTemplate.statusKind,
        description: selectedTemplate.description,
        keyColumn: selectedTemplate.keyColumn,
        valueColumn: selectedTemplate.valueColumn,
        rows: selectedTemplate.rows.map((row) => ({
          key: row.key,
          value: row.value,
          runtimeKeyLocked: row.runtimeKeyLocked,
          metadata: row.metadata ?? {},
        })),
        metadata: selectedTemplate.metadata ?? { ui: {} },
        sortOrder: nextSortOrder,
      })
    },
    onSuccess: (table) => {
      const targetSessionId = copySessionId
      setCopyTargetStory(null)
      setCopySessionId(null)
      if (targetSessionId) {
        queryClient.invalidateQueries({ queryKey: ['play-session-status-tables', targetSessionId] })
      }
      if (targetSessionId && targetSessionId === selectedSessionId) {
        setSelectedRuntimeTableId(table.id)
      }
    },
    onError: (error) => setFormError(error instanceof Error ? error.message : '复制到会话失败'),
  })

  const unmountMutation = useMutation({
    mutationFn: ({ storyId, mountId }: { storyId: number; mountId: number }) => {
      if (!currentWorkspace) throw new Error('workspace missing')
      return unmountStatusTemplate(currentWorkspace, storyId, mountId)
    },
    onSuccess: () => invalidateTemplates(),
    onError: (error) => setFormError(error instanceof Error ? error.message : '解除挂载失败'),
  })

  const createRuntimeMutation = useMutation({
    mutationFn: (kind: StatusKind) => {
      if (!selectedSessionId) throw new Error('session missing')
      const nextSortOrder = runtimeTables.reduce((max, table) => Math.max(max, table.sortOrder), 0) + 10
      return createSessionStatusTable(selectedSessionId, {
        name: kind === 'scene' ? '未命名场景' : '未命名状态表',
        statusKind: kind,
        description: '',
        keyColumn: DEFAULT_KEY_COLUMN,
        valueColumn: DEFAULT_VALUE_COLUMN,
        rows: [],
        metadata: { ui: {} },
        sortOrder: nextSortOrder,
      })
    },
    onSuccess: (table) => {
      setSelectedRuntimeTableId(table.id)
      setCreateRuntimeOpen(false)
      invalidateRuntimeTables()
    },
    onError: (error) => setFormError(error instanceof Error ? error.message : '新增状态表失败'),
  })

  const saveRuntimeMutation = useMutation({
    mutationFn: () => {
      if (!selectedSessionId || !selectedRuntimeTable) throw new Error('status table missing')
      const result = validateRows(runtimeDraft.rows)
      if (result.error) throw new Error(result.error)
      return updateSessionStatusTable(selectedSessionId, selectedRuntimeTable.id, {
        name: runtimeDraft.name.trim(),
        description: runtimeDraft.description,
        keyColumn: runtimeDraft.keyColumn.trim() || DEFAULT_KEY_COLUMN,
        valueColumn: runtimeDraft.valueColumn.trim() || DEFAULT_VALUE_COLUMN,
        rows: result.rows,
      })
    },
    onSuccess: (table) => {
      setSelectedRuntimeTableId(table.id)
      setFormError('')
      invalidateRuntimeTables()
    },
    onError: (error) => setFormError(error instanceof Error ? error.message : '保存状态表失败'),
  })

  const deleteRuntimeMutation = useMutation({
    mutationFn: () => {
      if (!selectedSessionId || !selectedRuntimeTable) throw new Error('status table missing')
      return deleteSessionStatusTable(selectedSessionId, selectedRuntimeTable.id)
    },
    onSuccess: () => {
      setDeleteRuntimeOpen(false)
      setSelectedRuntimeTableId(null)
      invalidateRuntimeTables()
    },
    onError: (error) => setFormError(error instanceof Error ? error.message : '删除状态表失败'),
  })

  const templateDeleteDisabled = !selectedTemplate || Boolean(selectedTemplateMounts.length) || deleteTemplateMutation.isPending
  const activeTemplateAction = view === 'templates'
  const activeRuntimeAction = view === 'runtime'

  return (
    <div className="min-w-0 px-5 py-7 lg:px-8">
      <header className="mb-6 grid gap-5 xl:grid-cols-[minmax(0,1fr)_auto] xl:items-end">
        <div className="space-y-4">
          <nav className="flex w-fit items-center gap-1 rounded-xl border border-slate-200 bg-white p-1 shadow-sm" aria-label="状态表视图">
            <button
              type="button"
              onClick={() => setView('templates')}
              className={`min-w-28 rounded-lg px-3 py-2 text-sm font-extrabold transition ${
                view === 'templates' ? 'bg-violet-50 text-violet-700' : 'text-slate-500 hover:bg-slate-50 hover:text-slate-900'
              }`}
            >
              模板状态表
            </button>
            <button
              type="button"
              onClick={() => setView('runtime')}
              className={`min-w-28 rounded-lg px-3 py-2 text-sm font-extrabold transition ${
                view === 'runtime' ? 'bg-violet-50 text-violet-700' : 'text-slate-500 hover:bg-slate-50 hover:text-slate-900'
              }`}
            >
              故事运行时
            </button>
          </nav>
          <div>
            <h1 className="text-3xl font-bold leading-tight text-slate-950">
              {view === 'templates' ? '模板状态表 CRUD' : '故事运行时状态表'}
            </h1>
            <p className="mt-2 text-sm leading-6 text-slate-500">
              {view === 'templates'
                ? '维护工作区级状态表模板。模板内容保存为 SQLite 文档，创建会话时复制到会话状态表。'
                : '管理某个会话中的状态表文档。运行时表只影响当前会话，不回写模板。'}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap gap-3">
          {activeTemplateAction ? (
            <>
              <button
                type="button"
                onClick={() => setDeleteTemplateOpen(true)}
                disabled={templateDeleteDisabled}
                className="inline-flex h-10 items-center gap-2 rounded-lg border border-rose-200 bg-rose-50 px-4 text-sm font-bold text-rose-700 shadow-sm disabled:cursor-not-allowed disabled:opacity-50"
              >
                <Trash2 size={16} />
                删除模板
              </button>
              <button
                type="button"
                onClick={() => setCreateTemplateOpen(true)}
                disabled={!currentWorkspace || createTemplateMutation.isPending}
                className="inline-flex h-10 items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 text-sm font-bold text-slate-700 shadow-sm transition hover:border-violet-200 hover:text-violet-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <FilePlus2 size={16} />
                新增模板
              </button>
              <button
                type="button"
                onClick={() => saveTemplateMutation.mutate()}
                disabled={!selectedTemplate || !templateDraft.name.trim() || saveTemplateMutation.isPending}
                className="inline-flex h-10 items-center gap-2 rounded-lg bg-violet-600 px-4 text-sm font-bold text-white shadow-lg shadow-violet-200 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {saveTemplateMutation.isPending ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
                保存模板
              </button>
            </>
          ) : null}
          {activeRuntimeAction ? (
            <>
              <button
                type="button"
                onClick={() => setDeleteRuntimeOpen(true)}
                disabled={!selectedRuntimeTable || deleteRuntimeMutation.isPending}
                className="inline-flex h-10 items-center gap-2 rounded-lg border border-rose-200 bg-rose-50 px-4 text-sm font-bold text-rose-700 shadow-sm disabled:cursor-not-allowed disabled:opacity-50"
              >
                <Trash2 size={16} />
                删除状态表
              </button>
              <button
                type="button"
                onClick={() => setCreateRuntimeOpen(true)}
                disabled={!selectedSessionId || createRuntimeMutation.isPending}
                className="inline-flex h-10 items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 text-sm font-bold text-slate-700 shadow-sm transition hover:border-violet-200 hover:text-violet-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <FilePlus2 size={16} />
                新增状态表
              </button>
              <button
                type="button"
                onClick={() => saveRuntimeMutation.mutate()}
                disabled={!selectedRuntimeTable || !runtimeDraft.name.trim() || saveRuntimeMutation.isPending}
                className="inline-flex h-10 items-center gap-2 rounded-lg bg-violet-600 px-4 text-sm font-bold text-white shadow-lg shadow-violet-200 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {saveRuntimeMutation.isPending ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
                保存状态表
              </button>
            </>
          ) : null}
        </div>
      </header>

      {formError ? (
        <div className="mb-4 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-semibold text-rose-700">
          {formError}
        </div>
      ) : null}

      {!currentWorkspace ? (
        <Panel>
          <div className="px-6 py-12 text-center text-sm text-slate-500">请先选择 workspace。</div>
        </Panel>
      ) : view === 'templates' ? (
        <section className="grid gap-4 xl:grid-cols-[330px_minmax(0,1fr)_330px]">
          <Panel>
            <PanelHead title="模板列表" description="每张模板都是独立状态表，状态种类只区分场景与普通状态。" />
            <div className="space-y-3 px-4 py-4">
              {templatesQuery.isLoading ? (
                <div className="py-8 text-center text-sm text-slate-400">加载模板中...</div>
              ) : templates.length ? templates.map((table) => (
                <StatusTableCard
                  key={table.id}
                  table={table}
                  active={table.id === selectedTemplateId}
                  mounted={mountedTemplateIds.has(table.id)}
                  onClick={() => setSelectedTemplateId(table.id)}
                />
              )) : (
                <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-8 text-center text-sm text-slate-500">
                  暂无模板。
                </div>
              )}
            </div>
          </Panel>

          <Panel>
            <PanelHead
              title={selectedTemplate?.name ?? '未选择模板'}
              description="模板 CRUD 面板。保存时更新模板基础信息与初始键值内容，不在这个页面实现复制到会话。"
            />
            <div className="space-y-5 px-5 py-5">
              {selectedTemplate ? (
                <>
                  <div className="grid gap-4 md:grid-cols-2">
                    <label>
                      <FieldLabel label="模板名" note="必填" />
                      <input
                        value={templateDraft.name}
                        onChange={(event) => setTemplateDraft({ ...templateDraft, name: event.target.value })}
                        className="h-10 w-full rounded-[10px] border border-slate-200 px-3 text-sm text-slate-950 outline-none transition focus:border-violet-300 focus:ring-4 focus:ring-violet-100"
                      />
                    </label>
                    <label>
                      <FieldLabel label="状态种类" note="只读" />
                      <KindField kind={selectedTemplate.statusKind} hint={statusKindLabel(selectedTemplate.statusKind)} />
                      <p className="mt-2 text-xs leading-5 text-slate-400">状态种类由后端枚举控制；创建后不可在此页面修改。</p>
                    </label>
                  </div>
                  <label className="block">
                    <FieldLabel label="描述" note="可选" />
                    <textarea
                      value={templateDraft.description}
                      onChange={(event) => setTemplateDraft({ ...templateDraft, description: event.target.value })}
                      className="min-h-24 w-full resize-none rounded-[10px] border border-slate-200 px-3 py-3 text-sm leading-6 text-slate-950 outline-none transition focus:border-violet-300 focus:ring-4 focus:ring-violet-100"
                    />
                  </label>
                  <div>
                    <h3 className="mb-3 text-sm font-bold text-slate-950">Key-Value 模板内容</h3>
                    <KvEditor draft={templateDraft} onChange={setTemplateDraft} toolbarTitle="初始键值" />
                  </div>
                  <div className="grid gap-4 border-t border-slate-100 pt-4 text-xs text-slate-500 md:grid-cols-2">
                    <p>创建时间 {formatDate(selectedTemplate.createdAt)}</p>
                    <p>更新时间 {formatDate(selectedTemplate.updatedAt)}</p>
                  </div>
                </>
              ) : (
                <div className="px-4 py-12 text-center text-sm text-slate-500">请选择或新增模板。</div>
              )}
            </div>
          </Panel>

          <Panel>
            <PanelHead title="挂载与删除" description="模板只有挂载到故事后，创建 session 时才会生成运行时副本。" />
            <div className="space-y-4 px-4 py-4">
              <div className="flex items-center justify-between gap-3">
                <h3 className="text-sm font-bold text-slate-950">故事挂载</h3>
                <button
                  type="button"
                  onClick={() => setMountDialogOpen(true)}
                  disabled={!selectedTemplate || !stories.length}
                  className="h-9 rounded-lg border border-slate-200 bg-white px-3 text-xs font-extrabold text-violet-700 transition hover:border-violet-200 hover:bg-violet-50 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  添加挂载
                </button>
              </div>
              <div className="space-y-3">
                {selectedTemplateMounts.length ? selectedTemplateMounts.map(({ story, mount }) => (
                  <article key={mount.id} className="flex items-start gap-3 rounded-xl border border-slate-200 bg-white p-3">
                    <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-violet-50 text-violet-600">
                      <TableProperties size={18} />
                    </span>
                    <div className="min-w-0 flex-1">
                      <h3 className="truncate text-sm font-bold text-slate-950">{story.title}</h3>
                      <p className="mt-1 line-clamp-2 text-sm leading-5 text-slate-500">{story.summary || '暂无摘要'}</p>
                    </div>
                    <div className="flex shrink-0 items-center gap-1">
                      <button
                        type="button"
                        aria-label={`复制模板到 ${story.title} 的会话`}
                        onClick={() => setCopyTargetStory(story)}
                        className="flex h-9 w-9 items-center justify-center rounded-lg bg-slate-50 text-slate-500 transition hover:bg-violet-50 hover:text-violet-700 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        <Copy size={16} />
                      </button>
                      <button
                        type="button"
                        aria-label="删除挂载"
                        onClick={() => unmountMutation.mutate({ storyId: story.id, mountId: mount.id })}
                        disabled={unmountMutation.isPending}
                        className="flex h-9 w-9 items-center justify-center rounded-lg bg-slate-50 text-slate-500 transition hover:bg-rose-50 hover:text-rose-700 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {unmountMutation.isPending ? <Loader2 size={16} className="animate-spin" /> : <Trash2 size={16} />}
                      </button>
                    </div>
                  </article>
                )) : (
                  <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-8 text-center text-sm text-slate-500">
                    暂无故事挂载。
                  </div>
                )}
              </div>
            </div>
          </Panel>
        </section>
      ) : (
        <section className="grid gap-4 xl:grid-cols-[330px_minmax(0,1fr)]">
          <Panel>
            <PanelHead title="故事会话" description="选择故事和会话后，查看来自模板副本和会话内新建的状态表。" />
            <div className="space-y-5 px-4 py-4">
              <label className="block">
                <FieldLabel label="故事" note="单选" />
                <select
                  value={selectedStoryId ?? ''}
                  onChange={(event) => {
                    const nextStoryId = Number(event.target.value)
                    setSelectedStoryId(Number.isFinite(nextStoryId) ? nextStoryId : null)
                    setSelectedSessionId(null)
                    setSelectedRuntimeTableId(null)
                  }}
                  className="h-10 w-full rounded-[10px] border border-slate-200 bg-white px-3 text-sm text-slate-950 outline-none transition focus:border-violet-300 focus:ring-4 focus:ring-violet-100"
                >
                  {stories.map((story) => <option key={story.id} value={story.id}>{story.title}</option>)}
                </select>
              </label>
              <label className="block">
                <FieldLabel label="会话" note="单选" />
                <select
                  value={selectedSessionId ?? ''}
                  onChange={(event) => {
                    setSelectedSessionId(event.target.value || null)
                    setSelectedRuntimeTableId(null)
                  }}
                  className="h-10 w-full rounded-[10px] border border-slate-200 bg-white px-3 text-sm text-slate-950 outline-none transition focus:border-violet-300 focus:ring-4 focus:ring-violet-100"
                >
                  {sessions.map((session) => <option key={session.id} value={session.id}>{session.title || session.id}</option>)}
                </select>
                <p className="mt-2 text-xs leading-5 text-slate-400">当前 session_id：{selectedSessionId ?? '暂无'}</p>
              </label>
              <div>
                <h3 className="mb-3 text-sm font-bold text-slate-950">运行时表</h3>
                <div className="space-y-3">
                  {runtimeTablesQuery.isLoading ? (
                    <div className="py-8 text-center text-sm text-slate-400">加载运行时表中...</div>
                  ) : runtimeTables.length ? runtimeTables.map((table) => (
                    <StatusTableCard
                      key={table.id}
                      table={table}
                      active={table.id === selectedRuntimeTableId}
                      onClick={() => setSelectedRuntimeTableId(table.id)}
                    />
                  )) : (
                    <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-8 text-center text-sm text-slate-500">
                      暂无运行时表。
                    </div>
                  )}
                </div>
              </div>
            </div>
          </Panel>

          <Panel>
            <PanelHead
              title={selectedRuntimeTable?.name ?? '未选择状态表'}
              description="会话副本 CRUD 面板。保存时只更新当前会话内的键值内容。"
            />
            <div className="space-y-5 px-5 py-5">
              {selectedRuntimeTable ? (
                <>
                  <div className="grid gap-4 md:grid-cols-2">
                    <label>
                      <FieldLabel label="状态表名" note="必填" />
                      <input
                        value={runtimeDraft.name}
                        onChange={(event) => setRuntimeDraft({ ...runtimeDraft, name: event.target.value })}
                        className="h-10 w-full rounded-[10px] border border-slate-200 px-3 text-sm text-slate-950 outline-none transition focus:border-violet-300 focus:ring-4 focus:ring-violet-100"
                      />
                    </label>
                    <label>
                      <FieldLabel label="状态种类" note="只读" />
                      <KindField kind={selectedRuntimeTable.statusKind} />
                    </label>
                  </div>
                  <div className="grid gap-4 md:grid-cols-2">
                    <label>
                      <FieldLabel label="来源" note="只读" />
                      <ReadOnlyField
                        dotClass={selectedRuntimeTable.origin === 'template_copy' ? 'bg-amber-500' : 'bg-emerald-500'}
                        title={originLabel(selectedRuntimeTable.origin)}
                        hint={originLabel(selectedRuntimeTable.origin)}
                      />
                    </label>
                    <label>
                      <FieldLabel label="源模板" note="只读" />
                      <input
                        value={selectedRuntimeTable.sourceTableId ? `${templateNameById(templates, selectedRuntimeTable.sourceTableId)} #${selectedRuntimeTable.sourceTableId}` : '无'}
                        readOnly
                        className="h-10 w-full rounded-[10px] border border-slate-200 bg-slate-50 px-3 text-sm text-slate-500 outline-none"
                      />
                    </label>
                  </div>
                  <label className="block">
                    <FieldLabel label="描述" note="可选" />
                    <textarea
                      value={runtimeDraft.description}
                      onChange={(event) => setRuntimeDraft({ ...runtimeDraft, description: event.target.value })}
                      className="min-h-24 w-full resize-none rounded-[10px] border border-slate-200 px-3 py-3 text-sm leading-6 text-slate-950 outline-none transition focus:border-violet-300 focus:ring-4 focus:ring-violet-100"
                    />
                  </label>
                  <div>
                    <h3 className="mb-3 text-sm font-bold text-slate-950">Key-Value 运行时内容</h3>
                    <KvEditor draft={runtimeDraft} onChange={setRuntimeDraft} toolbarTitle="当前键值" />
                  </div>
                  <div className="grid gap-4 border-t border-slate-100 pt-4 text-xs text-slate-500 md:grid-cols-3">
                    <p>会话 {selectedSessionLabel(selectedSession)}</p>
                    <p>创建时间 {formatDate(selectedRuntimeTable.createdAt)}</p>
                    <p>更新时间 {formatDate(selectedRuntimeTable.updatedAt)}</p>
                  </div>
                </>
              ) : (
                <div className="px-4 py-12 text-center text-sm text-slate-500">请选择或新增运行时状态表。</div>
              )}
            </div>
          </Panel>
        </section>
      )}

      {createTemplateOpen ? (
        <StatusKindCreateDialog
          pending={createTemplateMutation.isPending}
          onClose={() => setCreateTemplateOpen(false)}
          onCreate={(kind) => createTemplateMutation.mutate(kind)}
        />
      ) : null}

      {createRuntimeOpen ? (
        <StatusKindCreateDialog
          title="新增状态表"
          pending={createRuntimeMutation.isPending}
          onClose={() => setCreateRuntimeOpen(false)}
          onCreate={(kind) => createRuntimeMutation.mutate(kind)}
        />
      ) : null}

      {mountDialogOpen ? (
        <MountDialog
          stories={stories}
          selectedTemplate={selectedTemplate}
          selectedTemplateMounts={selectedTemplateMounts}
          pending={mountMutation.isPending}
          onClose={() => setMountDialogOpen(false)}
          onMount={(storyId) => mountMutation.mutate(storyId)}
        />
      ) : null}

      {copyTargetStory ? (
        <CopyTemplateToSessionDialog
          selectedTemplate={selectedTemplate}
          story={copyTargetStory}
          sessions={copySessions}
          selectedSessionId={copySessionId}
          loading={copySessionsQuery.isLoading}
          pending={copyTemplateToSessionMutation.isPending}
          onSelectSession={setCopySessionId}
          onClose={() => setCopyTargetStory(null)}
          onCopy={() => copyTemplateToSessionMutation.mutate()}
        />
      ) : null}

      {deleteTemplateOpen && selectedTemplate ? (
        <DeleteDialog
          title="删除模板"
          heading={`确认删除「${selectedTemplate.name}」？`}
          body="删除后会移除这个工作区状态表模板。这个操作不会影响已经创建的会话副本，也不会删除其它模板。"
          pending={deleteTemplateMutation.isPending}
          onClose={() => setDeleteTemplateOpen(false)}
          onDelete={() => deleteTemplateMutation.mutate()}
        />
      ) : null}

      {deleteRuntimeOpen && selectedRuntimeTable ? (
        <DeleteDialog
          title="删除状态表"
          heading={`确认删除「${selectedRuntimeTable.name}」？`}
          body="删除后会从当前会话中移除该状态表。这个操作不会回写模板，也不会影响其它会话。"
          pending={deleteRuntimeMutation.isPending}
          onClose={() => setDeleteRuntimeOpen(false)}
          onDelete={() => deleteRuntimeMutation.mutate()}
        />
      ) : null}
    </div>
  )
}

function templateNameById(templates: StatusTable[], templateId: number) {
  return templates.find((template) => template.id === templateId)?.name ?? '源模板'
}

function selectedSessionLabel(session: SessionSummary | null) {
  if (!session) return '暂无'
  return session.title || session.id
}

export function StatusTablesPage() {
  return (
    <AppShell>
      <StatusTablesContent />
    </AppShell>
  )
}
