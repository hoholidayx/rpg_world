'use client'

import Link from 'next/link'
import { useState } from 'react'
import {
  BookOpen,
  Check,
  ChevronDown,
  ChevronRight,
  CircleDot,
  Clock3,
  Compass,
  FolderOpen,
  Globe2,
  Home,
  Import,
  Megaphone,
  MoreHorizontal,
  Play,
  Plus,
  Settings,
  Sparkles,
  UploadCloud,
  UserRound,
  UsersRound,
} from 'lucide-react'
import type { SessionSummary, WorkspaceSummary } from '@/types/session'

const defaultWorkspace: WorkspaceSummary = {
  id: 'default',
  name: 'Default',
}

const workspaceOptions: WorkspaceSummary[] = [
  defaultWorkspace,
  {
    id: 'fog_port',
    name: 'Fog Port',
    description: '雾港测试工作区',
  },
  {
    id: 'sandbox',
    name: 'Sandbox',
    description: '沙盒工作区',
  },
]

function sessionHref(session: Pick<SessionSummary, 'id' | 'workspace'>) {
  return `/session/${session.id}?workspace=${encodeURIComponent(session.workspace)}`
}

const navItems = [
  { label: '首页', icon: Home, active: true },
  { label: '最近会话', icon: Clock3 },
  { label: '故事库', icon: BookOpen },
  { label: '角色库', icon: UsersRound },
  { label: '世界设定', icon: Globe2 },
  { label: '设置', icon: Settings },
]

const stories = [
  {
    title: '雾港',
    summary: '潮湿的港口城市，迷雾笼罩着钟楼与码头，隐秘的交易在夜色中进行。',
    status: '进行中',
    statusClass: 'bg-violet-100 text-violet-700',
    sessions: 3,
    characters: 5,
    updatedAt: '2025/05/30 14:22',
    workspace: defaultWorkspace.id,
    sessionId: 'demo_session',
    selected: true,
    artClass: 'from-slate-700 via-slate-500 to-indigo-200',
    accent: 'bg-slate-100',
  },
  {
    title: '黑市边缘',
    summary: '在秩序与混乱的缝隙中生存，每个选择都可能改变你的立场。',
    status: '进行中',
    statusClass: 'bg-emerald-100 text-emerald-700',
    sessions: 2,
    characters: 4,
    updatedAt: '2025/05/29 19:33',
    workspace: defaultWorkspace.id,
    sessionId: 'market_edge',
    artClass: 'from-emerald-900 via-emerald-600 to-emerald-100',
    accent: 'bg-emerald-100',
  },
  {
    title: '永夜之森',
    summary: '古老森林中的低语与传说，寻找失落的文明与被遗忘的真相。',
    status: '未开始',
    statusClass: 'bg-slate-100 text-slate-500',
    sessions: 1,
    characters: 3,
    updatedAt: '2025/05/20 11:11',
    workspace: defaultWorkspace.id,
    sessionId: 'forest_night',
    artClass: 'from-amber-700 via-orange-300 to-amber-50',
    accent: 'bg-amber-100',
  },
]

const recentSessions: Array<SessionSummary & {
  story: string
  place: string
  status: string
  statusClass: string
  artClass: string
}> = [
  {
    id: 'demo_session',
    workspace: defaultWorkspace.id,
    title: '雾港序章：码头钟楼下的第一幕',
    description: '适合验证 Play WebUI 基础流程，包含流式叙事、角色状态、场景切换...',
    story: '雾港',
    place: '雾港 - 码头区',
    updatedAt: '2025/05/30 14:22',
    status: '进行中',
    statusClass: 'bg-violet-100 text-violet-700',
    artClass: 'from-slate-900 via-blue-950 to-slate-400',
  },
  {
    id: 'market_edge',
    workspace: defaultWorkspace.id,
    title: '黑市边缘：旧灯笼里的第二把钥匙',
    description: '微弱的灯火晃动，门后的齿轮仍在转动。',
    story: '黑市边缘',
    place: '黑市中堂',
    updatedAt: '2025/05/28 21:07',
    status: '暂停中',
    statusClass: 'bg-sky-100 text-sky-700',
    artClass: 'from-stone-900 via-amber-950 to-stone-400',
  },
  {
    id: 'ledger_name',
    workspace: defaultWorkspace.id,
    title: '黑市余波：账本背面的名字',
    description: '账本合上，名字未被抹去，新的线索浮出水面。',
    story: '黑市边缘',
    place: '密档房',
    updatedAt: '2025/05/27 11:41',
    status: '已完成',
    statusClass: 'bg-emerald-100 text-emerald-700',
    artClass: 'from-zinc-900 via-stone-700 to-yellow-100',
  },
]

