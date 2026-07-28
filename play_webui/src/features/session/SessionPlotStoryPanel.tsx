'use client'

import { useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  CalendarClock,
  CheckCircle2,
  ChevronDown,
  Dices,
  Eye,
  EyeOff,
  GitBranch,
  Loader2,
  RefreshCw,
  Route,
  ShieldCheck,
  ShieldOff,
} from 'lucide-react'
import { SideDrawer } from '@/components/common/SideDrawer'
import { getSessionPlotStory } from '@/lib/api/plotScheduling'
import { cn } from '@/lib/utils/cn'
import type {
  PlotStoryLine,
  PlotStoryNode,
  SceneTimeValue,
} from '@/types/plotScheduling'

type BadgeTone = 'slate' | 'violet' | 'emerald' | 'amber' | 'rose' | 'sky'

const BADGE_TONES: Record<BadgeTone, string> = {
  slate: 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300',
  violet: 'bg-violet-100 text-violet-700 dark:bg-violet-500/15 dark:text-violet-200',
  emerald: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-200',
  amber: 'bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-200',
  rose: 'bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-200',
  sky: 'bg-sky-100 text-sky-700 dark:bg-sky-500/15 dark:text-sky-200',
}

function Badge({
  children,
  tone = 'slate',
}: {
  children: ReactNode
  tone?: BadgeTone
}) {
  return (
    <span className={cn('rounded-full px-2.5 py-1 text-[10px] font-black', BADGE_TONES[tone])}>
      {children}
    </span>
  )
}

function formatSceneTime(value: SceneTimeValue | null) {
  if (!value) return '未设置'
  const minute = String(value.minute).padStart(2, '0')
  return `${value.year} 年 ${value.month} 月 ${value.day} 日 ${value.hour}:${minute}`
}

function nodePanelId(slotKey: string) {
  return `plot-story-${slotKey.replace(/[^A-Za-z0-9_-]/g, '-')}`
}

