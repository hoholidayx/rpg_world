import { Check } from 'lucide-react'
import {
  STATUS_UPDATE_FREQUENCY,
  type StatusRow,
  type StatusUpdateFrequency,
} from '@/types/statusTables'
import type { TableDraft } from '../draft'

export function KvEditor({
  draft,
  onChange,
  toolbarTitle,
  isScene = false,
}: {
  draft: TableDraft
  onChange: (draft: TableDraft) => void
  toolbarTitle: string
  isScene?: boolean
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
      rows: [...draft.rows, {
        key: '',
        value: '',
        runtimeKeyLocked: false,
        metadata: {},
        updateFrequency: STATUS_UPDATE_FREQUENCY.REALTIME,
        updateRule: '',
        deferredIntervalTurns: null,
      }],
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
        <div className="min-w-[980px]">
          <div className="grid grid-cols-[170px_minmax(180px,1fr)_150px_minmax(220px,1fr)_110px_60px] items-center gap-3 border-b border-slate-100 bg-slate-50 px-3 py-3 text-xs font-extrabold text-slate-600">
            <span>Key</span>
            <span>Value</span>
            <span>更新频率</span>
            <span>事件规则 / 延迟周期</span>
            <span>运行时锁定 key</span>
            <span />
          </div>
          {draft.rows.length ? draft.rows.map((row, index) => (
            <div key={index} className="grid grid-cols-[170px_minmax(180px,1fr)_150px_minmax(220px,1fr)_110px_60px] items-center gap-3 border-b border-slate-100 bg-white px-3 py-3 last:border-b-0">
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
              <select
                value={isScene ? STATUS_UPDATE_FREQUENCY.REALTIME : row.updateFrequency}
                disabled={isScene}
                onChange={(event) => {
                  const updateFrequency = event.target.value as StatusUpdateFrequency
                  updateRow(index, {
                    updateFrequency,
                    updateRule: updateFrequency === STATUS_UPDATE_FREQUENCY.EVENT_DRIVEN ? row.updateRule : '',
                    deferredIntervalTurns: updateFrequency === STATUS_UPDATE_FREQUENCY.DEFERRED
                      ? row.deferredIntervalTurns
                      : null,
                  })
                }}
                className="h-9 rounded-lg border border-slate-200 bg-white px-2 text-sm text-slate-950 outline-none disabled:bg-slate-100"
              >
                <option value={STATUS_UPDATE_FREQUENCY.REALTIME}>实时</option>
                <option value={STATUS_UPDATE_FREQUENCY.EVENT_DRIVEN}>事件驱动</option>
                <option value={STATUS_UPDATE_FREQUENCY.DEFERRED}>延迟归纳</option>
                <option value={STATUS_UPDATE_FREQUENCY.MANUAL}>仅手动</option>
              </select>
              {row.updateFrequency === STATUS_UPDATE_FREQUENCY.EVENT_DRIVEN && !isScene ? (
                <input
                  value={row.updateRule}
                  placeholder="明确描述触发事件"
                  onChange={(event) => updateRow(index, { updateRule: event.target.value })}
                  className="h-9 min-w-0 rounded-lg border border-slate-200 px-3 text-sm text-slate-950 outline-none"
                />
              ) : row.updateFrequency === STATUS_UPDATE_FREQUENCY.DEFERRED && !isScene ? (
                <input
                  type="number"
                  min={1}
                  step={1}
                  value={row.deferredIntervalTurns ?? ''}
                  placeholder="留空使用全局默认周期"
                  onChange={(event) => updateRow(index, {
                    deferredIntervalTurns: event.target.value ? Number(event.target.value) : null,
                  })}
                  className="h-9 min-w-0 rounded-lg border border-slate-200 px-3 text-sm text-slate-950 outline-none"
                />
              ) : (
                <span className="text-xs text-slate-400">
                  {isScene ? '场景字段固定实时' : row.updateFrequency === STATUS_UPDATE_FREQUENCY.MANUAL ? 'Agent 不自动更新' : '相关 turn 检查'}
                </span>
              )}
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
        频率约束会在工具层校验；事件驱动字段必须填写明确规则。勾选运行时锁定后，LLM 不能删除或重命名 key。
      </p>
    </div>
  )
}
