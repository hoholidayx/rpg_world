'use client'

import { CSSProperties, PointerEvent, useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import { useQuery } from '@tanstack/react-query'
import { DebugEventLauncher } from '@/components/debug/DebugEventLauncher'
import { CommandPaletteDialog } from '@/components/input/CommandPaletteDialog'
import { SendStopButton } from '@/components/input/SendStopButton'
import { getSession } from '@/lib/api/sessions'
import type { SessionSummary } from '@/types/session'
import {
  Copy,
  Maximize2,
  RotateCcw,
  Settings,
  Sparkles,
  Star,
  Zap,
} from 'lucide-react'

const sceneRows = [
  ['地点', '雾港钟楼码头'],
  ['时间', '雨夜 23:40'],
  ['天气', '海雾'],
  ['危险', '低'],
  ['线索', '铜钥匙'],
  ['氛围', '潮湿、压抑、带着未说出口的秘密'],
]

const characterTags = ['警惕', '试探', '低声交谈']

const statusTables = [
  {
    title: '当前场景',
    rows: [
      ['地点', '雾港钟楼码头'],
      ['时间', '雨夜 23:40'],
      ['天气', '海雾'],
      ['危险', '低（0%）'],
      ['氛围', '潮湿、压抑'],
    ],
  },
  {
    title: '关系：伊凡',
    rows: [
      ['态度', '中性 +10'],
      ['信任', '仍在试探'],
      ['压力', '轻微'],
      ['最近互动', '交出铜钥匙'],
    ],
  },
  {
    title: '线索',
    rows: [
      ['铜钥匙', '已获得'],
      ['潮汐信号', '0'],
      ['第十三下钟', '待确认'],
      ['门后的名字', '未知'],
    ],
  },
  {
    title: '世界进度',
    rows: [
      ['章节', '序章 1 / 5'],
      ['下一幕', '未开启'],
      ['主线推进', '18%'],
      ['分支风险', '低'],
    ],
  },
  {
    title: '随身物品',
    rows: [
      ['铜钥匙', '1'],
      ['防水火柴', '3'],
      ['旧地图', '残页'],
      ['银币', '12'],
    ],
  },
]

const quickActions = ['观察钥匙', '询问守夜人', '检查钟楼', '保持沉默']

const defaultSidebarSizes = {
  left: 282,
  right: 314,
}

const sidebarLimits = {
  leftMin: 232,
  leftMax: 420,
  rightMin: 260,
  rightMax: 460,
}

type DragState = {
  side: 'left' | 'right'
  startX: number
  startLeft: number
  startRight: number
}

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value))
}

function Logo() {
  return (
    <Link href="/" className="flex items-center gap-3">
      <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-violet-500 to-indigo-500 text-white shadow-lg shadow-violet-200">
        <Sparkles size={22} fill="currentColor" />
      </span>
      <span className="text-lg font-bold text-slate-950">RPG World Play</span>
    </Link>
  )
}

function Panel({ title, action, children }: { title: string; action?: string; children: React.ReactNode }) {
  return (
    <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
        <h2 className="text-lg font-bold text-slate-950">{title}</h2>
        {action ? <button className="rounded-full border border-slate-200 px-3 py-1 text-sm font-medium text-slate-600">{action}</button> : <Star size={18} className="text-slate-500" />}
      </div>
      {children}
    </section>
  )
}

function StatusTable({ title, rows }: { title: string; rows: string[][] }) {
  return (
    <section className="overflow-hidden rounded-xl border border-slate-200 bg-white">
      <h3 className="border-b border-slate-100 bg-slate-50 px-3 py-2 text-sm font-bold text-slate-950">{title}</h3>
      <div className="divide-y divide-slate-100">
        {rows.map(([key, value]) => (
          <dl key={key} className="grid grid-cols-[82px_minmax(0,1fr)] gap-3 px-3 py-2 text-sm leading-5">
            <dt className="truncate text-slate-400">{key}</dt>
            <dd className="min-w-0 break-words font-medium text-slate-700">{value}</dd>
          </dl>
        ))}
      </div>
    </section>
  )
}