const storyStats = [
  { label: '全部故事', value: 3, icon: FolderOpen, color: 'text-slate-500' },
  { label: '进行中', value: 2, icon: CircleDot, color: 'text-emerald-500' },
  { label: '未开始', value: 1, icon: Clock3, color: 'text-slate-400' },
  { label: '已完成', value: 0, icon: Compass, color: 'text-orange-500' },
]

const quickLinks = [
  { label: '创建角色', icon: UserRound },
  { label: '导入设定', icon: Import },
  { label: '世界设定', icon: Globe2 },
  { label: '设置', icon: Settings },
]

function Logo() {
  return (
    <div className="flex items-center gap-3">
      <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-violet-500 to-indigo-500 text-white shadow-lg shadow-violet-200">
        <Sparkles size={22} fill="currentColor" />
      </div>
      <span className="text-xl font-bold text-slate-950">RPG World Play</span>
    </div>
  )
}

function MiniLandscape({ className }: { className: string }) {
  return (
    <div className={`relative h-16 w-28 shrink-0 overflow-hidden rounded-lg bg-gradient-to-br ${className}`}>
      <div className="absolute -bottom-8 left-2 h-16 w-16 rounded-full bg-white/10" />
      <div className="absolute -bottom-7 right-4 h-20 w-20 rounded-full bg-black/20" />
      <div className="absolute bottom-3 left-5 h-8 w-3 rounded-t-full bg-white/60" />
      <div className="absolute bottom-2 left-4 h-2 w-5 rounded-sm bg-white/40" />
      <div className="absolute right-4 top-4 h-2 w-2 rounded-full bg-white/70" />
    </div>
  )
}

function StoryCard({ story, workspace }: { story: (typeof stories)[number]; workspace: string }) {
  return (
    <article
      className={`rounded-xl border bg-white p-5 shadow-sm transition hover:-translate-y-0.5 hover:shadow-lg ${
        story.selected ? 'border-violet-500 shadow-violet-100' : 'border-slate-200'
      }`}
    >
      <div className="flex items-start gap-4">
        <div className={`relative h-16 w-16 shrink-0 overflow-hidden rounded-full bg-gradient-to-br ${story.artClass}`}>
          <div className="absolute bottom-0 left-2 h-8 w-12 rounded-t-full bg-white/20" />
          <div className="absolute bottom-3 left-7 h-10 w-3 rounded-t-full bg-white/60" />
          <div className="absolute bottom-1 right-3 h-3 w-6 rounded-full bg-black/20" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-3">
            <h3 className="truncate text-lg font-bold text-slate-950">{story.title}</h3>
            <span className={`rounded-full px-3 py-1 text-xs font-semibold ${story.statusClass}`}>{story.status}</span>
          </div>
          <p className="mt-2 line-clamp-2 min-h-10 text-sm leading-5 text-slate-500">{story.summary}</p>
        </div>
      </div>
      <div className="mt-6 grid grid-cols-2 gap-4 text-sm">
        <div>
          <p className="text-slate-400">会话</p>
          <p className="font-semibold text-slate-900">{story.sessions}</p>
        </div>
        <div>
          <p className="text-slate-400">角色</p>
          <p className="font-semibold text-slate-900">{story.characters}</p>
        </div>
      </div>
      <div className="mt-4 flex items-center justify-between gap-4">
        <p className="text-xs text-slate-500">更新时间&nbsp;&nbsp; {story.updatedAt}</p>
        <Link
          href={sessionHref({ id: story.sessionId, workspace })}
          className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-semibold text-slate-800 transition hover:border-violet-300 hover:text-violet-700"
        >
          查看
        </Link>
      </div>
    </article>
  )
}