function PlotStoryNodeItem({
  node,
  index,
  spoilerProtectionEnabled,
  expanded,
  onToggle,
}: {
  node: PlotStoryNode
  index: number
  spoilerProtectionEnabled: boolean
  expanded: boolean
  onToggle: () => void
}) {
  const detail = node.eventDetail
  if (!node.revealed || !detail) {
    return (
      <li className="relative pl-11">
        <span className="absolute left-0 top-4 flex h-8 w-8 items-center justify-center rounded-full border-4 border-white bg-slate-300 text-[11px] font-black text-white shadow-sm dark:border-slate-950 dark:bg-slate-700">
          {index + 1}
        </span>
        <div
          aria-label={`第 ${index + 1} 个事件已由防剧透隐藏`}
          className="rounded-2xl border border-dashed border-slate-300 bg-slate-100/80 px-4 py-4 dark:border-slate-700 dark:bg-slate-900/80"
        >
          <div className="flex items-center gap-3">
            <EyeOff size={17} className="shrink-0 text-slate-400" />
            <div className="min-w-0">
              <p className="font-mono text-sm font-black tracking-[0.28em] text-slate-400" aria-hidden="true">
                ********
              </p>
              <p className="mt-1 text-[11px] font-semibold text-slate-400">
                尚未注入，事件内容已隐藏
              </p>
            </div>
          </div>
        </div>
      </li>
    )
  }

  const panelId = nodePanelId(node.slotKey)
  const sourceTurn = node.lastSourceInjectionTurnId
  const eventTurn = node.lastEventInjectionTurnId

  return (
    <li className="relative pl-11">
      <span className={cn(
        'absolute left-0 top-4 flex h-8 w-8 items-center justify-center rounded-full border-4 border-white text-[11px] font-black text-white shadow-sm dark:border-slate-950',
        node.sourceInjected
          ? 'bg-emerald-500'
          : node.eventInjected
            ? 'bg-sky-500'
            : 'bg-violet-500',
      )}>
        {index + 1}
      </span>
      <article className={cn(
        'overflow-hidden rounded-2xl border bg-white shadow-sm transition dark:bg-slate-950',
        expanded
          ? 'border-violet-300 ring-4 ring-violet-100/70 dark:border-violet-500/50 dark:ring-violet-500/10'
          : 'border-slate-200 hover:border-violet-200 dark:border-slate-800 dark:hover:border-violet-500/40',
      )}>
        <button
          type="button"
          aria-expanded={expanded}
          aria-controls={panelId}
          onClick={onToggle}
          className="flex w-full items-start gap-3 px-4 py-4 text-left"
        >
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h4 className="min-w-0 text-sm font-black text-slate-950 dark:text-slate-100 sm:text-base">
                {detail.title}
              </h4>
              {node.sourceInjected ? (
                <Badge tone="emerald">
                  当前位置已注入{sourceTurn ? ` · Turn ${sourceTurn}` : ''}
                </Badge>
              ) : node.eventInjected ? (
                <Badge tone="sky">
                  已在其他位置注入{eventTurn ? ` · Turn ${eventTurn}` : ''}
                </Badge>
              ) : spoilerProtectionEnabled ? (
                <Badge tone="violet">首事件固定可见</Badge>
              ) : (
                <Badge>尚未注入</Badge>
              )}
              {node.sessionDisabled ? <Badge tone="rose">会话已禁用</Badge> : null}
              {!node.enabled || !detail.eventEnabled ? <Badge tone="slate">定义已停用</Badge> : null}
            </div>
            <p className="mt-2 flex items-center gap-2 text-xs font-bold text-slate-400">
              <CalendarClock size={14} className="shrink-0" />
              {formatSceneTime(detail.scheduledTime)}
              <span aria-hidden="true">·</span>
              {detail.dispatchMode === 'forced' ? '强制调度' : '适宜时调度'}
            </p>
          </div>
          <ChevronDown
            size={18}
            className={cn(
              'mt-1 shrink-0 text-slate-400 transition',
              expanded ? 'rotate-180 text-violet-600 dark:text-violet-300' : '',
            )}
          />
        </button>

        {expanded ? (
          <div
            id={panelId}
            className="border-t border-slate-100 bg-slate-50/80 px-4 py-4 dark:border-slate-800 dark:bg-slate-900/60"
          >
            {detail.description ? (
              <section>
                <p className="text-[10px] font-black uppercase tracking-[0.12em] text-slate-400">事件详情</p>
                <p className="mt-2 whitespace-pre-wrap text-sm font-semibold leading-6 text-slate-700 dark:text-slate-200">
                  {detail.description}
                </p>
              </section>
            ) : null}
            <section className={detail.description ? 'mt-5' : ''}>
              <p className="text-[10px] font-black uppercase tracking-[0.12em] text-violet-500">剧情指引</p>
              <p className="mt-2 whitespace-pre-wrap rounded-xl border border-violet-100 bg-white px-4 py-3 text-sm font-semibold leading-6 text-slate-700 dark:border-violet-500/20 dark:bg-slate-950 dark:text-slate-200">
                {detail.directive}
              </p>
            </section>
            {detail.suitabilityHint ? (
              <section className="mt-5">
                <p className="text-[10px] font-black uppercase tracking-[0.12em] text-amber-600 dark:text-amber-300">适宜条件</p>
                <p className="mt-2 whitespace-pre-wrap text-sm font-semibold leading-6 text-slate-600 dark:text-slate-300">
                  {detail.suitabilityHint}
                </p>
              </section>
            ) : null}

            <dl className="mt-5 grid gap-3 sm:grid-cols-2">
              <div className="rounded-xl bg-white px-3.5 py-3 dark:bg-slate-950">
                <dt className="text-[10px] font-black uppercase tracking-[0.08em] text-slate-400">调度时间</dt>
                <dd className="mt-1 text-xs font-bold leading-5 text-slate-700 dark:text-slate-200">
                  {formatSceneTime(detail.scheduledTime)}
                </dd>
              </div>
              <div className="rounded-xl bg-white px-3.5 py-3 dark:bg-slate-950">
                <dt className="text-[10px] font-black uppercase tracking-[0.08em] text-slate-400">截止时间</dt>
                <dd className="mt-1 text-xs font-bold leading-5 text-slate-700 dark:text-slate-200">
                  {formatSceneTime(detail.deadlineTime)}
                </dd>
              </div>
              <div className="rounded-xl bg-white px-3.5 py-3 dark:bg-slate-950">
                <dt className="text-[10px] font-black uppercase tracking-[0.08em] text-slate-400">当前位置</dt>
                <dd className="mt-1 text-xs font-bold leading-5 text-slate-700 dark:text-slate-200">
                  {node.sourceInjected
                    ? `已注入 ${node.sourceInjectionCount} 次`
                    : '尚未从此位置注入'}
                </dd>
              </div>
              <div className="rounded-xl bg-white px-3.5 py-3 dark:bg-slate-950">
                <dt className="text-[10px] font-black uppercase tracking-[0.08em] text-slate-400">同一事件</dt>
                <dd className="mt-1 text-xs font-bold leading-5 text-slate-700 dark:text-slate-200">
                  {node.eventInjected
                    ? `共注入 ${node.eventInjectionCount} 次`
                    : '尚未注入'}
                  {detail.allowRepeat
                    ? ` · 可重复，冷却 ${detail.repeatCooldownMinutes} 分钟`
                    : ' · 不重复'}
                </dd>
              </div>
            </dl>
          </div>
        ) : null}
      </article>
    </li>
  )
}

