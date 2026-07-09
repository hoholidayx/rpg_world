import { useState } from 'react'
import { Copy, FilePlus2, Loader2 } from 'lucide-react'
import { ConfirmDialog, Dialog } from '@/components/common/Dialog'
import { StoryMountDialog } from '@/components/common/StoryMountDialog'
import type { CharacterCard } from '@/types/characters'
import type { SessionSummary } from '@/types/session'
import type { StorySummary } from '@/types/story'
import { STATUS_KIND, type StatusKind, type StatusTable } from '@/types/statusTables'
import type { StatusTablesController } from '../useStatusTablesController'
import { FieldLabel } from './FormBits'

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
  const [kind, setKind] = useState<StatusKind>(STATUS_KIND.NORMAL)

  return (
    <Dialog title={title} onClose={onClose} size="xl">
      <div className="space-y-5 px-6 py-5">
        <label>
          <FieldLabel label="状态种类" note="创建后只读" />
          <select
            value={kind}
            onChange={(event) => setKind(event.target.value as StatusKind)}
            className="h-10 w-full rounded-[10px] border border-slate-200 bg-white px-3 text-sm text-slate-950 outline-none transition focus:border-violet-300 focus:ring-4 focus:ring-violet-100"
          >
            <option value={STATUS_KIND.NORMAL}>普通状态</option>
            <option value={STATUS_KIND.SCENE}>场景</option>
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
    </Dialog>
  )
}

function StoryStatusKindCreateDialog({
  characters,
  loadingCharacters,
  pending,
  onClose,
  onCreate,
}: {
  characters: CharacterCard[]
  loadingCharacters: boolean
  pending: boolean
  onClose: () => void
  onCreate: (kind: StatusKind, characterMountId: number | null) => void
}) {
  const [kind, setKind] = useState<StatusKind>(STATUS_KIND.NORMAL)
  const [characterMountId, setCharacterMountId] = useState<number | null>(null)

  return (
    <Dialog title="新增故事模板" onClose={onClose} size="xl">
      <div className="space-y-5 px-6 py-5">
        <label>
          <FieldLabel label="状态种类" note="创建后只读" />
          <select
            value={kind}
            onChange={(event) => setKind(event.target.value as StatusKind)}
            className="h-10 w-full rounded-[10px] border border-slate-200 bg-white px-3 text-sm text-slate-950 outline-none transition focus:border-violet-300 focus:ring-4 focus:ring-violet-100"
          >
            <option value={STATUS_KIND.NORMAL}>普通状态</option>
            <option value={STATUS_KIND.SCENE}>场景</option>
          </select>
        </label>
        <label>
          <FieldLabel label="绑定角色" note="可选" />
          <select
            value={characterMountId ?? ''}
            onChange={(event) => {
              const value = event.target.value
              setCharacterMountId(value ? Number(value) : null)
            }}
            disabled={loadingCharacters}
            className="h-10 w-full rounded-[10px] border border-slate-200 bg-white px-3 text-sm text-slate-950 outline-none transition focus:border-violet-300 focus:ring-4 focus:ring-violet-100 disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-slate-400"
          >
            <option value="">无绑定</option>
            {characters.map((character) => (
              <option key={character.mountId ?? character.id} value={character.mountId ?? ''}>
                {character.name}
              </option>
            ))}
          </select>
        </label>
      </div>
      <footer className="flex justify-end gap-3 border-t border-slate-100 px-6 py-4">
        <button type="button" onClick={onClose} className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-bold text-slate-600">
          取消
        </button>
        <button
          type="button"
          onClick={() => onCreate(kind, characterMountId)}
          disabled={pending}
          className="inline-flex items-center gap-2 rounded-lg bg-violet-600 px-4 py-2 text-sm font-bold text-white shadow-lg shadow-violet-200 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {pending ? <Loader2 size={16} className="animate-spin" /> : <FilePlus2 size={16} />}
          创建
        </button>
      </footer>
    </Dialog>
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
    <Dialog title="复制到会话" onClose={onClose} size="xl">
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
    </Dialog>
  )
}

