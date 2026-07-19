'use client'

import { useEffect, useMemo, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  CalendarClock,
  CheckCircle2,
  Clock3,
  Dices,
  GitBranch,
  History,
  Pencil,
  Plus,
  Route,
  ShieldAlert,
  Sparkles,
  Trash2,
  X,
} from 'lucide-react'
import { AppShell, useAppShell } from '@/features/layout/AppShell'
import {
  createPlotEvent,
  createPlotNode,
  createPlotOutline,
  createPlotPool,
  deletePlotEvent,
  deletePlotNode,
  deletePlotOutline,
  deletePlotPool,
  getSessionPlotSchedule,
  getStoryPlotSchedule,
  reorderPlotEvents,
  reorderPlotNodes,
  setPlotEventOverride,
  setPlotNodeOverride,
  updatePlotEvent,
  updatePlotNode,
  updatePlotOutline,
  updatePlotPool,
} from '@/lib/api/plotScheduling'
import { getSessionRPModules, getStoryRPModules, patchStoryRPModule } from '@/lib/api/rpModules'
import { listSessions } from '@/lib/api/sessions'
import { listStories } from '@/lib/api/stories'
import type { RPModuleConfig } from '@/types/rpModules'
import {
  PLOT_DISPATCH_MODE,
  PLOT_POOL_MODE,
  type PlotEvent,
  type PlotEventInput,
  type PlotEventPool,
  type PlotNodeInput,
  type PlotOutline,
  type PlotOutlineInput,
  type PlotOutlineNode,
  type PlotPoolInput,
  type PlotSchedule,
  type SceneTimeValue,
} from '@/types/plotScheduling'

const PLOT_MODULE_NAME = 'plot_scheduler'
const DEFAULT_TIME: SceneTimeValue = { year: 1, month: 1, day: 1, hour: 8, minute: 0 }

type View = 'outlines' | 'pools' | 'runtime'
type EditorTarget =
  | { kind: 'pool'; item?: PlotEventPool }
  | { kind: 'event'; poolId: number; item?: PlotEvent }
  | { kind: 'outline'; item?: PlotOutline }
  | { kind: 'node'; outlineId: number; item?: PlotOutlineNode }

type EditorSave =
  | { kind: 'pool'; input: PlotPoolInput }
  | { kind: 'event'; input: PlotEventInput }
  | { kind: 'outline'; input: PlotOutlineInput }
  | { kind: 'node'; input: PlotNodeInput }

const panelClass = 'rounded-2xl border border-slate-200 bg-white shadow-sm'
const inputClass = 'h-11 w-full rounded-xl border border-slate-200 bg-white px-3.5 text-base font-semibold text-slate-800 outline-none transition focus:border-violet-400 focus:ring-4 focus:ring-violet-100'
const textareaClass = 'w-full rounded-xl border border-slate-200 bg-white px-3.5 py-3 text-base font-medium leading-7 text-slate-800 outline-none transition focus:border-violet-400 focus:ring-4 focus:ring-violet-100'
const primaryButton = 'inline-flex h-11 items-center justify-center gap-2 rounded-xl bg-violet-600 px-4 text-sm font-black text-white shadow-sm transition hover:bg-violet-700 disabled:cursor-not-allowed disabled:opacity-50'
const quietButton = 'inline-flex h-10 items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-3.5 text-sm font-bold text-slate-600 transition hover:border-violet-200 hover:bg-violet-50 hover:text-violet-700 disabled:cursor-not-allowed disabled:opacity-40'

function formatSceneTime(value: SceneTimeValue | null | undefined) {
  if (!value) return '未设置时间'
  const minute = value.minute ? ` ${value.minute} 分` : ''
  return `第 ${value.year} 年 ${value.month} 月 ${value.day} 日 ${value.hour} 时${minute}`
}

function isValidSceneTime(value: SceneTimeValue) {
  return Number.isInteger(value.year) && value.year >= 1
    && Number.isInteger(value.month) && value.month >= 1 && value.month <= 12
    && Number.isInteger(value.day) && value.day >= 1 && value.day <= 31
    && Number.isInteger(value.hour) && value.hour >= 0 && value.hour <= 23
    && Number.isInteger(value.minute) && value.minute >= 0 && value.minute <= 59
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-2 flex items-center justify-between gap-3 text-sm font-black text-slate-700">
        {label}
        {hint ? <span className="font-semibold text-slate-400">{hint}</span> : null}
      </span>
      {children}
    </label>
  )
}

function SceneTimeEditor({ value, onChange }: { value: SceneTimeValue; onChange: (value: SceneTimeValue) => void }) {
  const fields: Array<[keyof SceneTimeValue, string, number, number]> = [
    ['year', '年', 1, 9999], ['month', '月', 1, 12], ['day', '日', 1, 31],
    ['hour', '时', 0, 23], ['minute', '分', 0, 59],
  ]
  return (
    <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-5">
      {fields.map(([key, label, min, max]) => (
        <label key={key} className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2">
          <span className="block text-xs font-black text-slate-400">{label}</span>
          <input
            type="number"
            min={min}
            max={max}
            value={value[key]}
            onChange={(event) => onChange({ ...value, [key]: Number(event.target.value) })}
            className="mt-1 w-full bg-transparent text-lg font-black text-slate-900 outline-none"
          />
        </label>
      ))}
    </div>
  )
}

function Toggle({ checked, label, onChange, disabled = false }: { checked: boolean; label: string; onChange: (checked: boolean) => void; disabled?: boolean }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className="inline-flex items-center gap-2.5 text-sm font-bold text-slate-600 disabled:opacity-50"
    >
      <span className={`relative h-6 w-11 rounded-full transition ${checked ? 'bg-violet-600' : 'bg-slate-300'}`}>
        <span className={`absolute top-1 h-4 w-4 rounded-full bg-white shadow-sm transition ${checked ? 'left-6' : 'left-1'}`} />
      </span>
      {label}
    </button>
  )
}

