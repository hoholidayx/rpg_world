import { FilePlus2, Loader2, Save, Trash2 } from 'lucide-react'
import { STATUS_TABLE_VIEW } from '../constants'
import type { StatusTablesController } from '../useStatusTablesController'

export function StatusTablesHeader({ controller }: { controller: StatusTablesController }) {
  const {
    currentWorkspace,
    view,
    setView,
    activeRuntimeAction,
    activeStoryTemplateAction,
    activeTemplateAction,
    createRuntimeMutation,
    createStoryTemplateMutation,
    createTemplateMutation,
    deleteRuntimeMutation,
    deleteStoryTemplateMutation,
    saveRuntimeMutation,
    saveStoryTemplateMutation,
    saveTemplateMutation,
    selectedRuntimeTable,
    selectedSessionId,
    selectedStoryTemplate,
    selectedStoryId,
    selectedStoryMount,
    selectedTemplate,
    storyTemplateDraft,
    storyTemplateOwned,
    templateDeleteDisabled,
    templateDraft,
    runtimeDraft,
    unmountMutation,
    setCreateRuntimeOpen,
    setCreateStoryTemplateOpen,
    setCreateTemplateOpen,
    setDeleteRuntimeOpen,
    setDeleteStoryTemplateOpen,
    setDeleteTemplateOpen,
  } = controller

  return (
    <header className="mb-6 grid gap-5 xl:grid-cols-[minmax(0,1fr)_auto] xl:items-end">
      <div className="space-y-4">
        <nav className="flex w-fit items-center gap-1 rounded-xl border border-slate-200 bg-white p-1 shadow-sm" aria-label="状态表视图">
          <button
            type="button"
            onClick={() => setView(STATUS_TABLE_VIEW.SYSTEM)}
            className={`min-w-28 rounded-lg px-3 py-2 text-sm font-extrabold transition ${
              view === STATUS_TABLE_VIEW.SYSTEM ? 'bg-violet-50 text-violet-700' : 'text-slate-500 hover:bg-slate-50 hover:text-slate-900'
            }`}
          >
            系统模板
          </button>
          <button
            type="button"
            onClick={() => setView(STATUS_TABLE_VIEW.STORY)}
            className={`min-w-28 rounded-lg px-3 py-2 text-sm font-extrabold transition ${
              view === STATUS_TABLE_VIEW.STORY ? 'bg-violet-50 text-violet-700' : 'text-slate-500 hover:bg-slate-50 hover:text-slate-900'
            }`}
          >
            故事状态模板
          </button>
          <button
            type="button"
            onClick={() => setView(STATUS_TABLE_VIEW.RUNTIME)}
            className={`min-w-28 rounded-lg px-3 py-2 text-sm font-extrabold transition ${
              view === STATUS_TABLE_VIEW.RUNTIME ? 'bg-violet-50 text-violet-700' : 'text-slate-500 hover:bg-slate-50 hover:text-slate-900'
            }`}
          >
            故事运行时
          </button>
        </nav>
        <div>
          <h1 className="text-3xl font-bold leading-tight text-slate-950">
            {view === STATUS_TABLE_VIEW.SYSTEM ? '系统模板' : view === STATUS_TABLE_VIEW.STORY ? '故事状态模板' : '故事运行时状态表'}
          </h1>
          <p className="mt-2 text-sm leading-6 text-slate-500">
            {view === STATUS_TABLE_VIEW.SYSTEM
              ? '维护工作区级状态表模板。模板内容保存为 SQLite 文档，可挂载到多个故事。'
              : view === STATUS_TABLE_VIEW.STORY
                ? '管理当前故事已挂载的状态表模板，并可把单张状态表绑定到故事角色。'
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
        {activeStoryTemplateAction ? (
          <>
            {storyTemplateOwned ? (
              <button
                type="button"
                onClick={() => setDeleteStoryTemplateOpen(true)}
                disabled={!selectedStoryMount || deleteStoryTemplateMutation.isPending}
                className="inline-flex h-10 items-center gap-2 rounded-lg border border-rose-200 bg-rose-50 px-4 text-sm font-bold text-rose-700 shadow-sm disabled:cursor-not-allowed disabled:opacity-50"
              >
                <Trash2 size={16} />
                删除模板
              </button>
            ) : (
              <button
                type="button"
                onClick={() => {
                  if (selectedStoryId && selectedStoryMount) {
                    unmountMutation.mutate({ storyId: selectedStoryId, mountId: selectedStoryMount.id })
                  }
                }}
                disabled={!selectedStoryMount || unmountMutation.isPending}
                className="inline-flex h-10 items-center gap-2 rounded-lg border border-rose-200 bg-rose-50 px-4 text-sm font-bold text-rose-700 shadow-sm disabled:cursor-not-allowed disabled:opacity-50"
              >
                <Trash2 size={16} />
                解除挂载
              </button>
            )}
            <button
              type="button"
              onClick={() => setCreateStoryTemplateOpen(true)}
              disabled={!selectedStoryId || createStoryTemplateMutation.isPending}
              className="inline-flex h-10 items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 text-sm font-bold text-slate-700 shadow-sm transition hover:border-violet-200 hover:text-violet-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <FilePlus2 size={16} />
              新增模板
            </button>
            <button
              type="button"
              onClick={() => saveStoryTemplateMutation.mutate()}
              disabled={!selectedStoryTemplate || !storyTemplateDraft.name.trim() || saveStoryTemplateMutation.isPending}
              className="inline-flex h-10 items-center gap-2 rounded-lg bg-violet-600 px-4 text-sm font-bold text-white shadow-lg shadow-violet-200 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {saveStoryTemplateMutation.isPending ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
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
  )
}