function PlotStoryLineCard({
  line,
  spoilerProtectionEnabled,
  expandedSlots,
  onToggleNode,
}: {
  line: PlotStoryLine
  spoilerProtectionEnabled: boolean
  expandedSlots: ReadonlySet<string>
  onToggleNode: (slotKey: string) => void
}) {
  const injectedCount = line.nodes.filter((node) => node.sourceInjected).length

  return (
    <section className="overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-950">
      <header className="border-b border-slate-100 bg-gradient-to-r from-white to-violet-50/60 px-5 py-5 dark:border-slate-800 dark:from-slate-950 dark:to-violet-500/5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-violet-100 text-violet-700 dark:bg-violet-500/15 dark:text-violet-200">
                {line.kind === 'outline' ? <GitBranch size={18} /> : <Dices size={18} />}
              </span>
              <div>
                <p className="text-[10px] font-black uppercase tracking-[0.12em] text-violet-500">
                  {line.kind === 'outline' ? '剧情大纲' : '动态事件池'}
                </p>
                <h3 className="mt-0.5 text-lg font-black text-slate-950 dark:text-slate-100">{line.name}</h3>
              </div>
            </div>
            {line.description ? (
              <p className="mt-3 max-w-3xl text-sm font-semibold leading-6 text-slate-500 dark:text-slate-300">
                {line.description}
              </p>
            ) : null}
          </div>
          <div className="flex flex-wrap gap-2">
            <Badge tone={line.enabled ? 'emerald' : 'slate'}>
              {line.enabled ? '剧情线启用' : '剧情线停用'}
            </Badge>
            <Badge>{injectedCount}/{line.nodes.length} 个位置已注入</Badge>
          </div>
        </div>
      </header>

      {line.nodes.length ? (
        <ol className="relative space-y-3 px-5 py-5 before:absolute before:bottom-8 before:left-9 before:top-8 before:w-px before:bg-slate-200 dark:before:bg-slate-800">
          {line.nodes.map((node, index) => (
            <PlotStoryNodeItem
              key={node.slotKey}
              node={node}
              index={index}
              spoilerProtectionEnabled={spoilerProtectionEnabled}
              expanded={expandedSlots.has(node.slotKey)}
              onToggle={() => onToggleNode(node.slotKey)}
            />
          ))}
        </ol>
      ) : (
        <p className="px-5 py-8 text-center text-sm font-semibold text-slate-400">这条剧情线暂时没有事件。</p>
      )}
    </section>
  )
}

function PlotStorySection({
  title,
  description,
  icon,
  lines,
  spoilerProtectionEnabled,
  expandedSlots,
  onToggleNode,
}: {
  title: string
  description: string
  icon: ReactNode
  lines: PlotStoryLine[]
  spoilerProtectionEnabled: boolean
  expandedSlots: ReadonlySet<string>
  onToggleNode: (slotKey: string) => void
}) {
  if (!lines.length) return null

  return (
    <section>
      <div className="mb-3 flex items-center gap-3 px-1">
        <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-slate-950 text-white dark:bg-violet-600">
          {icon}
        </span>
        <div>
          <h2 className="text-base font-black text-slate-950 dark:text-slate-100">{title}</h2>
          <p className="mt-0.5 text-xs font-semibold text-slate-400">{description}</p>
        </div>
      </div>
      <div className="space-y-4">
        {lines.map((line) => (
          <PlotStoryLineCard
            key={`${line.kind}:${line.id}`}
            line={line}
            spoilerProtectionEnabled={spoilerProtectionEnabled}
            expandedSlots={expandedSlots}
            onToggleNode={onToggleNode}
          />
        ))}
      </div>
    </section>
  )
}

