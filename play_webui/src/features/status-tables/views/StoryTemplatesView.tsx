import { STORY_STATUS_MOUNT_ORIGIN } from '@/types/statusTables'
import { statusKindLabel, storyMountOriginLabel } from '../constants'
import { characterLabelByMountId, formatDate } from '../helpers'
import type { StatusTablesController } from '../useStatusTablesController'
import { Chip, FieldLabel, KindField, Panel, PanelHead, ReadOnlyField } from '../components/FormBits'
import { KvEditor } from '../components/KvEditor'
import { StatusTableCard } from '../components/StatusTableCard'

export function StoryTemplatesView({ controller }: { controller: StatusTablesController }) {
  const {
    selectedStory,
    selectedStoryId,
    selectedStoryMount,
    selectedStoryMountId,
    selectedStoryMounts,
    selectedStoryTemplate,
    setSelectedRuntimeTableId,
    setSelectedSessionId,
    setSelectedStoryId,
    setSelectedStoryMountId,
    setStoryTemplateDraft,
    stories,
    storyCharacters,
    storyCharactersQuery,
    storyMountQueries,
    storyTemplateDraft,
    templates,
    updateStoryMountMutation,
  } = controller

  return (
    <section className="grid gap-4 xl:grid-cols-[330px_minmax(0,1fr)]">
      <Panel>
        <PanelHead title="故事模板" description="选择故事后管理已挂载的状态表模板。" />
        <div className="space-y-5 px-4 py-4">
          <label className="block">
            <FieldLabel label="故事" note="单选" />
            <select
              value={selectedStoryId ?? ''}
              onChange={(event) => {
                const nextStoryId = Number(event.target.value)
                setSelectedStoryId(Number.isFinite(nextStoryId) ? nextStoryId : null)
                setSelectedStoryMountId(null)
                setSelectedSessionId(null)
                setSelectedRuntimeTableId(null)
              }}
              className="h-10 w-full rounded-[10px] border border-slate-200 bg-white px-3 text-sm text-slate-950 outline-none transition focus:border-violet-300 focus:ring-4 focus:ring-violet-100"
            >
              {stories.map((story) => <option key={story.id} value={story.id}>{story.title}</option>)}
            </select>
          </label>
          <div>
            <h3 className="mb-3 text-sm font-bold text-slate-950">故事状态模板</h3>
            <div className="space-y-3">
              {storyMountQueries.some((query) => query.isLoading) ? (
                <div className="py-8 text-center text-sm text-slate-400">加载故事模板中...</div>
              ) : selectedStoryMounts.length ? selectedStoryMounts.map((mount) => {
                const table = templates.find((item) => item.id === mount.statusTableId)
                if (!table) return null
                return (
                  <StatusTableCard
                    key={mount.id}
                    table={table}
                    active={mount.id === selectedStoryMountId}
                    extraChips={(
                      <>
                        <Chip tone={mount.mountOrigin === STORY_STATUS_MOUNT_ORIGIN.STORY_TEMPLATE ? 'green' : 'amber'}>
                          {storyMountOriginLabel(mount.mountOrigin)}
                        </Chip>
                        <Chip tone={mount.characterMountId ? 'sky' : 'gray'}>
                          {characterLabelByMountId(storyCharacters, mount.characterMountId)}
                        </Chip>
                      </>
                    )}
                    onClick={() => setSelectedStoryMountId(mount.id)}
                  />
                )
              }) : (
                <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-8 text-center text-sm text-slate-500">
                  暂无故事状态模板。
                </div>
              )}
            </div>
          </div>
        </div>
      </Panel>

      <Panel>
        <PanelHead
          title={selectedStoryTemplate?.name ?? '未选择模板'}
          description={selectedStory ? `${selectedStory.title} 的状态模板与角色绑定。` : '请选择故事。'}
        />
        <div className="space-y-5 px-5 py-5">
          {selectedStoryTemplate && selectedStoryMount ? (
            <>
              <div className="grid gap-4 md:grid-cols-2">
                <label>
                  <FieldLabel label="模板名" note="必填" />
                  <input
                    value={storyTemplateDraft.name}
                    onChange={(event) => setStoryTemplateDraft({ ...storyTemplateDraft, name: event.target.value })}
                    className="h-10 w-full rounded-[10px] border border-slate-200 px-3 text-sm text-slate-950 outline-none transition focus:border-violet-300 focus:ring-4 focus:ring-violet-100"
                  />
                </label>
                <label>
                  <FieldLabel label="状态种类" note="只读" />
                  <KindField kind={selectedStoryTemplate.statusKind} hint={statusKindLabel(selectedStoryTemplate.statusKind)} />
                </label>
              </div>
              <div className="grid gap-4 md:grid-cols-2">
                <label>
                  <FieldLabel label="来源" note="只读" />
                  <ReadOnlyField
                    dotClass={selectedStoryMount.mountOrigin === STORY_STATUS_MOUNT_ORIGIN.STORY_TEMPLATE ? 'bg-emerald-500' : 'bg-amber-500'}
                    title={storyMountOriginLabel(selectedStoryMount.mountOrigin)}
                    hint={`挂载 #${selectedStoryMount.id}`}
                  />
                </label>
                <label>
                  <FieldLabel label="绑定角色" note="可选" />
                  <select
                    value={selectedStoryMount.characterMountId ?? ''}
                    onChange={(event) => {
                      const value = event.target.value
                      updateStoryMountMutation.mutate(value ? Number(value) : null)
                    }}
                    disabled={storyCharactersQuery.isLoading || updateStoryMountMutation.isPending}
                    className="h-10 w-full rounded-[10px] border border-slate-200 bg-white px-3 text-sm text-slate-950 outline-none transition focus:border-violet-300 focus:ring-4 focus:ring-violet-100 disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-slate-400"
                  >
                    <option value="">无绑定</option>
                    {storyCharacters.map((character) => (
                      <option key={character.mountId ?? character.id} value={character.mountId ?? ''}>
                        {character.name}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <label className="block">
                <FieldLabel label="描述" note="可选" />
                <textarea
                  value={storyTemplateDraft.description}
                  onChange={(event) => setStoryTemplateDraft({ ...storyTemplateDraft, description: event.target.value })}
                  className="min-h-24 w-full resize-none rounded-[10px] border border-slate-200 px-3 py-3 text-sm leading-6 text-slate-950 outline-none transition focus:border-violet-300 focus:ring-4 focus:ring-violet-100"
                />
              </label>
              <div>
                <h3 className="mb-3 text-sm font-bold text-slate-950">Key-Value 模板内容</h3>
                <KvEditor draft={storyTemplateDraft} onChange={setStoryTemplateDraft} toolbarTitle="初始键值" />
              </div>
              <div className="grid gap-4 border-t border-slate-100 pt-4 text-xs text-slate-500 md:grid-cols-3">
                <p>角色 {characterLabelByMountId(storyCharacters, selectedStoryMount.characterMountId)}</p>
                <p>创建时间 {formatDate(selectedStoryTemplate.createdAt)}</p>
                <p>更新时间 {formatDate(selectedStoryTemplate.updatedAt)}</p>
              </div>
            </>
          ) : (
            <div className="px-4 py-12 text-center text-sm text-slate-500">请选择或新增故事状态模板。</div>
          )}
        </div>
      </Panel>
    </section>
  )
}
