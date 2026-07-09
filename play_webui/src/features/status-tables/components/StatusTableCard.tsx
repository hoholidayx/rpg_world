import type { ReactNode } from 'react'
import { STATUS_KIND, STATUS_ORIGIN, type StatusTable } from '@/types/statusTables'
import { originLabel, statusKindLabel } from '../constants'
import { Chip } from './FormBits'

export function StatusTableCard({
  table,
  active,
  mounted,
  extraChips,
  onClick,
}: {
  table: StatusTable
  active: boolean
  mounted?: boolean
  extraChips?: ReactNode
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
        <Chip tone={table.statusKind === STATUS_KIND.SCENE ? 'sky' : 'violet'}>{statusKindLabel(table.statusKind)}</Chip>
      </div>
      <p className="mt-2 line-clamp-2 min-h-10 text-sm leading-5 text-slate-500">
        {table.description || (table.statusKind === STATUS_KIND.SCENE ? '场景状态表。' : '普通状态表进入结构化上下文。')}
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        {typeof mounted === 'boolean' ? <Chip tone={mounted ? 'green' : 'gray'}>{mounted ? '已挂载' : '未挂载'}</Chip> : null}
        {table.origin ? <Chip tone={table.origin === STATUS_ORIGIN.TEMPLATE_COPY ? 'amber' : 'green'}>{originLabel(table.origin)}</Chip> : null}
        {extraChips}
        <Chip tone="gray">{table.rows.length} key</Chip>
      </div>
    </button>
  )
}