function RecentSessionRow({ session, workspace }: { session: (typeof recentSessions)[number]; workspace: string }) {
  const href = sessionHref({ id: session.id, workspace })

  return (
    <article className="grid gap-4 rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-sm transition hover:border-violet-200 hover:shadow-md md:grid-cols-[auto_minmax(0,1fr)_220px_auto_auto] md:items-center">
      <MiniLandscape className={session.artClass} />
      <div className="min-w-0">
        <Link href={href} className="block truncate text-sm font-bold text-slate-950 hover:text-violet-700">
          {session.title}
        </Link>
        <p className="mt-1 truncate text-xs text-slate-500">{session.description}</p>
      </div>
      <dl className="grid gap-1 text-xs text-slate-500">
        <div className="flex gap-2">
          <dt>故事：</dt>
          <dd>{session.story}</dd>
        </div>
        <div className="flex gap-2">
          <dt>地点：</dt>
          <dd>{session.place}</dd>
        </div>
        <div className="flex gap-2">
          <dt>更新时间：</dt>
          <dd>{session.updatedAt}</dd>
        </div>
      </dl>
      <span className={`w-fit rounded-full px-3 py-1 text-xs font-semibold ${session.statusClass}`}>{session.status}</span>
      <div className="flex items-center gap-2">
        <Link
          href={href}
          aria-label={`继续 ${session.title}`}
          className="flex h-10 w-10 items-center justify-center rounded-lg border border-slate-200 text-slate-900 transition hover:border-violet-300 hover:text-violet-700"
        >
          <Play size={16} fill="currentColor" />
        </Link>
        <button className="flex h-10 w-10 items-center justify-center rounded-lg text-slate-500 transition hover:bg-slate-100" aria-label="更多">
          <MoreHorizontal size={18} />
        </button>
      </div>
    </article>
  )
}

function WorkspaceSwitcher({ value, onChange }: { value: string; onChange: (workspace: string) => void }) {
  const [open, setOpen] = useState(false)
  const selectedWorkspace = workspaceOptions.find((workspace) => workspace.id === value) ?? defaultWorkspace

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((isOpen) => !isOpen)}
        className="flex h-10 items-center gap-2 rounded-full border border-slate-200 bg-white px-3 text-sm font-medium text-slate-900 shadow-sm transition hover:border-violet-200 hover:bg-violet-50/70 hover:text-violet-700"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="切换 workspace"
      >
        <FolderOpen size={16} className="text-slate-400" />
        <span className="hidden text-slate-500 sm:inline">Workspace</span>
        <span className="max-w-28 truncate font-semibold">{selectedWorkspace.name}</span>
        <ChevronDown size={16} className={`text-slate-400 transition ${open ? 'rotate-180 text-violet-500' : ''}`} />
      </button>
      {open ? (
        <div className="absolute left-0 top-full z-40 mt-2 w-56 overflow-hidden rounded-xl border border-slate-200 bg-white p-1 shadow-xl shadow-slate-200/70" role="menu">
          {workspaceOptions.map((workspace) => {
            const selected = workspace.id === value

            return (
              <button
                key={workspace.id}
                type="button"
                onClick={() => {
                  onChange(workspace.id)
                  setOpen(false)
                }}
                className={`flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm transition ${
                  selected ? 'bg-violet-50 text-violet-700' : 'text-slate-700 hover:bg-slate-50 hover:text-slate-950'
                }`}
                role="menuitem"
              >
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-slate-500">
                  <FolderOpen size={16} />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-semibold">{workspace.name}</span>
                  {workspace.description ? <span className="mt-0.5 block truncate text-xs text-slate-500">{workspace.description}</span> : null}
                </span>
                {selected ? <Check size={16} className="shrink-0 text-violet-600" /> : null}
              </button>
            )
          })}
        </div>
      ) : null}
    </div>
  )
}

