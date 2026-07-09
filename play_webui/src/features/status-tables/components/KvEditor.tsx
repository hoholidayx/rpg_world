import { Check } from 'lucide-react'
import type { StatusRow } from '@/types/statusTables'
import type { TableDraft } from '../draft'

export function KvEditor({
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
