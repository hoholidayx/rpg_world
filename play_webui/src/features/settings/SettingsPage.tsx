'use client'

import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import {
  AlertTriangle,
  Check,
  ChevronDown,
  Database,
  FileWarning,
  FolderOpen,
  Loader2,
  RefreshCw,
  Settings,
  ShieldCheck,
  Sparkles,
  Trash2,
} from 'lucide-react'
import { createUnindexedRuntimeDeleteToken, deleteUnindexedRuntimeItems, scanUnindexedRuntime } from '@/lib/api/ops'
import { listWorkspaces } from '@/lib/api/sessions'
import type { UnindexedRuntimeItem } from '@/types/ops'
import type { WorkspaceSummary } from '@/types/session'

type WorkspaceSwitcherProps = {
  value: string | null
  workspaces: WorkspaceSummary[]
  isLoading: boolean
  isError: boolean
  onChange: (workspace: string | null) => void
}

function itemKey(item: UnindexedRuntimeItem) {
  return [
    item.category,
    item.kind,
    item.workspaceId,
    item.storyId,
    item.sessionId,
    item.relativePath,
    item.path,
  ].join('::')
}

function categoryLabel(item: UnindexedRuntimeItem) {
  return item.category === 'status_csv' ? '未索引状态表' : '未索引运行目录'
}

function kindLabel(kind: string) {
  if (kind === 'story') return '故事目录'
  if (kind === 'session') return '会话目录'
  if (kind === 'template') return '模板 CSV'
  return kind || '未知类型'
}

function itemOwner(item: UnindexedRuntimeItem) {
  const parts = [`workspace ${item.workspaceId}`]
  if (item.storyId) parts.push(`story ${item.storyId}`)
  if (item.sessionId) parts.push(`session ${item.sessionId}`)
  return parts.join(' / ')
}

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

function WorkspaceSwitcher({ value, workspaces, isLoading, isError, onChange }: WorkspaceSwitcherProps) {
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

function SettingsHero() {
  return (
    <section className="relative overflow-hidden rounded-2xl bg-white px-8 py-7 shadow-sm">
      <div className="relative z-10">
        <p className="mb-2 text-sm font-semibold text-violet-600">设置后台</p>
        <h1 className="text-3xl font-bold leading-tight text-slate-950">工作区数据清理</h1>
        <p className="mt-3 max-w-2xl text-base leading-7 text-slate-500">扫描当前工作区未索引的运行目录与状态表 CSV，确认后通过 Ops 接口删除。</p>
      </div>
      <div className="absolute inset-y-0 right-0 hidden w-[42%] overflow-hidden md:block">
        <div className="absolute bottom-0 right-0 h-full w-full bg-gradient-to-l from-violet-100 via-indigo-50 to-transparent" />
        <div className="absolute bottom-0 right-12 h-28 w-80 rounded-[100%] bg-violet-200/70" />
        <div className="absolute bottom-2 right-28 h-20 w-72 rounded-[100%] bg-indigo-200/70" />
        <div className="absolute bottom-0 right-36 h-16 w-48 rounded-t-full bg-indigo-300/40" />
        <div className="absolute right-40 top-7 h-14 w-14 rounded-full bg-amber-100" />
        <div className="absolute bottom-8 right-24 h-16 w-8 rounded-t-full bg-indigo-700/80" />
        <div className="absolute bottom-7 right-20 h-4 w-16 rounded bg-indigo-700/80" />
      </div>
    </section>
  )
}

function StatCard({ label, value, icon: Icon }: { label: string; value: number; icon: typeof FileWarning }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white px-4 py-4 shadow-sm">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm text-slate-500">{label}</p>
        <Icon size={17} className="text-violet-500" />
      </div>
      <p className="mt-2 text-2xl font-bold text-slate-950">{value}</p>
    </div>
  )
}