function Sidebar() {
  return (
    <aside className="min-h-0 overflow-y-auto border-r border-slate-200 bg-white px-5 py-5 lg:h-screen">
      <Logo />

      <div className="mt-4 space-y-4">
        <Panel title="场景 HUD">
          <dl className="space-y-3 px-4 py-4 text-sm">
            {sceneRows.map(([label, value]) => (
              <div key={label} className="grid grid-cols-[52px_minmax(0,1fr)] gap-3">
                <dt className="text-slate-400">{label}</dt>
                <dd className={`font-semibold ${label === '危险' ? 'text-emerald-600' : 'text-slate-950'}`}>{value}</dd>
              </div>
            ))}
          </dl>
        </Panel>

        <Panel title="角色" action="全部">
          <div className="px-4 py-4">
            <div className="mb-3 flex gap-2">
              <span className="rounded-lg bg-violet-100 px-3 py-1 text-sm font-bold text-violet-700">伊凡</span>
              <span className="rounded-lg border border-slate-200 px-3 py-1 text-sm text-slate-500">你</span>
              <span className="rounded-lg border border-slate-200 px-3 py-1 text-sm text-slate-500">更多</span>
            </div>
            <div className="flex gap-3">
              <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-slate-200 text-xl font-bold text-slate-600">伊</div>
              <div className="min-w-0">
                <h3 className="font-bold text-slate-950">守夜人伊凡</h3>
                <p className="mt-1 text-sm leading-5 text-slate-500">谨慎、疲惫，似乎知道某个秘密。</p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {characterTags.map((tag) => (
                    <span key={tag} className="rounded-full border border-slate-200 px-3 py-1 text-xs text-slate-500 odd:bg-slate-50 last:border-emerald-200 last:bg-emerald-50 last:text-emerald-700">
                      {tag}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </Panel>
      </div>
    </aside>
  )
}

function Header({ session, sessionId }: { session: SessionSummary | undefined; sessionId: string }) {
  return (
    <header className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-200 bg-white px-6 py-4">
      <div>
        <h1 className="text-xl font-bold text-slate-950">{session?.title ?? '加载会话中'}</h1>
        <p className="mt-1 text-sm text-slate-500">
          {session ? `故事：${session.storyId} / ${session.id}` : sessionId}
        </p>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <span className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-2 text-sm font-bold text-emerald-700">
          ● SSE · done
        </span>
        <DebugEventLauncher />
      </div>
    </header>
  )
}

function AssistantMessage({ speaker, children }: { speaker: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[44px_minmax(0,720px)] gap-3">
      <div className="flex h-11 w-11 items-center justify-center rounded-full bg-slate-200 text-base font-bold text-slate-600">{speaker}</div>
      <div>
        <p className="mb-2 text-sm text-slate-400">23:41&nbsp;&nbsp; 助手（Narrator）</p>
        <div className="rounded-2xl border border-slate-200 bg-white px-5 py-4 leading-7 text-slate-950 shadow-sm">{children}</div>
      </div>
    </div>
  )
}

function UserMessage({ children }: { children: React.ReactNode }) {
  return (
    <div className="ml-auto grid max-w-[520px] grid-cols-[minmax(0,1fr)_44px] gap-3">
      <div>
        <p className="mb-2 text-right text-sm text-slate-400">23:41&nbsp;&nbsp; 你（IC）</p>
        <div className="rounded-2xl bg-violet-600 px-5 py-4 leading-7 text-white shadow-xl shadow-violet-200">{children}</div>
      </div>
      <div className="flex h-11 w-11 items-center justify-center rounded-full bg-violet-100 text-base font-bold text-violet-700">你</div>
    </div>
  )
}

function ToolCall() {
  return (
    <div className="grid grid-cols-[44px_minmax(0,520px)] gap-3">
      <div className="flex h-11 w-11 items-center justify-center rounded-full bg-slate-200 text-slate-600">
        <Settings size={17} />
      </div>
      <div className="rounded-2xl border border-blue-200 bg-blue-50 px-5 py-4 text-blue-800">
        工具调用：线索检定（观察守夜人动作）→ 成功（难度 12，结果 14）
      </div>
    </div>
  )
}

function QuickActionCard() {
  return (
    <div className="grid grid-cols-[44px_minmax(0,420px)] gap-3">
      <div className="flex h-11 w-11 items-center justify-center rounded-full bg-slate-200 text-amber-500">
        <Zap size={18} fill="currentColor" />
      </div>
      <div className="rounded-2xl border border-amber-200 bg-amber-50 px-5 py-4">
        <h3 className="font-bold text-slate-950">快捷行动</h3>
        <div className="mt-3 flex flex-wrap gap-2">
          {quickActions.map((action) => (
            <button key={action} className="rounded-lg border border-amber-300 bg-white/70 px-3 py-2 text-sm font-bold text-amber-800">
              {action}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

function Timeline() {
  return (
    <section className="min-h-0 flex-1 overflow-y-auto bg-[#f7f7fa] px-6 py-9">
      <div className="mx-auto max-w-5xl">
        <div className="mb-8 flex items-center justify-center gap-4 text-sm text-slate-400">
          <span className="h-px w-48 bg-slate-200" />
          时间线 / Timeline
          <span className="h-px w-48 bg-slate-200" />
        </div>

        <div className="space-y-8">
          <UserMessage>我拉紧斗篷，沿着潮湿的石阶走向码头钟楼。</UserMessage>
          <AssistantMessage speaker="旁">
            雾气贴着地面翻涌，钟楼二层透出一线琥珀色灯光。守夜人停下擦拭灯罩的动作，像是已经等你很久。
          </AssistantMessage>
          <UserMessage>我压低声音问他：今晚是谁敲响了第十三下钟？</UserMessage>
          <AssistantMessage speaker="伊">
            守夜人没有立刻回答。他从怀里取出一枚沾着盐霜的铜钥匙，轻轻推到你面前：“先确认你还记得门后的名字。”
          </AssistantMessage>
          <div className="ml-[54px] flex gap-2">
            {[RotateCcw, Copy, Maximize2].map((Icon, index) => (
              <button key={index} className="flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-500">
                <Icon size={14} />
              </button>
            ))}
          </div>
          <ToolCall />
          <QuickActionCard />
        </div>
      </div>
    </section>
  )
}

function Composer({ sessionId }: { sessionId: string }) {
  return (
    <section data-session-id={sessionId} className="border-t border-slate-200 bg-white px-6 py-4">
      <div className="mx-auto max-w-6xl overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-4 py-2">
          <div className="flex flex-wrap gap-2">
            <CommandPaletteDialog sessionId={sessionId} />
            <button className="rounded-full border border-slate-200 px-3 py-1.5 text-sm text-slate-500">输入 / 触发命令</button>
          </div>
        </div>
        <div className="grid grid-cols-[minmax(0,1fr)_128px] gap-4 px-4 py-3">
          <textarea
            className="min-h-24 resize-none border-0 bg-transparent pt-2 text-base text-slate-900 outline-none placeholder:text-slate-400"
            placeholder="输入你的行动、台词或 GM 指令..."
            defaultValue=""
          />
          <SendStopButton sessionId={sessionId} />
        </div>
        <div className="flex flex-wrap items-center justify-between gap-3 bg-slate-50 px-4 py-2">
          <div className="flex flex-wrap gap-2">
            <button className="rounded-full border border-violet-200 bg-violet-50 px-3 py-1 text-xs font-medium text-violet-700">细腻描写</button>
            <button className="rounded-full border border-slate-200 px-3 py-1 text-xs text-slate-500">快速推进</button>
            <button className="rounded-full border border-slate-200 px-3 py-1 text-xs text-slate-500">多给选项</button>
          </div>
          <p className="text-xs text-slate-500">Enter 发送 / Shift+Enter 换行</p>
        </div>
      </div>
    </section>
  )
}

function RightRail() {
  return (
    <aside className="min-h-0 overflow-y-auto border-l border-slate-200 bg-white px-5 py-5 lg:h-screen">
      <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <h2 className="mb-4 text-lg font-bold text-slate-950">状态表</h2>
        <div className="space-y-3">
          {statusTables.map((table) => (
            <StatusTable key={table.title} {...table} />
          ))}
        </div>
      </section>
    </aside>
  )
}

export function SessionRoom({ sessionId }: { sessionId: string }) {
  const [leftWidth, setLeftWidth] = useState(defaultSidebarSizes.left)
  const [rightWidth, setRightWidth] = useState(defaultSidebarSizes.right)
  const [dragState, setDragState] = useState<DragState | null>(null)
  const sessionQuery = useQuery({
    queryKey: ['play-session', sessionId],
    // workspace/story 不再从路由传入，避免前端持有可失配的会话定位三元组。
    queryFn: () => getSession(sessionId),
  })

  const session = sessionQuery.data

  useEffect(() => {
    if (!dragState) return

    const handlePointerMove = (event: globalThis.PointerEvent) => {
      if (dragState.side === 'left') {
        setLeftWidth(clamp(dragState.startLeft + event.clientX - dragState.startX, sidebarLimits.leftMin, sidebarLimits.leftMax))
        return
      }
      setRightWidth(clamp(dragState.startRight - (event.clientX - dragState.startX), sidebarLimits.rightMin, sidebarLimits.rightMax))
    }

    const stopDragging = () => {
      setDragState(null)
    }

    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
    window.addEventListener('pointermove', handlePointerMove)
    window.addEventListener('pointerup', stopDragging)
    window.addEventListener('pointercancel', stopDragging)

    return () => {
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
      window.removeEventListener('pointermove', handlePointerMove)
      window.removeEventListener('pointerup', stopDragging)
      window.removeEventListener('pointercancel', stopDragging)
    }
  }, [dragState])

  const gridStyle = useMemo(
    () =>
      ({
        '--session-grid-columns': `${leftWidth}px 8px minmax(0,1fr) 8px ${rightWidth}px`,
      }) as CSSProperties,
    [leftWidth, rightWidth],
  )

  const startDrag = (side: 'left' | 'right') => (event: PointerEvent<HTMLButtonElement>) => {
    event.preventDefault()
    setDragState({
      side,
      startX: event.clientX,
      startLeft: leftWidth,
      startRight: rightWidth,
    })
  }

  return (
    <main
      style={gridStyle}
      data-workspace={session?.workspace ?? ''}
      data-story-id={session?.storyId ?? ''}
      data-session-id={sessionId}
      className="min-h-screen bg-[#f7f7fa] text-slate-900 lg:grid lg:h-screen lg:min-h-0 lg:grid-cols-[var(--session-grid-columns)] lg:overflow-hidden"
    >
      <Sidebar />
      <button
        type="button"
        aria-label="调整左侧栏宽度"
        onPointerDown={startDrag('left')}
        className="group hidden cursor-col-resize bg-slate-100 transition hover:bg-violet-50 lg:flex lg:h-screen lg:items-stretch lg:justify-center"
      >
        <span className="my-auto h-16 w-1 rounded-full bg-slate-300 transition group-hover:bg-violet-400" />
      </button>
      <section className="flex min-h-screen min-w-0 flex-col lg:h-screen lg:min-h-0">
        <Header session={session} sessionId={sessionId} />
        <Timeline />
        <Composer sessionId={sessionId} />
      </section>
      <button
        type="button"
        aria-label="调整右侧栏宽度"
        onPointerDown={startDrag('right')}
        className="group hidden cursor-col-resize bg-slate-100 transition hover:bg-violet-50 lg:flex lg:h-screen lg:items-stretch lg:justify-center"
      >
        <span className="my-auto h-16 w-1 rounded-full bg-slate-300 transition group-hover:bg-violet-400" />
      </button>
      <RightRail />
    </main>
  )
}
