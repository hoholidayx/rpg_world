import { Copy, Loader2, TableProperties, Trash2 } from 'lucide-react'
import { STATUS_KIND } from '@/types/statusTables'
import { STATUS_DESCRIPTION_PLACEHOLDER, statusKindLabel } from '../constants'
import { formatDate } from '../helpers'
import type { StatusTablesController } from '../useStatusTablesController'
import { FieldLabel, KindField, Panel, PanelHead } from '../components/FormBits'
import { KvEditor } from '../components/KvEditor'
import { StatusTableCard } from '../components/StatusTableCard'

export function SystemTemplatesView({ controller }: { controller: StatusTablesController }) {
  const {
    mountedTemplateIds,
    selectedTemplate,
    selectedTemplateId,
    selectedTemplateMounts,
    setCopyTargetStoryId,
    setMountDialogOpen,
    setSelectedTemplateId,
    setTemplateDraft,
    stories,
    systemTemplates,
    templateDraft,
    templatesQuery,
    unmountMutation,
  } = controller

  return (
    <section className="grid gap-4 xl:grid-cols-[330px_minmax(0,1fr)_330px]">
      <Panel>
        <PanelHead title="系统模板列表" description="工作区级状态表模板，可挂载到多个故事。" />
        <div className="space-y-3 px-4 py-4">
          {templatesQuery.isLoading ? (
            <div className="py-8 text-center text-sm text-slate-400">加载模板中...</div>
          ) : systemTemplates.length ? systemTemplates.map((table) => (
            <StatusTableCard
              key={table.id}
              table={table}
              active={table.id === selectedTemplateId}
              mounted={mountedTemplateIds.has(table.id)}
              onClick={() => setSelectedTemplateId(table.id)}
            />
          )) : (
            <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-8 text-center text-sm text-slate-500">
              暂无系统模板。
            </div>
          )}
        </div>
      </Panel>

      <Panel>
        <PanelHead
          title={selectedTemplate?.name ?? '未选择模板'}
          description="保存时更新系统模板基础信息与初始键值内容。"
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
                <FieldLabel label="用途与更新规则" note="可选" />
                <textarea
                  value={templateDraft.description}
                  onChange={(event) => setTemplateDraft({ ...templateDraft, description: event.target.value })}
                  placeholder={STATUS_DESCRIPTION_PLACEHOLDER}
                  className="min-h-24 w-full resize-none rounded-[10px] border border-slate-200 px-3 py-3 text-sm leading-6 text-slate-950 outline-none transition focus:border-violet-300 focus:ring-4 focus:ring-violet-100"
                />
              </label>
              <div>
                <h3 className="mb-3 text-sm font-bold text-slate-950">Key-Value 模板内容</h3>
                <KvEditor draft={templateDraft} onChange={setTemplateDraft} toolbarTitle="初始键值" isScene={selectedTemplate.statusKind === STATUS_KIND.SCENE} />
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
                    onClick={() => setCopyTargetStoryId(story.id)}
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
  )
}