function DataCleanupContainer({ workspaceId }: { workspaceId: string | null }) {
  const [items, setItems] = useState<UnindexedRuntimeItem[] | null>(null)
  const [selectedKeys, setSelectedKeys] = useState<string[]>([])
  const [confirmToken, setConfirmToken] = useState('')
  const [issuedToken, setIssuedToken] = useState('')
  const [issuedTokenItems, setIssuedTokenItems] = useState<UnindexedRuntimeItem[]>([])
  const [notice, setNotice] = useState('')

  useEffect(() => {
    setItems(null)
    setSelectedKeys([])
    setConfirmToken('')
    setIssuedToken('')
    setIssuedTokenItems([])
    setNotice('')
  }, [workspaceId])

  const selectedItems = useMemo(
    () => items?.filter((item) => selectedKeys.includes(itemKey(item))) ?? [],
    [items, selectedKeys],
  )
  const selectedItem = selectedItems.length === 1 ? selectedItems[0] : null
  const selectedKeySet = useMemo(() => new Set(selectedKeys), [selectedKeys])
  const runtimeDirectoryCount = items?.filter((item) => item.category === 'runtime_directory').length ?? 0
  const statusCsvCount = items?.filter((item) => item.category === 'status_csv').length ?? 0
  const itemKeys = useMemo(() => items?.map(itemKey) ?? [], [items])

  function clearDeleteState() {
    setConfirmToken('')
    setIssuedToken('')
    setIssuedTokenItems([])
  }

  function setSelection(nextKeys: string[]) {
    setSelectedKeys(nextKeys)
    clearDeleteState()
  }

  const scanMutation = useMutation({
    mutationFn: (targetWorkspace: string) => scanUnindexedRuntime(targetWorkspace),
    onSuccess: (data) => {
      setItems(data.items)
      setSelectedKeys([])
      setConfirmToken('')
      setIssuedToken('')
      setIssuedTokenItems([])
      setNotice(data.items.length ? '扫描完成，可从列表中多选需要处理的条目。' : '扫描完成，当前工作区没有未索引数据。')
    },
  })

  const tokenMutation = useMutation({
    mutationFn: (targets: UnindexedRuntimeItem[]) => createUnindexedRuntimeDeleteToken(targets),
    onSuccess: (data, targets) => {
      setIssuedToken(data.token)
      setIssuedTokenItems(targets)
      setConfirmToken('')
      setNotice(`确认 token 已生成，已绑定 ${targets.length} 个条目，${data.expiresInSeconds} 秒内有效。`)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: ({ targets, token }: { targets: UnindexedRuntimeItem[]; token: string }) => deleteUnindexedRuntimeItems(targets, token),
    onSuccess: () => {
      setNotice('删除完成，已重新扫描当前工作区。')
      setConfirmToken('')
      setIssuedToken('')
      setIssuedTokenItems([])
      if (workspaceId) scanMutation.mutate(workspaceId)
    },
  })

  const errorMessage = scanMutation.error?.message || tokenMutation.error?.message || deleteMutation.error?.message || ''
  const selectionLocked = tokenMutation.isPending || deleteMutation.isPending
  const deleteTargets = issuedToken ? issuedTokenItems : selectedItems

  return (
    <section className="rounded-2xl bg-white/70 p-6 shadow-sm">
      <div className="flex flex-col gap-4 border-b border-slate-200 pb-5 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <h2 className="text-xl font-bold text-slate-950">数据清理</h2>
          <p className="mt-2 text-sm leading-6 text-slate-500">当前工作区：{workspaceId || '暂无 workspace'}</p>
        </div>
        <div className="flex flex-wrap gap-3">
          <button
            type="button"
            onClick={() => workspaceId && scanMutation.mutate(workspaceId)}
            disabled={!workspaceId || scanMutation.isPending || selectionLocked}
            className="flex h-10 items-center gap-2 rounded-lg bg-violet-600 px-4 text-sm font-semibold text-white shadow-lg shadow-violet-200 transition hover:bg-violet-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {scanMutation.isPending ? <Loader2 size={16} className="animate-spin" /> : <Database size={16} />}
            开始扫描
          </button>
          <button
            type="button"
            onClick={() => workspaceId && scanMutation.mutate(workspaceId)}
            disabled={!workspaceId || scanMutation.isPending || selectionLocked}
            className="flex h-10 items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700 transition hover:border-violet-300 hover:text-violet-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <RefreshCw size={16} className={scanMutation.isPending ? 'animate-spin' : ''} />
            刷新
          </button>
        </div>
      </div>

      <div className="mt-5 grid gap-4 md:grid-cols-3">
        <StatCard label="未索引目录" value={runtimeDirectoryCount} icon={FolderOpen} />
        <StatCard label="未索引状态表" value={statusCsvCount} icon={FileWarning} />
        <StatCard label="总计" value={items?.length ?? 0} icon={ShieldCheck} />
      </div>

      {notice || errorMessage ? (
        <div className={`mt-5 rounded-xl border px-4 py-3 text-sm ${
          errorMessage ? 'border-rose-200 bg-rose-50 text-rose-700' : 'border-violet-100 bg-violet-50 text-violet-700'
        }`}>
          {errorMessage || notice}
        </div>
      ) : null}

      <div className="mt-5 grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <div className="flex flex-col gap-3 border-b border-slate-200 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h3 className="text-sm font-bold text-slate-950">未索引列表</h3>
              <p className="mt-1 text-xs text-slate-500">已选 {selectedKeys.length} 项</p>
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => setSelection(itemKeys)}
                disabled={!items?.length || selectedKeys.length === itemKeys.length || selectionLocked}
                className="h-8 rounded-lg border border-slate-200 bg-white px-3 text-xs font-semibold text-slate-600 transition hover:border-violet-300 hover:text-violet-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                全选
              </button>
              <button
                type="button"
                onClick={() => setSelection([])}
                disabled={!items?.length || selectedKeys.length === 0 || selectionLocked}
                className="h-8 rounded-lg border border-slate-200 bg-white px-3 text-xs font-semibold text-slate-600 transition hover:border-violet-300 hover:text-violet-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                取消全选
              </button>
              <button
                type="button"
                onClick={() => setSelection(itemKeys.filter((key) => !selectedKeySet.has(key)))}
                disabled={!items?.length || selectionLocked}
                className="h-8 rounded-lg border border-slate-200 bg-white px-3 text-xs font-semibold text-slate-600 transition hover:border-violet-300 hover:text-violet-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                反选
              </button>
            </div>
          </div>
          <div className="grid grid-cols-[56px_150px_240px_minmax(0,1fr)] border-b border-slate-200 bg-slate-50 px-4 py-3 text-xs font-semibold text-slate-500">
            <span>选择</span>
            <span>类型</span>
            <span>归属</span>
            <span>路径</span>
          </div>
          <div className="max-h-[520px] overflow-auto">
            {items === null ? (
              <div className="px-5 py-16 text-center text-sm text-slate-500">点击“开始扫描”查看当前工作区的未索引数据。</div>
            ) : items.length === 0 ? (
              <div className="px-5 py-16 text-center text-sm text-slate-500">没有需要清理的未索引数据。</div>
            ) : (
              items.map((item) => {
                const key = itemKey(item)
                const selected = selectedKeySet.has(key)
                return (
                  <button
                    key={key}
                    type="button"
                    aria-pressed={selected}
                    disabled={selectionLocked}
                    onClick={() => {
                      setSelection(
                        selected
                          ? selectedKeys.filter((selectedKey) => selectedKey !== key)
                          : [...selectedKeys, key],
                      )
                    }}
                    className={`grid w-full grid-cols-[56px_150px_240px_minmax(0,1fr)] items-center gap-0 border-b border-slate-100 px-4 py-3 text-left text-sm transition last:border-b-0 ${
                      selected ? 'bg-violet-50 text-violet-800' : 'bg-white text-slate-700 hover:bg-slate-50'
                    } disabled:cursor-not-allowed disabled:opacity-60`}
                  >
                    <span>
                      <span className={`flex h-5 w-5 items-center justify-center rounded-full border ${
                        selected ? 'border-violet-600 bg-violet-600 text-white' : 'border-slate-300'
                      }`}>
                        {selected ? <Check size={13} /> : null}
                      </span>
                    </span>
                    <span className="min-w-0">
                      <span className="block truncate font-semibold">{categoryLabel(item)}</span>
                      <span className="mt-0.5 block truncate text-xs text-slate-500">{kindLabel(item.kind)}</span>
                    </span>
                    <span className="truncate text-xs text-slate-500">{itemOwner(item)}</span>
                    <span className="truncate font-mono text-xs text-slate-600">{item.relativePath || item.path}</span>
                  </button>
                )
              })
            )}
          </div>
        </div>

        <aside className="space-y-4">
          <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex items-center gap-3">
              <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-violet-50 text-violet-600">
                <FileWarning size={19} />
              </span>
              <div>
                <h3 className="font-bold text-slate-950">选中条目</h3>
                <p className="text-xs text-slate-500">
                  {selectedItems.length === 0 ? '未选择' : selectedItems.length === 1 ? categoryLabel(selectedItems[0]) : `已选择 ${selectedItems.length} 项`}
                </p>
              </div>
            </div>
            {selectedItem ? (
              <dl className="mt-5 space-y-3 text-sm">
                <div>
                  <dt className="text-xs text-slate-400">类型</dt>
                  <dd className="mt-1 font-medium text-slate-800">{kindLabel(selectedItem.kind)}</dd>
                </div>
                <div>
                  <dt className="text-xs text-slate-400">归属</dt>
                  <dd className="mt-1 break-words font-medium text-slate-800">{itemOwner(selectedItem)}</dd>
                </div>
                <div>
                  <dt className="text-xs text-slate-400">相对路径</dt>
                  <dd className="mt-1 break-words font-mono text-xs text-slate-700">{selectedItem.relativePath || '无'}</dd>
                </div>
                <div>
                  <dt className="text-xs text-slate-400">绝对路径</dt>
                  <dd className="mt-1 break-words font-mono text-xs text-slate-500">{selectedItem.path}</dd>
                </div>
              </dl>
            ) : (
              <p className="mt-5 text-sm leading-6 text-slate-500">
                {selectedItems.length > 1 ? '已多选条目。右侧 token 会绑定当前选择的全部条目。' : '扫描后从列表中选择一个或多个条目。'}
              </p>
            )}
          </section>

          <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex items-center gap-3">
              <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-rose-50 text-rose-600">
                <AlertTriangle size={19} />
              </span>
              <div>
                <h3 className="font-bold text-slate-950">二次确认删除</h3>
                <p className="text-xs text-slate-500">Token 绑定当前选中的全部条目。</p>
              </div>
            </div>
            <button
              type="button"
              onClick={() => selectedItems.length > 0 && tokenMutation.mutate(selectedItems)}
              disabled={selectedItems.length === 0 || tokenMutation.isPending || deleteMutation.isPending}
              className="mt-5 flex h-10 w-full items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white text-sm font-semibold text-slate-700 transition hover:border-violet-300 hover:text-violet-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {tokenMutation.isPending ? <Loader2 size={16} className="animate-spin" /> : <ShieldCheck size={16} />}
              申请删除 token（{selectedItems.length}）
            </button>
            {issuedToken ? (
              <div className="mt-4 rounded-lg border border-violet-100 bg-violet-50 p-3">
                <p className="text-xs font-semibold text-violet-700">X-Delete-Confirm-Token</p>
                <p className="mt-1 text-xs text-violet-700">已绑定 {issuedTokenItems.length} 个条目</p>
                <p className="mt-2 break-all font-mono text-xs text-violet-900">{issuedToken}</p>
              </div>
            ) : null}
            <label className="mt-4 block text-xs font-semibold text-slate-500" htmlFor="delete-token">
              粘贴一次性确认 token
            </label>
            <input
              id="delete-token"
              value={confirmToken}
              onChange={(event) => setConfirmToken(event.target.value)}
              placeholder="X-Delete-Confirm-Token"
              className="mt-2 h-10 w-full rounded-lg border border-slate-200 bg-white px-3 font-mono text-sm text-slate-900 outline-none transition placeholder:text-slate-400 focus:border-violet-400 focus:ring-4 focus:ring-violet-100"
            />
            <button
              type="button"
              onClick={() => deleteTargets.length > 0 && deleteMutation.mutate({ targets: deleteTargets, token: confirmToken })}
              disabled={deleteTargets.length === 0 || !confirmToken.trim() || deleteMutation.isPending}
              className="mt-4 flex h-10 w-full items-center justify-center gap-2 rounded-lg bg-rose-600 text-sm font-semibold text-white shadow-lg shadow-rose-100 transition hover:bg-rose-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {deleteMutation.isPending ? <Loader2 size={16} className="animate-spin" /> : <Trash2 size={16} />}
              执行运维删除（{deleteTargets.length}）
            </button>
          </section>
        </aside>
      </div>
    </section>
  )
}

export function SettingsPage() {
  const [currentWorkspace, setCurrentWorkspace] = useState<string | null>(null)
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
        <div className="flex items-center gap-3 rounded-full px-2 py-1 text-sm font-medium text-slate-900">
          <span className="flex h-10 w-10 items-center justify-center rounded-full bg-indigo-100 text-indigo-700">P</span>
          <span className="hidden sm:inline">Player One</span>
        </div>
      </header>

      <div className="grid min-h-[calc(100vh-72px)] lg:grid-cols-[296px_minmax(0,1fr)]">
        <aside className="hidden border-r border-slate-200 bg-white/70 px-6 py-9 lg:flex lg:flex-col lg:justify-between">
          <nav className="space-y-3">
            <div className="flex items-center gap-4 rounded-xl bg-violet-50 px-5 py-4 text-base font-medium text-violet-700 shadow-sm">
              <Settings size={22} />
              数据清理
            </div>
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
            <SettingsHero />
            <DataCleanupContainer workspaceId={currentWorkspace} />
          </div>
        </div>
      </div>
    </main>
  )
}