export function StatusTableDialogs({ controller }: { controller: StatusTablesController }) {
  const {
    copySessionId,
    copySessions,
    copySessionsQuery,
    copyTargetStory,
    copyTemplateToSessionMutation,
    createRuntimeMutation,
    createRuntimeOpen,
    createStoryTemplateMutation,
    createStoryTemplateOpen,
    createTemplateMutation,
    createTemplateOpen,
    deleteRuntimeMutation,
    deleteRuntimeOpen,
    deleteStoryTemplateMutation,
    deleteStoryTemplateOpen,
    deleteTemplateMutation,
    deleteTemplateOpen,
    mountDialogOpen,
    mountMutation,
    selectedRuntimeTable,
    selectedStoryTemplate,
    selectedTemplate,
    selectedTemplateMountedStoryIds,
    setCopySessionId,
    setCopyTargetStoryId,
    setCreateRuntimeOpen,
    setCreateStoryTemplateOpen,
    setCreateTemplateOpen,
    setDeleteRuntimeOpen,
    setDeleteStoryTemplateOpen,
    setDeleteTemplateOpen,
    setMountDialogOpen,
    stories,
    storyCharacters,
    storyCharactersQuery,
  } = controller

  return (
    <>
      {createTemplateOpen ? (
        <StatusKindCreateDialog
          pending={createTemplateMutation.isPending}
          onClose={() => setCreateTemplateOpen(false)}
          onCreate={(kind) => createTemplateMutation.mutate(kind)}
        />
      ) : null}

      {createStoryTemplateOpen ? (
        <StoryStatusKindCreateDialog
          characters={storyCharacters}
          loadingCharacters={storyCharactersQuery.isLoading}
          pending={createStoryTemplateMutation.isPending}
          onClose={() => setCreateStoryTemplateOpen(false)}
          onCreate={(kind, characterMountId) => createStoryTemplateMutation.mutate({ kind, characterMountId })}
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
        <StoryMountDialog
          stories={stories}
          description={selectedTemplate ? `将「${selectedTemplate.name}」添加到故事。` : '请先选择一个状态表模板。'}
          mountedStoryIds={selectedTemplateMountedStoryIds}
          pending={mountMutation.isPending}
          disabled={!selectedTemplate}
          footerNote="添加后右侧会显示当前模板的故事挂载。"
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
          onClose={() => setCopyTargetStoryId(null)}
          onCopy={() => copyTemplateToSessionMutation.mutate()}
        />
      ) : null}

      {deleteTemplateOpen && selectedTemplate ? (
        <ConfirmDialog
          title="删除模板"
          heading={`确认删除「${selectedTemplate.name}」？`}
          body="删除后会移除这个工作区状态表模板。这个操作不会影响已经创建的会话副本，也不会删除其它模板。"
          pending={deleteTemplateMutation.isPending}
          onClose={() => setDeleteTemplateOpen(false)}
          onConfirm={() => deleteTemplateMutation.mutate()}
        />
      ) : null}

      {deleteStoryTemplateOpen && selectedStoryTemplate ? (
        <ConfirmDialog
          title="删除故事模板"
          heading={`确认删除「${selectedStoryTemplate.name}」？`}
          body="删除后会移除这个故事状态模板及其挂载。这个操作不会影响已经创建的会话副本。"
          pending={deleteStoryTemplateMutation.isPending}
          onClose={() => setDeleteStoryTemplateOpen(false)}
          onConfirm={() => deleteStoryTemplateMutation.mutate()}
        />
      ) : null}

      {deleteRuntimeOpen && selectedRuntimeTable ? (
        <ConfirmDialog
          title="删除状态表"
          heading={`确认删除「${selectedRuntimeTable.name}」？`}
          body="删除后会从当前会话中移除该状态表。这个操作不会回写模板，也不会影响其它会话。"
          pending={deleteRuntimeMutation.isPending}
          onClose={() => setDeleteRuntimeOpen(false)}
          onConfirm={() => deleteRuntimeMutation.mutate()}
        />
      ) : null}
    </>
  )
}