export function HomePage() {
  const [currentWorkspace, setCurrentWorkspace] = useState(defaultWorkspace.id)

  return (
    <main className="min-h-screen bg-[#f7f8fc] text-slate-900">
      <header className="sticky top-0 z-30 flex h-[72px] items-center justify-between border-b border-slate-200/80 bg-white/90 px-6 backdrop-blur">
        <div className="flex items-center gap-4">
          <Logo />
          <WorkspaceSwitcher value={currentWorkspace} onChange={setCurrentWorkspace} />
        </div>
        <div className="hidden items-center gap-10 text-sm text-slate-900 md:flex">
          <span className="flex items-center gap-2">
            <span className="h-3 w-3 rounded-full bg-emerald-500" />
            Play API mock
          </span>
          <span className="flex items-center gap-2">
            <span className="h-3 w-3 rounded-full bg-emerald-500" />
            SSE ready
          </span>
        </div>
        <button className="flex items-center gap-3 rounded-full px-2 py-1 text-sm font-medium text-slate-900 transition hover:bg-slate-100">
          <span className="flex h-10 w-10 items-center justify-center rounded-full bg-indigo-100 text-indigo-700">P</span>
          <span className="hidden sm:inline">Player One</span>
          <ChevronDown size={16} className="text-slate-400" />
        </button>
      </header>

      <div className="grid min-h-[calc(100vh-72px)] lg:grid-cols-[296px_minmax(0,1fr)]">
        <aside className="hidden border-r border-slate-200 bg-white/70 px-6 py-9 lg:flex lg:flex-col lg:justify-between">
          <nav className="space-y-3">
            {navItems.map((item) => (
              <a
                key={item.label}
                className={`flex items-center gap-4 rounded-xl px-5 py-4 text-base font-medium transition ${
                  item.active
                    ? 'bg-violet-50 text-violet-700 shadow-sm'
                    : 'text-slate-500 hover:bg-slate-100 hover:text-slate-900'
                }`}
                href="#"
              >
                <item.icon size={22} />
                {item.label}
              </a>
            ))}
          </nav>

          <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <p className="mb-4 text-sm text-slate-400">系统状态</p>
            <div className="space-y-4 text-sm text-slate-600">
              <p className="flex items-center gap-3">
                <span className="h-2 w-2 rounded-full bg-emerald-500" />
                Play API mock
              </p>
              <p className="flex items-center gap-3">
                <span className="h-2 w-2 rounded-full bg-emerald-500" />
                SSE ready
              </p>
            </div>
          </section>
        </aside>

        <div className="grid gap-6 px-5 py-8 xl:grid-cols-[minmax(0,1fr)_352px] xl:px-7">
          <section className="min-w-0 space-y-7">
            <section className="relative overflow-hidden rounded-2xl bg-white px-9 py-8 shadow-sm">
              <div className="relative z-10">
                <h1 className="text-4xl font-bold leading-tight text-slate-950">欢迎回来，Player One</h1>
                <p className="mt-3 text-lg text-slate-500">选择一个故事，继续你的冒险。</p>
              </div>
              <div className="absolute inset-y-0 right-0 hidden w-[48%] overflow-hidden md:block">
                <div className="absolute bottom-0 right-0 h-full w-full bg-gradient-to-l from-violet-100 via-indigo-50 to-transparent" />
                <div className="absolute bottom-0 right-20 h-24 w-96 rounded-[100%] bg-indigo-200/70" />
                <div className="absolute bottom-2 right-0 h-40 w-80 rounded-[100%] bg-violet-200/70" />
                <div className="absolute bottom-0 right-32 h-16 w-48 rounded-t-full bg-indigo-300/40" />
                <div className="absolute right-48 top-8 h-16 w-16 rounded-full bg-amber-100" />
                <div className="absolute bottom-4 right-24 h-1 w-32 rounded-full bg-indigo-300/60" />
                <div className="absolute bottom-6 right-28 h-0 w-0 border-b-[46px] border-l-[16px] border-r-[16px] border-b-indigo-700 border-l-transparent border-r-transparent" />
                <div className="absolute bottom-5 right-24 h-10 w-24 rounded-b-full bg-indigo-700" />
              </div>
            </section>

            <section className="rounded-2xl bg-white/60 p-6 shadow-sm">
              <div className="mb-5 flex items-center justify-between gap-4">
                <h2 className="text-xl font-bold text-slate-950">我的故事</h2>
                <button className="flex items-center gap-2 rounded-lg bg-violet-600 px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-violet-200 transition hover:bg-violet-700">
                  <Plus size={16} />
                  新建故事
                </button>
              </div>
              <div className="grid gap-5 min-[1400px]:grid-cols-2 2xl:grid-cols-3">
                {stories.map((story) => (
                  <StoryCard key={story.title} story={story} workspace={currentWorkspace} />
                ))}
              </div>
              <Link href={sessionHref({ id: 'demo_session', workspace: currentWorkspace })} className="mx-auto mt-6 flex w-fit items-center gap-2 text-sm font-medium text-violet-700">
                查看全部故事
                <ChevronRight size={16} />
              </Link>
            </section>

            <section className="rounded-2xl bg-white/60 p-6 shadow-sm">
              <div className="mb-4 flex items-center justify-between">
                <h2 className="text-xl font-bold text-slate-950">最近会话</h2>
              </div>
              <div className="space-y-3">
                {recentSessions.map((session) => (
                  <RecentSessionRow key={session.title} session={session} workspace={currentWorkspace} />
                ))}
              </div>
              <Link href={sessionHref({ id: 'demo_session', workspace: currentWorkspace })} className="mx-auto mt-6 flex w-fit items-center gap-2 text-sm font-medium text-violet-700">
                查看全部会话
                <ChevronRight size={16} />
              </Link>
            </section>
          </section>

          <aside className="space-y-4">
            <section className="rounded-2xl bg-white p-6 shadow-sm">
              <h2 className="mb-5 text-lg font-bold text-slate-950">快捷开始</h2>
              <div className="grid grid-cols-2 gap-4">
                <button className="flex items-center gap-3 rounded-lg border border-slate-200 px-4 py-3 text-sm font-medium text-slate-700 transition hover:border-violet-300 hover:text-violet-700">
                  <Plus size={18} className="text-violet-600" />
                  新建空白会话
                </button>
                <button className="flex items-center gap-3 rounded-lg border border-slate-200 px-4 py-3 text-sm font-medium text-slate-700 transition hover:border-sky-300 hover:text-sky-700">
                  <UploadCloud size={18} className="text-sky-500" />
                  导入故事设定
                </button>
                <button className="flex items-center gap-3 rounded-lg border border-slate-200 px-4 py-3 text-sm font-medium text-slate-700 transition hover:border-orange-300 hover:text-orange-700">
                  <UserRound size={18} className="text-orange-500" />
                  角色沙盒
                </button>
                <button className="flex items-center gap-3 rounded-lg border border-slate-200 px-4 py-3 text-sm font-medium text-slate-700 transition hover:border-emerald-300 hover:text-emerald-700">
                  <Globe2 size={18} className="text-emerald-500" />
                  世界设定
                </button>
              </div>
            </section>

            <section className="rounded-2xl bg-white p-6 shadow-sm">
              <h2 className="mb-5 text-lg font-bold text-slate-950">故事分类</h2>
              <div className="space-y-4">
                {storyStats.map((stat) => (
                  <div key={stat.label} className="flex items-center justify-between text-sm">
                    <span className="flex items-center gap-3 text-slate-500">
                      <stat.icon size={16} className={stat.color} />
                      {stat.label}
                    </span>
                    <span className="text-slate-600">{stat.value}</span>
                  </div>
                ))}
              </div>
            </section>

            <section className="rounded-2xl bg-white p-6 shadow-sm">
              <div className="mb-4 flex items-center gap-3">
                <h2 className="text-lg font-bold text-slate-950">公告</h2>
                <Megaphone size={16} className="text-slate-400" />
              </div>
              <p className="text-sm leading-6 text-slate-500">欢迎使用 RPG World Play。</p>
              <p className="mt-1 text-sm leading-6 text-slate-500">可以在设置中调整偏好与界面主题。</p>
            </section>

            <section className="rounded-2xl bg-white p-6 shadow-sm">
              <h2 className="mb-4 text-lg font-bold text-slate-950">快速入口</h2>
              <div className="space-y-3">
                {quickLinks.map((link) => (
                  <a
                    key={link.label}
                    href="#"
                    className="flex items-center justify-between rounded-lg px-1 py-2 text-sm text-slate-500 transition hover:text-violet-700"
                  >
                    <span className="flex items-center gap-3">
                      <link.icon size={17} />
                      {link.label}
                    </span>
                    <ChevronRight size={16} />
                  </a>
                ))}
              </div>
            </section>
          </aside>
        </div>
      </div>
    </main>
  )
}
