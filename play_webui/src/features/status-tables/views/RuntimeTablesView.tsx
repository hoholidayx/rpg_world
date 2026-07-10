import { STATUS_ORIGIN } from '@/types/statusTables'
import { STATUS_DESCRIPTION_PLACEHOLDER, originLabel } from '../constants'
import { formatDate, selectedSessionLabel, templateNameById } from '../helpers'
import type { StatusTablesController } from '../useStatusTablesController'
import { FieldLabel, KindField, Panel, PanelHead, ReadOnlyField } from '../components/FormBits'
import { KvEditor } from '../components/KvEditor'
import { StatusTableCard } from '../components/StatusTableCard'

export function RuntimeTablesView({ controller }: { controller: StatusTablesController }) {
  const {
    runtimeDraft,
    runtimeTables,
    runtimeTablesQuery,
    selectedRuntimeTable,
    selectedRuntimeTableId,
    selectedSession,
    selectedSessionId,
    selectedStoryId,
    sessions,
    setRuntimeDraft,
    setSelectedRuntimeTableId,
    setSelectedSessionId,
    setSelectedStoryId,
    stories,
    templates,
  } = controller

  return (
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
                    dotClass={selectedRuntimeTable.origin === STATUS_ORIGIN.TEMPLATE_COPY ? 'bg-amber-500' : 'bg-emerald-500'}
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
                <FieldLabel label="用途与更新规则" note="可选" />
                <textarea
                  value={runtimeDraft.description}
                  onChange={(event) => setRuntimeDraft({ ...runtimeDraft, description: event.target.value })}
                  placeholder={STATUS_DESCRIPTION_PLACEHOLDER}
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
  )
}