export function SessionPlotStoryPanel({
  sessionId,
  open,
  onClose,
}: {
  sessionId: string
  open: boolean
  onClose: () => void
}) {
  const [spoilerState, setSpoilerState] = useState({
    sessionId,
    enabled: true,
  })
  const [expandedState, setExpandedState] = useState<{
    sessionId: string
    slots: Set<string>
  }>({
    sessionId,
    slots: new Set(),
  })
  const spoilerProtectionEnabled = spoilerState.sessionId === sessionId
    ? spoilerState.enabled
    : true
  const expandedSlots = expandedState.sessionId === sessionId
    ? expandedState.slots
    : new Set<string>()
  const revealSpoilers = !spoilerProtectionEnabled

  useEffect(() => {
    setSpoilerState({ sessionId, enabled: true })
    setExpandedState({ sessionId, slots: new Set() })
  }, [sessionId])

  const query = useQuery({
    queryKey: ['play-session-plot-story', sessionId, revealSpoilers],
    queryFn: () => getSessionPlotStory(sessionId, { revealSpoilers }),
    enabled: open,
    retry: false,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  })
  const data = query.data
  const stats = useMemo(() => {
    const lines = data ? [...data.outlines, ...data.pools] : []
    const nodes = lines.flatMap((line) => line.nodes)
    return {
      lines: lines.length,
      nodes: nodes.length,
      revealed: nodes.filter((node) => node.revealed).length,
      injected: nodes.filter((node) => node.sourceInjected).length,
    }
  }, [data])

  const toggleNode = (slotKey: string) => {
    setExpandedState((current) => {
      const next = current.sessionId === sessionId
        ? new Set(current.slots)
        : new Set<string>()
      if (next.has(slotKey)) next.delete(slotKey)
      else next.add(slotKey)
      return { sessionId, slots: next }
    })
  }

  const toggleSpoilerProtection = () => {
    setSpoilerState((current) => ({
      sessionId,
      enabled: current.sessionId === sessionId ? !current.enabled : false,
    }))
  }

  const empty = data && !data.outlines.length && !data.pools.length

  return (
    <SideDrawer
      open={open}
      side="right"
      eyebrow="Session plot story"
      title="剧情故事"
      description="浏览当前故事的剧情线、事件详情与已提交的注入记录。"
      meta={data ? (
        <div className="flex flex-wrap gap-2">
          <Badge>{stats.lines} 条剧情线</Badge>
          <Badge>{stats.revealed}/{stats.nodes} 个事件位置可见</Badge>
          <Badge tone="emerald">{stats.injected} 个位置已注入</Badge>
        </div>
      ) : undefined}
      onClose={onClose}
      panelClassName="!max-w-none lg:!w-[860px] lg:!max-w-[calc(100vw-36px)]"
      contentClassName="!overflow-hidden !p-0"
      overlayClassName="z-[65]"
    >
      <div className="flex h-full min-h-0 flex-col">
        <div className="shrink-0 border-b border-slate-200 bg-white px-4 py-3 dark:border-slate-800 dark:bg-slate-950 sm:px-5">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex min-w-0 items-start gap-3">
              <span className={cn(
                'mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl',
                spoilerProtectionEnabled
                  ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-200'
                  : 'bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-200',
              )}>
                {spoilerProtectionEnabled ? <ShieldCheck size={18} /> : <ShieldOff size={18} />}
              </span>
              <div className="min-w-0">
                <p className="text-sm font-black text-slate-900 dark:text-slate-100">
                  {spoilerProtectionEnabled ? '防剧透已开启' : '防剧透已关闭'}
                </p>
                <p className="mt-0.5 text-xs font-semibold leading-5 text-slate-500 dark:text-slate-300">
                  {spoilerProtectionEnabled
                    ? '仅显示每条剧情线的第一个事件，以及曾被成功注入的事件。'
                    : '当前故事的全部事件内容均可查看。'}
                </p>
              </div>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <button
                type="button"
                role="switch"
                aria-checked={spoilerProtectionEnabled}
                onClick={toggleSpoilerProtection}
                className={cn(
                  'inline-flex h-10 items-center gap-2 rounded-xl border px-3 text-xs font-black transition',
                  spoilerProtectionEnabled
                    ? 'border-emerald-200 bg-emerald-50 text-emerald-700 hover:bg-emerald-100 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-200'
                    : 'border-amber-200 bg-amber-50 text-amber-800 hover:bg-amber-100 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-200',
                )}
              >
                {spoilerProtectionEnabled ? <EyeOff size={15} /> : <Eye size={15} />}
                防剧透
                <span className={cn(
                  'relative h-5 w-9 rounded-full transition',
                  spoilerProtectionEnabled ? 'bg-emerald-500' : 'bg-slate-300 dark:bg-slate-700',
                )}>
                  <span className={cn(
                    'absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition',
                    spoilerProtectionEnabled ? 'left-[18px]' : 'left-0.5',
                  )} />
                </span>
              </button>
              <button
                type="button"
                onClick={() => void query.refetch()}
                disabled={query.isFetching}
                className="inline-flex h-10 items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 text-xs font-black text-slate-600 transition hover:border-violet-200 hover:text-violet-700 disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300"
              >
                <RefreshCw size={15} className={query.isFetching ? 'animate-spin' : ''} />
                <span className="hidden sm:inline">刷新</span>
              </button>
            </div>
          </div>
          <p className="mt-3 flex items-start gap-2 rounded-xl bg-slate-100 px-3 py-2 text-[11px] font-semibold leading-5 text-slate-500 dark:bg-slate-900 dark:text-slate-300">
            <CheckCircle2 size={14} className="mt-0.5 shrink-0 text-emerald-500" />
            “已注入”只表示调度器曾选择该事件并把指引注入一个成功提交的 Turn，不代表事件已经在正文中完成。
          </p>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain bg-[#f7f8fc] px-4 py-5 dark:bg-[#0b1020] sm:px-5">
          {query.isPending ? (
            <div className="flex min-h-64 items-center justify-center">
              <div className="text-center">
                <Loader2 size={24} className="mx-auto animate-spin text-violet-500" />
                <p className="mt-3 text-sm font-bold text-slate-400">正在整理当前剧情线…</p>
              </div>
            </div>
          ) : query.isError ? (
            <div className="rounded-2xl border border-rose-200 bg-rose-50 px-5 py-7 text-center dark:border-rose-500/30 dark:bg-rose-500/10">
              <p className="text-sm font-bold text-rose-700 dark:text-rose-200">
                剧情故事加载失败：{query.error instanceof Error ? query.error.message : '未知错误'}
              </p>
              <button
                type="button"
                onClick={() => void query.refetch()}
                className="mt-4 inline-flex h-9 items-center gap-2 rounded-lg bg-rose-600 px-3 text-xs font-black text-white"
              >
                <RefreshCw size={14} />重试
              </button>
            </div>
          ) : empty ? (
            <div className="flex min-h-64 items-center justify-center rounded-3xl border border-dashed border-slate-300 bg-white/70 px-6 py-12 text-center dark:border-slate-700 dark:bg-slate-900/70">
              <div className="max-w-md">
                <span className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-violet-100 text-violet-700 dark:bg-violet-500/15 dark:text-violet-200">
                  <Route size={22} />
                </span>
                <h3 className="mt-4 text-base font-black text-slate-950 dark:text-slate-100">当前故事还没有剧情线</h3>
                <p className="mt-2 text-sm font-semibold leading-6 text-slate-500 dark:text-slate-300">
                  在剧情动态调度页添加大纲或事件池后，会在这里按当前 Session 的注入进度展示。
                </p>
              </div>
            </div>
          ) : data ? (
            <div className="space-y-7">
              <PlotStorySection
                title="剧情大纲"
                description="按既定节点顺序推进的故事线"
                icon={<GitBranch size={18} />}
                lines={data.outlines}
                spoilerProtectionEnabled={spoilerProtectionEnabled}
                expandedSlots={expandedSlots}
                onToggleNode={toggleNode}
              />
              <PlotStorySection
                title="动态事件池"
                description="根据场景和适宜性动态选择的插曲"
                icon={<Dices size={18} />}
                lines={data.pools}
                spoilerProtectionEnabled={spoilerProtectionEnabled}
                expandedSlots={expandedSlots}
                onToggleNode={toggleNode}
              />
            </div>
          ) : null}
        </div>
      </div>
    </SideDrawer>
  )
}