function Tag({ children, tone = 'slate' }: { children: React.ReactNode; tone?: 'slate' | 'violet' | 'amber' | 'emerald' | 'rose' }) {
  const tones = {
    slate: 'bg-slate-100 text-slate-600', violet: 'bg-violet-100 text-violet-700',
    amber: 'bg-amber-100 text-amber-800', emerald: 'bg-emerald-100 text-emerald-700', rose: 'bg-rose-100 text-rose-700',
  }
  return <span className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-black ${tones[tone]}`}>{children}</span>
}

function Empty({ children }: { children: React.ReactNode }) {
  return <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50 px-6 py-14 text-center text-base font-semibold text-slate-500">{children}</div>
}

function DefinitionDialog({ target, schedule, busy, errorMessage, onClose, onSave }: {
  target: EditorTarget
  schedule: PlotSchedule
  busy: boolean
  errorMessage?: string
  onClose: () => void
  onSave: (value: EditorSave) => void
}) {
  const poolItem = target.kind === 'pool' ? target.item : undefined
  const eventItem = target.kind === 'event' ? target.item : undefined
  const outlineItem = target.kind === 'outline' ? target.item : undefined
  const nodeItem = target.kind === 'node' ? target.item : undefined
  const [name, setName] = useState(poolItem?.name ?? outlineItem?.name ?? '')
  const [description, setDescription] = useState(poolItem?.description ?? outlineItem?.description ?? eventItem?.description ?? '')
  const [priority, setPriority] = useState(poolItem?.priority ?? outlineItem?.priority ?? 0)
  const [enabled, setEnabled] = useState(poolItem?.enabled ?? outlineItem?.enabled ?? eventItem?.enabled ?? nodeItem?.enabled ?? true)
  const [poolMode, setPoolMode] = useState(poolItem?.selectionMode ?? PLOT_POOL_MODE.RANDOM)
  const [poolId, setPoolId] = useState(eventItem?.poolId ?? (target.kind === 'event' ? target.poolId : schedule.pools[0]?.id ?? 0))
  const [title, setTitle] = useState(eventItem?.title ?? '')
  const [directive, setDirective] = useState(eventItem?.directive ?? '')
  const [suitabilityHint, setSuitabilityHint] = useState(eventItem?.suitabilityHint ?? '')
  const [dispatchMode, setDispatchMode] = useState(eventItem?.dispatchMode ?? nodeItem?.dispatchMode ?? PLOT_DISPATCH_MODE.SOFT)
  const [hasTime, setHasTime] = useState(Boolean(eventItem?.scheduledTime) || target.kind === 'node')
  const [scheduledTime, setScheduledTime] = useState(eventItem?.scheduledTime ?? nodeItem?.scheduledTime ?? DEFAULT_TIME)
  const [allowRepeat, setAllowRepeat] = useState(eventItem?.allowRepeat ?? false)
  const [cooldown, setCooldown] = useState(eventItem?.repeatCooldownMinutes || 60)
  const [eventId, setEventId] = useState(nodeItem?.eventId ?? schedule.events[0]?.id ?? 0)

  const titleText = target.kind === 'pool'
    ? `${poolItem ? '编辑' : '新建'}事件池`
    : target.kind === 'event'
      ? `${eventItem ? '编辑' : '新建'}剧情事件`
      : target.kind === 'outline'
        ? `${outlineItem ? '编辑' : '新建'}剧情大纲`
        : `${nodeItem ? '编辑' : '新建'}大纲节点`

  const submit = () => {
    if (target.kind === 'pool') {
      onSave({ kind: 'pool', input: { name, description, priority, enabled, selectionMode: poolMode } })
    } else if (target.kind === 'event') {
      onSave({ kind: 'event', input: {
        poolId, title, directive, description, suitabilityHint, dispatchMode,
        scheduledTime: hasTime ? scheduledTime : null, enabled, allowRepeat,
        repeatCooldownMinutes: allowRepeat ? cooldown : 0,
      } })
    } else if (target.kind === 'outline') {
      onSave({ kind: 'outline', input: { name, description, priority, enabled } })
    } else {
      onSave({ kind: 'node', input: { eventId, scheduledTime, dispatchMode, enabled } })
    }
  }

  const valid = target.kind === 'pool' || target.kind === 'outline'
    ? name.trim().length > 0
    : target.kind === 'event'
      ? poolId > 0
        && title.trim().length > 0
        && directive.trim().length > 0
        && (!hasTime || isValidSceneTime(scheduledTime))
        && (!allowRepeat || (Number.isInteger(cooldown) && cooldown > 0))
      : eventId > 0 && isValidSceneTime(scheduledTime)

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/45 p-4" role="dialog" aria-modal="true">
      <div className="max-h-[92vh] w-full max-w-3xl overflow-y-auto rounded-3xl border border-slate-200 bg-white shadow-2xl">
        <header className="sticky top-0 z-10 flex items-center justify-between border-b border-slate-200 bg-white/95 px-6 py-5 backdrop-blur dark:border-slate-700 dark:bg-slate-900/95">
          <div>
            <p className="text-xs font-black uppercase tracking-[0.2em] text-violet-500">Plot scheduling</p>
            <h2 className="mt-1 text-2xl font-black text-slate-950">{titleText}</h2>
          </div>
          <button type="button" onClick={onClose} className="flex h-10 w-10 items-center justify-center rounded-xl text-slate-500 hover:bg-slate-100" aria-label="关闭"><X size={20} /></button>
        </header>
        <div className="space-y-5 p-6">
          {errorMessage ? <div className="flex items-start gap-3 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-bold text-rose-800"><ShieldAlert className="mt-0.5 shrink-0" size={18} /><span>{errorMessage}</span></div> : null}
          {target.kind === 'pool' || target.kind === 'outline' ? (
            <>
              <Field label={target.kind === 'pool' ? '事件池名称' : '大纲名称'}><input value={name} onChange={(event) => setName(event.target.value)} className={inputClass} autoFocus /></Field>
              <Field label="说明" hint="仅用于管理"><textarea value={description} onChange={(event) => setDescription(event.target.value)} rows={3} className={textareaClass} /></Field>
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="优先级" hint="数值越高越先调度"><input type="number" value={priority} onChange={(event) => setPriority(Number(event.target.value))} className={inputClass} /></Field>
                {target.kind === 'pool' ? <Field label="池内模式"><select value={poolMode} onChange={(event) => setPoolMode(event.target.value as typeof poolMode)} className={inputClass}><option value="random">随机</option><option value="sequential">顺序</option></select></Field> : <div className="flex items-end pb-2"><Toggle checked={enabled} label="启用此大纲" onChange={setEnabled} /></div>}
              </div>
              {target.kind === 'pool' ? <Toggle checked={enabled} label="启用此事件池" onChange={setEnabled} /> : null}
            </>
          ) : null}

          {target.kind === 'event' ? (
            <>
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="所属事件池"><select value={poolId} onChange={(event) => setPoolId(Number(event.target.value))} className={inputClass}>{schedule.pools.map((pool) => <option key={pool.id} value={pool.id}>{pool.name}</option>)}</select></Field>
                <Field label="调度约束"><select value={dispatchMode} onChange={(event) => setDispatchMode(event.target.value as typeof dispatchMode)} className={inputClass}><option value="soft">软约束 · 先判断适宜性</option><option value="forced">强制 · 到时直接注入</option></select></Field>
              </div>
              <Field label="事件标题"><input value={title} onChange={(event) => setTitle(event.target.value)} className={inputClass} autoFocus /></Field>
              <Field label="事件说明" hint="供策划阅读"><textarea value={description} onChange={(event) => setDescription(event.target.value)} rows={2} className={textareaClass} /></Field>
              <Field label="注入指令" hint="将进入 RP Module 动态层"><textarea value={directive} onChange={(event) => setDirective(event.target.value)} rows={5} className={textareaClass} /></Field>
              <Field label="适宜性提示" hint="只影响软约束判断"><textarea value={suitabilityHint} onChange={(event) => setSuitabilityHint(event.target.value)} rows={2} className={textareaClass} /></Field>
              <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                <Toggle checked={hasTime} label="设置首次可调度时间" onChange={setHasTime} />
                {hasTime ? <div className="mt-4"><SceneTimeEditor value={scheduledTime} onChange={setScheduledTime} /></div> : <p className="mt-2 text-sm font-semibold text-slate-500">未设置时，事件在会话开始后立即进入候选。</p>}
              </div>
              <div className="grid gap-4 rounded-2xl border border-slate-200 p-4 sm:grid-cols-[1fr_220px]">
                <div><Toggle checked={allowRepeat} label="允许重复发生" onChange={setAllowRepeat} /><p className="mt-2 text-sm font-semibold text-slate-500">重复状态与大纲节点独立，冷却按世界内 Scene 时间计算。</p></div>
                {allowRepeat ? <Field label="冷却分钟"><input type="number" min={1} value={cooldown} onChange={(event) => setCooldown(Number(event.target.value))} className={inputClass} /></Field> : null}
              </div>
              <Toggle checked={enabled} label="启用池内调度" onChange={setEnabled} />
            </>
          ) : null}

          {target.kind === 'node' ? (
            <>
              <Field label="引用剧情事件"><select value={eventId} onChange={(event) => setEventId(Number(event.target.value))} className={inputClass}>{schedule.events.map((event) => <option key={event.id} value={event.id}>{event.title}</option>)}</select></Field>
              <fieldset>
                <legend className="mb-2 text-sm font-black text-slate-700">固定时间节点</legend>
                <SceneTimeEditor value={scheduledTime} onChange={setScheduledTime} />
              </fieldset>
              <Field label="调度约束"><select value={dispatchMode} onChange={(event) => setDispatchMode(event.target.value as typeof dispatchMode)} className={inputClass}><option value="soft">软约束 · 先判断适宜性</option><option value="forced">强制 · 到时直接注入</option></select></Field>
              <Toggle checked={enabled} label="启用此节点" onChange={setEnabled} />
            </>
          ) : null}
        </div>
        <footer className="sticky bottom-0 flex justify-end gap-3 border-t border-slate-200 bg-white/95 px-6 py-4 backdrop-blur dark:border-slate-700 dark:bg-slate-900/95">
          <button type="button" onClick={onClose} className={quietButton}>取消</button>
          <button type="button" disabled={!valid || busy} onClick={submit} className={primaryButton}>{busy ? '保存中…' : '保存'}</button>
        </footer>
      </div>
    </div>
  )
}

function ModuleBanner({ module, busy, onMount }: { module: RPModuleConfig | undefined; busy: boolean; onMount: () => void }) {
  const mounted = Boolean(module?.storyMounted)
  const effective = Boolean(module?.effectiveEnabled)
  return (
    <section className={`${panelClass} mb-6 overflow-hidden`}>
      <div className="flex flex-col gap-4 bg-gradient-to-r from-violet-600 to-indigo-600 px-6 py-5 text-white xl:flex-row xl:items-center xl:justify-between">
        <div className="flex items-start gap-4">
          <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-white/15"><Sparkles size={24} /></span>
          <div><p className="text-lg font-black">RP Module · 剧情动态调度</p><p className="mt-1 max-w-3xl text-sm font-semibold leading-6 text-violet-100">定义属于 Story；只有挂载并启用模块后，Session turn 才会按照 Scene 时间选择候选并注入动态层。</p></div>
        </div>
        {mounted ? <div className="flex shrink-0 items-center gap-2 rounded-full bg-white/15 px-4 py-2 text-sm font-black"><CheckCircle2 size={17} />{effective ? '已挂载并生效' : '已挂载 · 当前未生效'}</div> : <button type="button" disabled={busy} onClick={onMount} className="h-11 shrink-0 rounded-xl bg-white px-5 text-sm font-black text-violet-700 shadow-lg disabled:opacity-50">挂载到当前故事</button>}
      </div>
    </section>
  )
}

function PoolsView({ schedule, busy, onEdit, onDelete, onMove }: {
  schedule: PlotSchedule; busy: boolean; onEdit: (target: EditorTarget) => void
  onDelete: (kind: 'pool' | 'event', id: number) => void
  onMove: (pool: PlotEventPool, event: PlotEvent, direction: -1 | 1) => void
}) {
  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between gap-3"><div><h2 className="text-2xl font-black text-slate-950">剧情事件池</h2><p className="mt-1 text-base font-medium text-slate-500">多池按优先级仲裁；池内可随机或严格顺序选择。</p></div><button type="button" onClick={() => onEdit({ kind: 'pool' })} className={primaryButton}><Plus size={17} />新建事件池</button></div>
      {!schedule.pools.length ? <Empty>暂无事件池。先创建一个池，再添加可复用的剧情事件。</Empty> : schedule.pools.map((pool) => {
        const events = schedule.events.filter((event) => event.poolId === pool.id).sort((a, b) => a.position - b.position || a.id - b.id)
        return (
          <section key={pool.id} className={`${panelClass} overflow-hidden`}>
            <header className="flex flex-col gap-4 border-b border-slate-200 bg-slate-50 px-6 py-5 lg:flex-row lg:items-center lg:justify-between">
              <div><div className="flex flex-wrap items-center gap-2"><h3 className="text-xl font-black text-slate-950">{pool.name}</h3><Tag tone={pool.selectionMode === 'random' ? 'violet' : 'amber'}>{pool.selectionMode === 'random' ? '随机池' : '顺序池'}</Tag><Tag>优先级 {pool.priority}</Tag>{!pool.enabled ? <Tag tone="rose">已停用</Tag> : null}</div><p className="mt-2 text-sm font-semibold text-slate-500">{pool.description || '未填写事件池说明。'}</p></div>
              <div className="flex flex-wrap gap-2"><button type="button" onClick={() => onEdit({ kind: 'event', poolId: pool.id })} className={primaryButton}><Plus size={16} />添加事件</button><button type="button" onClick={() => onEdit({ kind: 'pool', item: pool })} className={quietButton}><Pencil size={15} />编辑</button><button type="button" disabled={busy || events.length > 0} onClick={() => onDelete('pool', pool.id)} className={quietButton}><Trash2 size={15} />删除</button></div>
            </header>
            <div className="divide-y divide-slate-100">
              {!events.length ? <div className="px-6 py-10 text-center text-sm font-semibold text-slate-400">此池暂无事件</div> : events.map((event, index) => (
                <article key={event.id} className="grid gap-4 px-6 py-5 xl:grid-cols-[minmax(0,1fr)_auto] xl:items-center">
                  <div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><span className="flex h-7 w-7 items-center justify-center rounded-lg bg-slate-100 text-xs font-black text-slate-500">{index + 1}</span><h4 className="text-lg font-black text-slate-900">{event.title}</h4><Tag tone={event.dispatchMode === 'forced' ? 'rose' : 'emerald'}>{event.dispatchMode === 'forced' ? '强制' : '软约束'}</Tag>{event.allowRepeat ? <Tag tone="amber">可重复 · {event.repeatCooldownMinutes} 分钟</Tag> : null}{!event.enabled ? <Tag tone="rose">已停用</Tag> : null}</div><p className="mt-2 line-clamp-2 text-sm font-medium leading-6 text-slate-600">{event.directive}</p><p className="mt-2 flex items-center gap-2 text-xs font-bold text-slate-400"><Clock3 size={14} />{event.scheduledTime ? `首次：${formatSceneTime(event.scheduledTime)}` : '无起始时间 · 立即候选'}</p></div>
                  <div className="flex flex-wrap gap-2"><button type="button" disabled={index === 0 || busy} onClick={() => onMove(pool, event, -1)} className={quietButton} aria-label="上移"><ArrowUp size={15} /></button><button type="button" disabled={index === events.length - 1 || busy} onClick={() => onMove(pool, event, 1)} className={quietButton} aria-label="下移"><ArrowDown size={15} /></button><button type="button" onClick={() => onEdit({ kind: 'event', poolId: pool.id, item: event })} className={quietButton}><Pencil size={15} />编辑</button><button type="button" disabled={busy} onClick={() => onDelete('event', event.id)} className={quietButton}><Trash2 size={15} /></button></div>
                </article>
              ))}
            </div>
          </section>
        )
      })}
    </div>
  )
}

function OutlinesView({ schedule, busy, onEdit, onDelete, onMove }: {
  schedule: PlotSchedule; busy: boolean; onEdit: (target: EditorTarget) => void
  onDelete: (kind: 'outline' | 'node', id: number, outlineId?: number) => void
  onMove: (outline: PlotOutline, node: PlotOutlineNode, direction: -1 | 1) => void
}) {
  const eventById = new Map(schedule.events.map((event) => [event.id, event]))
  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between gap-3"><div><h2 className="text-2xl font-black text-slate-950">剧情大纲</h2><p className="mt-1 text-base font-medium text-slate-500">每条大纲是一条按 Scene 时间推进的线性节点链；同一事件可被多个节点引用。</p></div><button type="button" onClick={() => onEdit({ kind: 'outline' })} className={primaryButton}><Plus size={17} />新建大纲</button></div>
      {!schedule.outlines.length ? <Empty>暂无剧情大纲。事件池可以独立运行，也可以先创建大纲组织固定时间节点。</Empty> : schedule.outlines.map((outline) => {
        const nodes = [...outline.nodes].sort((a, b) => a.position - b.position || a.id - b.id)
        return (
          <section key={outline.id} className={`${panelClass} overflow-hidden`}>
            <header className="flex flex-col gap-4 border-b border-slate-200 px-6 py-5 lg:flex-row lg:items-center lg:justify-between"><div><div className="flex flex-wrap items-center gap-2"><GitBranch className="text-violet-500" size={21} /><h3 className="text-xl font-black text-slate-950">{outline.name}</h3><Tag>优先级 {outline.priority}</Tag>{!outline.enabled ? <Tag tone="rose">已停用</Tag> : null}</div><p className="mt-2 text-sm font-semibold text-slate-500">{outline.description || '未填写大纲说明。'}</p></div><div className="flex flex-wrap gap-2"><button type="button" disabled={!schedule.events.length} onClick={() => onEdit({ kind: 'node', outlineId: outline.id })} className={primaryButton}><Plus size={16} />添加节点</button><button type="button" onClick={() => onEdit({ kind: 'outline', item: outline })} className={quietButton}><Pencil size={15} />编辑</button><button type="button" disabled={busy} onClick={() => onDelete('outline', outline.id)} className={quietButton} aria-label={`删除大纲 ${outline.name}`}><Trash2 size={15} /></button></div></header>
            <div className="px-6 py-6">
              {!nodes.length ? <div className="rounded-xl border border-dashed border-slate-200 px-4 py-8 text-center text-sm font-semibold text-slate-400">暂无节点{!schedule.events.length ? '，请先在事件池创建事件' : ''}</div> : <div className="relative ml-3 border-l-2 border-violet-200 pl-8">{nodes.map((node, index) => { const event = eventById.get(node.eventId); return (
                <article key={node.id} className="relative pb-7 last:pb-0"><span className="absolute -left-[43px] top-1 flex h-6 w-6 items-center justify-center rounded-full border-4 border-white bg-violet-500 text-[10px] font-black text-white">{index + 1}</span><div className="rounded-2xl border border-slate-200 bg-slate-50 p-4"><div className="flex flex-col gap-3 xl:flex-row xl:items-start xl:justify-between"><div><p className="flex items-center gap-2 text-sm font-black text-violet-700"><CalendarClock size={16} />{formatSceneTime(node.scheduledTime)}</p><h4 className="mt-2 text-lg font-black text-slate-950">{event?.title ?? `已删除事件 #${node.eventId}`}</h4><div className="mt-2 flex flex-wrap gap-2"><Tag tone={node.dispatchMode === 'forced' ? 'rose' : 'emerald'}>{node.dispatchMode === 'forced' ? '强制' : '软约束'}</Tag>{!node.enabled ? <Tag tone="rose">已停用</Tag> : null}<Tag>引用事件 #{node.eventId}</Tag></div></div><div className="flex flex-wrap gap-2"><button type="button" disabled={index === 0 || busy} onClick={() => onMove(outline, node, -1)} className={quietButton} aria-label="上移节点"><ArrowUp size={15} /></button><button type="button" disabled={index === nodes.length - 1 || busy} onClick={() => onMove(outline, node, 1)} className={quietButton} aria-label="下移节点"><ArrowDown size={15} /></button><button type="button" onClick={() => onEdit({ kind: 'node', outlineId: outline.id, item: node })} className={quietButton}><Pencil size={15} />编辑</button><button type="button" disabled={busy} onClick={() => onDelete('node', node.id, outline.id)} className={quietButton} aria-label="删除节点"><Trash2 size={15} /></button></div></div></div></article>
              )})}</div>}
            </div>
          </section>
        )
      })}
    </div>
  )
}

