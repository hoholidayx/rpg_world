import type { ReactNode } from 'react'
import { STATUS_KIND, type StatusKind } from '@/types/statusTables'
import { statusKindHint, statusKindLabel } from '../constants'

export type ChipTone = 'violet' | 'green' | 'amber' | 'sky' | 'gray'

export function Chip({ children, tone = 'violet' }: { children: ReactNode; tone?: ChipTone }) {
  const classes: Record<ChipTone, string> = {
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

export function KindField({ kind, hint }: { kind: StatusKind; hint?: string }) {
  return (
    <div className="grid min-h-10 grid-cols-[10px_auto_minmax(0,1fr)] items-center gap-2 rounded-[10px] border border-slate-200 bg-slate-50 px-3">
      <span className={`h-2.5 w-2.5 rounded-full ${kind === STATUS_KIND.SCENE ? 'bg-sky-600' : 'bg-violet-600'}`} />
      <strong className="text-sm text-slate-950">{statusKindLabel(kind)}</strong>
      <em className="truncate text-right text-xs not-italic text-slate-500">{hint ?? statusKindHint(kind)}</em>
    </div>
  )
}

export function ReadOnlyField({ dotClass, title, hint }: { dotClass: string; title: string; hint: string }) {
  return (
    <div className="grid min-h-10 grid-cols-[10px_auto_minmax(0,1fr)] items-center gap-2 rounded-[10px] border border-slate-200 bg-slate-50 px-3">
      <span className={`h-2.5 w-2.5 rounded-full ${dotClass}`} />
      <strong className="text-sm text-slate-950">{title}</strong>
      <em className="truncate text-right text-xs not-italic text-slate-500">{hint}</em>
    </div>
  )
}

export function FieldLabel({ label, note }: { label: string; note?: string }) {
  return (
    <div className="mb-2 flex items-center justify-between text-sm font-extrabold text-slate-950">
      <span>{label}</span>
      {note ? <span className="text-xs font-bold text-slate-400">{note}</span> : null}
    </div>
  )
}

export function Panel({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <section className={`overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm ${className}`}>
      {children}
    </section>
  )
}

export function PanelHead({ title, description }: { title: string; description: string }) {
  return (
    <header className="border-b border-slate-100 px-5 py-4">
      <h2 className="text-lg font-bold text-slate-950">{title}</h2>
      <p className="mt-1 text-sm leading-5 text-slate-500">{description}</p>
    </header>
  )
}