function RuntimeView({ schedule, sessions, sessionId, onSessionChange, runtime, sessionModule, busy, onEventOverride, onNodeOverride, onEarlier, onLatest, viewingOlder }: {
  schedule: PlotSchedule; sessions: Array<{ id: string; title?: string | null }>; sessionId: string
  onSessionChange: (id: string) => void; runtime: Awaited<ReturnType<typeof getSessionPlotSchedule>> | undefined
  sessionModule: RPModuleConfig | undefined; busy: boolean
  onEventOverride: (eventId: number, disabled: boolean) => void; onNodeOverride: (nodeId: number, disabled: boolean) => void
  onEarlier: (beforeId: number) => void; onLatest: () => void; viewingOlder: boolean
}) {
  const disabledEvents = new Set(runtime?.overrides.disabledEventIds ?? [])
  const disabledNodes = new Set(runtime?.overrides.disabledOutlineNodeIds ?? [])
  const eventById = new Map(schedule.events.map((event) => [event.id, event]))
  return (
    <div className="space-y-6">
      <section className={`${panelClass} p-6`}><div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(320px,0.7fr)] lg:items-end"><div><h2 className="text-2xl font-black text-slate-950">会话运行态</h2><p className="mt-2 text-base font-medium leading-7 text-slate-500">这里只读取事实状态，不触发适宜性判断。禁用覆盖只影响所选 Session。</p></div><Field label="选择会话"><select value={sessionId} onChange={(event) => onSessionChange(event.target.value)} className={inputClass}><option value="">请选择会话</option>{sessions.map((session) => <option key={session.id} value={session.id}>{session.title || '未命名会话'} · {session.id}</option>)}</select></Field></div></section>
      {!sessionId ? <Empty>选择一个会话后查看当前 Scene 时间、禁用覆盖和真实调度记录。</Empty> : !runtime ? <Empty>正在读取会话运行态…</Empty> : (
        <>
          {sessionModule && !sessionModule.effectiveEnabled ? <div className="flex items-start gap-3 rounded-2xl border border-amber-200 bg-amber-50 px-5 py-4 text-amber-900"><AlertTriangle className="mt-0.5 shrink-0" size={20} /><div><p className="font-black">当前 Session 的剧情调度模块未生效</p><p className="mt-1 text-sm font-semibold leading-6">定义与覆盖仍可管理，但 turn 不会执行调度。请检查 Story 开关、Session 覆盖或系统总开关。</p></div></div> : null}
          <section className="grid gap-4 lg:grid-cols-3"><div className={`${panelClass} p-5 lg:col-span-2`}><p className="text-sm font-black text-slate-400">CURRENT SCENE TIME</p>{runtime.sceneTime ? <p className="mt-3 text-2xl font-black text-slate-950">{formatSceneTime(runtime.sceneTime)}</p> : <div className="mt-3 flex items-start gap-3 rounded-xl bg-amber-50 p-4 text-amber-900"><AlertTriangle className="mt-0.5 shrink-0" size={20} /><p className="font-bold leading-6">{runtime.sceneTimeError || 'Scene 时间不可用，调度会安全跳过。'}</p></div>}<p className="mt-3 text-sm font-semibold text-slate-500">时间格式与当前场景“时间”字段严格一致；达到或超过节点时间才会进入候选。</p></div><div className={`${panelClass} p-5`}><p className="text-sm font-black text-slate-400">SESSION OVERRIDES</p><p className="mt-3 text-3xl font-black text-slate-950">{disabledEvents.size + disabledNodes.size}</p><p className="mt-2 text-sm font-semibold text-slate-500">{disabledEvents.size} 个池事件 · {disabledNodes.size} 个大纲节点</p></div></section>
          <section className={`${panelClass} overflow-hidden`}><header className="border-b border-slate-200 px-6 py-5"><h3 className="text-xl font-black text-slate-950">Session 禁用覆盖</h3><p className="mt-1 text-sm font-semibold text-slate-500">池事件与大纲节点分开覆盖；禁用事件不会连带禁用引用它的大纲节点。</p></header><div className="grid divide-y divide-slate-100 xl:grid-cols-2 xl:divide-x xl:divide-y-0"><div className="p-6"><h4 className="mb-4 flex items-center gap-2 font-black text-slate-800"><Dices size={18} className="text-violet-500" />事件池</h4><div className="space-y-2">{schedule.events.map((event) => <div key={event.id} className="flex items-center justify-between gap-3 rounded-xl bg-slate-50 px-4 py-3"><div className="min-w-0"><p className="truncate text-sm font-black text-slate-800">{event.title}</p><p className="mt-0.5 text-xs font-semibold text-slate-400">#{event.id}</p></div><Toggle disabled={busy} checked={!disabledEvents.has(event.id)} label={disabledEvents.has(event.id) ? '已禁用' : '启用'} onChange={(checked) => onEventOverride(event.id, !checked)} /></div>)}</div></div><div className="p-6"><h4 className="mb-4 flex items-center gap-2 font-black text-slate-800"><GitBranch size={18} className="text-violet-500" />大纲节点</h4><div className="space-y-2">{schedule.outlines.flatMap((outline) => outline.nodes.map((node) => <div key={node.id} className="flex items-center justify-between gap-3 rounded-xl bg-slate-50 px-4 py-3"><div className="min-w-0"><p className="truncate text-sm font-black text-slate-800">{outline.name} · {eventById.get(node.eventId)?.title ?? `事件 #${node.eventId}`}</p><p className="mt-0.5 text-xs font-semibold text-slate-400">{formatSceneTime(node.scheduledTime)}</p></div><Toggle disabled={busy} checked={!disabledNodes.has(node.id)} label={disabledNodes.has(node.id) ? '已禁用' : '启用'} onChange={(checked) => onNodeOverride(node.id, !checked)} /></div>))}</div></div></div></section>
          <section className={`${panelClass} overflow-hidden`}><header className="flex flex-col gap-3 border-b border-slate-200 px-6 py-5 sm:flex-row sm:items-center sm:justify-between"><div className="flex items-center gap-3"><History size={21} className="text-violet-500" /><div><h3 className="text-xl font-black text-slate-950">调度判断记录</h3><p className="mt-1 text-sm font-semibold text-slate-500">记录与主消息、剧情裁定和状态表在同一 turn 原子提交。</p></div></div>{viewingOlder ? <button type="button" onClick={onLatest} className={quietButton}>回到最新</button> : null}</header><div className="divide-y divide-slate-100">{!runtime.decisions.length ? <div className="px-6 py-12 text-center text-sm font-semibold text-slate-400">尚无已提交的调度判断</div> : runtime.decisions.map((decision) => { const snapshotTitle = typeof decision.eventSnapshot.eventTitle === 'string' ? decision.eventSnapshot.eventTitle : `事件 #${decision.eventId}`; const tone = decision.decisionStatus === 'triggered' ? 'emerald' : decision.decisionStatus === 'deferred' ? 'amber' : 'rose'; return <article key={decision.id} className="grid gap-3 px-6 py-5 lg:grid-cols-[140px_minmax(0,1fr)_auto] lg:items-start"><div><p className="text-sm font-black text-slate-800">Turn {decision.turnId}</p><p className="mt-1 text-xs font-semibold text-slate-400">{formatSceneTime(decision.sceneTime)}</p></div><div><div className="flex flex-wrap items-center gap-2"><h4 className="font-black text-slate-900">{snapshotTitle}</h4><Tag tone={tone}>{decision.decisionStatus === 'triggered' ? '已触发' : decision.decisionStatus === 'deferred' ? '已延期' : '判断错误'}</Tag><Tag>{decision.sourceKind === 'outline' ? '大纲' : '事件池'}</Tag></div><p className="mt-2 text-sm font-medium leading-6 text-slate-600">{decision.reason || decision.errorMessage || '无补充说明'}</p>{decision.errorCode ? <p className="mt-1 text-xs font-bold text-rose-500">{decision.errorCode}</p> : null}</div><Tag tone={decision.dispatchMode === 'forced' ? 'rose' : 'violet'}>{decision.dispatchMode === 'forced' ? '强制' : '软约束'}</Tag></article>})}</div>{runtime.nextBeforeId ? <footer className="border-t border-slate-200 px-6 py-4 text-center"><button type="button" onClick={() => onEarlier(runtime.nextBeforeId!)} className={quietButton}>查看更早记录</button></footer> : null}</section>
        </>
      )}
    </div>
  )
}

function PlotSchedulingContent() {
  const { currentWorkspace } = useAppShell()
  const queryClient = useQueryClient()
  const [storyId, setStoryId] = useState<number | null>(null)
  const [sessionId, setSessionId] = useState('')
  const [runtimeBeforeId, setRuntimeBeforeId] = useState<number | undefined>()
  const [view, setView] = useState<View>('outlines')
  const [editor, setEditor] = useState<EditorTarget | null>(null)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState<{ tone: 'ok' | 'error'; text: string } | null>(null)

  const storiesQuery = useQuery({ queryKey: ['plot-stories', currentWorkspace], queryFn: () => listStories(currentWorkspace!), enabled: Boolean(currentWorkspace) })
  const stories = useMemo(() => storiesQuery.data ?? [], [storiesQuery.data])
  useEffect(() => {
    if (!stories.length) { setStoryId(null); return }
    if (!storyId || !stories.some((story) => story.id === storyId)) setStoryId(stories[0].id)
  }, [stories, storyId])
  useEffect(() => { setSessionId(''); setRuntimeBeforeId(undefined) }, [storyId])
  useEffect(() => { setRuntimeBeforeId(undefined) }, [sessionId])

  const scheduleQuery = useQuery({ queryKey: ['plot-schedule', currentWorkspace, storyId], queryFn: () => getStoryPlotSchedule(currentWorkspace!, storyId!), enabled: Boolean(currentWorkspace && storyId) })
  const modulesQuery = useQuery({ queryKey: ['story-rp-modules', currentWorkspace, storyId], queryFn: () => getStoryRPModules(currentWorkspace!, storyId!), enabled: Boolean(currentWorkspace && storyId) })
  const sessionsQuery = useQuery({ queryKey: ['plot-sessions', currentWorkspace, storyId], queryFn: () => listSessions(currentWorkspace!, storyId!), enabled: Boolean(currentWorkspace && storyId) })
  const runtimeQuery = useQuery({ queryKey: ['session-plot-schedule', sessionId, runtimeBeforeId], queryFn: () => getSessionPlotSchedule(sessionId, { beforeId: runtimeBeforeId }), enabled: Boolean(sessionId) })
  const sessionModulesQuery = useQuery({ queryKey: ['session-rp-modules', sessionId], queryFn: () => getSessionRPModules(sessionId), enabled: Boolean(sessionId) })
  const plotModule = modulesQuery.data?.modules.find((module) => module.moduleName === PLOT_MODULE_NAME)
  const sessionPlotModule = sessionModulesQuery.data?.modules.find((module) => module.moduleName === PLOT_MODULE_NAME)

  const refreshSchedule = async () => {
    await queryClient.invalidateQueries({ queryKey: ['plot-schedule', currentWorkspace, storyId] })
    if (sessionId) await queryClient.invalidateQueries({ queryKey: ['session-plot-schedule', sessionId] })
  }
  const execute = async (success: string, action: () => Promise<unknown>, refresh = true) => {
    setBusy(true); setNotice(null)
    try { await action(); if (refresh) await refreshSchedule(); setNotice({ tone: 'ok', text: success }); return true }
    catch (error) { setNotice({ tone: 'error', text: error instanceof Error ? error.message : '操作失败' }); return false }
    finally { setBusy(false) }
  }
  const openEditor = (target: EditorTarget) => {
    setNotice(null)
    setEditor(target)
  }
  const saveEditor = async (value: EditorSave) => {
    if (!currentWorkspace || !storyId || !editor) return
    let action: () => Promise<unknown>
    if (value.kind === 'pool' && editor.kind === 'pool') action = () => editor.item ? updatePlotPool(currentWorkspace, storyId, editor.item.id, value.input) : createPlotPool(currentWorkspace, storyId, value.input)
    else if (value.kind === 'event' && editor.kind === 'event') action = () => editor.item ? updatePlotEvent(currentWorkspace, storyId, editor.item.id, value.input) : createPlotEvent(currentWorkspace, storyId, value.input)
    else if (value.kind === 'outline' && editor.kind === 'outline') action = () => editor.item ? updatePlotOutline(currentWorkspace, storyId, editor.item.id, value.input) : createPlotOutline(currentWorkspace, storyId, value.input)
    else if (value.kind === 'node' && editor.kind === 'node') action = () => editor.item ? updatePlotNode(currentWorkspace, storyId, editor.outlineId, editor.item.id, value.input) : createPlotNode(currentWorkspace, storyId, editor.outlineId, value.input)
    else return
    if (await execute('定义已保存。', action)) setEditor(null)
  }
  const deleteDefinition = async (kind: 'pool' | 'event' | 'outline' | 'node', id: number, outlineId?: number) => {
    if (!currentWorkspace || !storyId || !window.confirm('确定删除这项剧情调度定义吗？')) return
    const action = kind === 'pool' ? () => deletePlotPool(currentWorkspace, storyId, id) : kind === 'event' ? () => deletePlotEvent(currentWorkspace, storyId, id) : kind === 'outline' ? () => deletePlotOutline(currentWorkspace, storyId, id) : () => deletePlotNode(currentWorkspace, storyId, outlineId!, id)
    await execute('定义已删除。', action)
  }
  const moveEvent = async (pool: PlotEventPool, event: PlotEvent, direction: -1 | 1) => {
    if (!currentWorkspace || !storyId || !scheduleQuery.data) return
    const ids = scheduleQuery.data.events.filter((item) => item.poolId === pool.id).sort((a, b) => a.position - b.position || a.id - b.id).map((item) => item.id)
    const index = ids.indexOf(event.id); const target = index + direction
    if (target < 0 || target >= ids.length) return
    ;[ids[index], ids[target]] = [ids[target], ids[index]]
    await execute('事件顺序已更新。', () => reorderPlotEvents(currentWorkspace, storyId, pool.id, ids))
  }
  const moveNode = async (outline: PlotOutline, node: PlotOutlineNode, direction: -1 | 1) => {
    if (!currentWorkspace || !storyId) return
    const ids = [...outline.nodes].sort((a, b) => a.position - b.position || a.id - b.id).map((item) => item.id)
    const index = ids.indexOf(node.id); const target = index + direction
    if (target < 0 || target >= ids.length) return
    ;[ids[index], ids[target]] = [ids[target], ids[index]]
    await execute('节点顺序已更新。', () => reorderPlotNodes(currentWorkspace, storyId, outline.id, ids))
  }

  return (
    <div className="min-w-0 px-5 py-7 lg:px-8 2xl:px-10 2xl:py-9">
      <header className="mb-7 flex flex-col gap-5 xl:flex-row xl:items-end xl:justify-between"><div className="flex items-start gap-4"><span className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-violet-100 text-violet-700"><Route size={28} /></span><div><p className="text-sm font-black uppercase tracking-[0.2em] text-violet-500">Dynamic plot orchestration</p><h1 className="mt-1 text-3xl font-black text-slate-950 2xl:text-4xl">剧情动态调度</h1><p className="mt-2 max-w-4xl text-base font-medium leading-7 text-slate-500">以 Story 为边界组织线性大纲与事件池，根据当前 Scene 时间在每个 IC / GM turn 动态注入剧情。</p></div></div><div className="w-full xl:w-[420px]"><Field label="当前故事"><select value={storyId ?? ''} onChange={(event) => setStoryId(Number(event.target.value) || null)} className={inputClass}><option value="">请选择故事</option>{stories.map((story) => <option key={story.id} value={story.id}>{story.title}</option>)}</select></Field></div></header>
      {notice ? <div className={`mb-5 flex items-start gap-3 rounded-xl border px-4 py-3 text-sm font-bold ${notice.tone === 'ok' ? 'border-emerald-200 bg-emerald-50 text-emerald-800' : 'border-rose-200 bg-rose-50 text-rose-800'}`}>{notice.tone === 'ok' ? <CheckCircle2 size={18} /> : <ShieldAlert size={18} />}<span>{notice.text}</span></div> : null}
      {!currentWorkspace ? <Empty>请先在顶部选择 workspace。</Empty> : !storyId ? <Empty>当前 workspace 暂无 Story，请先在故事库创建故事。</Empty> : scheduleQuery.isError ? <Empty>剧情调度加载失败：{scheduleQuery.error instanceof Error ? scheduleQuery.error.message : '未知错误'}</Empty> : !scheduleQuery.data ? <Empty>正在加载剧情调度定义…</Empty> : (
        <>
          <ModuleBanner module={plotModule} busy={busy} onMount={() => execute('剧情调度模块已挂载。', async () => {
            await patchStoryRPModule(currentWorkspace, storyId, PLOT_MODULE_NAME, { enabled: true })
            await queryClient.invalidateQueries({ queryKey: ['story-rp-modules', currentWorkspace, storyId] })
            if (sessionId) await queryClient.invalidateQueries({ queryKey: ['session-rp-modules', sessionId] })
          }, false)} />
          <nav className="mb-6 flex w-fit max-w-full gap-1 overflow-x-auto rounded-2xl border border-slate-200 bg-white p-1.5 shadow-sm" aria-label="剧情调度视图">{[
            { id: 'outlines' as const, label: '剧情大纲', icon: GitBranch, count: scheduleQuery.data.outlines.length },
            { id: 'pools' as const, label: '事件池', icon: Dices, count: scheduleQuery.data.pools.length },
            { id: 'runtime' as const, label: '会话运行', icon: History, count: runtimeQuery.data?.decisions.length ?? 0 },
          ].map((item) => <button key={item.id} type="button" onClick={() => setView(item.id)} className={`flex h-11 shrink-0 items-center gap-2 rounded-xl px-4 text-sm font-black transition ${view === item.id ? 'bg-violet-600 text-white shadow-sm' : 'text-slate-500 hover:bg-slate-100 hover:text-slate-900'}`}><item.icon size={17} />{item.label}<span className={`rounded-full px-2 py-0.5 text-xs ${view === item.id ? 'bg-white/20' : 'bg-slate-100'}`}>{item.count}</span></button>)}</nav>
          {view === 'pools' ? <PoolsView schedule={scheduleQuery.data} busy={busy} onEdit={openEditor} onDelete={deleteDefinition} onMove={moveEvent} /> : view === 'outlines' ? <OutlinesView schedule={scheduleQuery.data} busy={busy} onEdit={openEditor} onDelete={deleteDefinition} onMove={moveNode} /> : runtimeQuery.isError ? <Empty>会话运行态加载失败：{runtimeQuery.error instanceof Error ? runtimeQuery.error.message : '未知错误'}</Empty> : <RuntimeView schedule={scheduleQuery.data} sessions={sessionsQuery.data ?? []} sessionId={sessionId} onSessionChange={setSessionId} runtime={runtimeQuery.data} sessionModule={sessionPlotModule} busy={busy} onEventOverride={(id, disabled) => execute('Session 事件覆盖已更新。', () => setPlotEventOverride(sessionId, id, disabled))} onNodeOverride={(id, disabled) => execute('Session 节点覆盖已更新。', () => setPlotNodeOverride(sessionId, id, disabled))} onEarlier={setRuntimeBeforeId} onLatest={() => setRuntimeBeforeId(undefined)} viewingOlder={runtimeBeforeId !== undefined} />}
          {editor ? <DefinitionDialog key={`${editor.kind}-${'item' in editor ? editor.item?.id ?? 'new' : 'new'}-${'outlineId' in editor ? editor.outlineId : ''}`} target={editor} schedule={scheduleQuery.data} busy={busy} errorMessage={notice?.tone === 'error' ? notice.text : undefined} onClose={() => setEditor(null)} onSave={saveEditor} /> : null}
        </>
      )}
    </div>
  )
}

export function PlotSchedulingPage() {
  return <AppShell><PlotSchedulingContent /></AppShell>
}
