import { PanelLeftClose, PanelRightClose, Settings, UserRound } from 'lucide-react'
import { cn } from '@/lib/utils/cn'
import type { SessionPlayerCharacter } from '@/types/session'

export function SessionSettingsMenu({
  open,
  leftCollapsed,
  rightCollapsed,
  onToggleOpen,
  onToggleSide,
  playerCharacter,
  onOpenRoleDialog,
}: {
  open: boolean
  leftCollapsed: boolean
  rightCollapsed: boolean
  onToggleOpen: () => void
  onToggleSide: (side: 'left' | 'right') => void
  playerCharacter?: SessionPlayerCharacter | null
  onOpenRoleDialog: () => void
}) {
  return (
    <div className="relative">
      <button
        type="button"
        aria-expanded={open}
        aria-label="设置"
        title="设置"
        onClick={onToggleOpen}
        className="flex h-10 w-10 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-600 shadow-sm transition hover:border-violet-200 hover:bg-violet-50 hover:text-violet-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:border-violet-500/60 dark:hover:bg-violet-500/10 dark:hover:text-violet-200"
      >
        <Settings size={18} />
      </button>

      {open ? (
        <section className="absolute right-0 top-full z-30 mt-2 w-72 overflow-hidden rounded-lg border border-slate-200 bg-white shadow-2xl shadow-slate-200/80 dark:border-slate-700 dark:bg-slate-950 dark:shadow-black/40" aria-label="会话设置菜单">
          <div className="border-b border-slate-200 px-4 py-3 dark:border-slate-800">
            <strong className="block text-sm font-black text-slate-950 dark:text-slate-100">会话设置</strong>
            <span className="mt-1 block text-xs font-semibold text-slate-400 dark:text-slate-300">布局与输入偏好</span>
          </div>
          <div className="p-2">
            <button
              type="button"
              onClick={onOpenRoleDialog}
              className="mb-1 grid w-full grid-cols-[34px_minmax(0,1fr)_auto] items-center gap-3 rounded-lg px-3 py-3 text-left transition hover:bg-violet-50 dark:hover:bg-violet-500/10"
            >
              {playerCharacter?.avatarUrl ? (
                <img
                  src={playerCharacter.avatarUrl}
                  alt=""
                  className="h-8 w-8 rounded-full object-cover"
                />
              ) : (
                <span className="flex h-8 w-8 items-center justify-center rounded-full bg-teal-50 text-sm font-black text-teal-700 dark:bg-teal-500/15 dark:text-teal-200">
                  {playerCharacter?.name?.slice(0, 1).toUpperCase() || <UserRound size={16} />}
                </span>
              )}
              <span className="min-w-0">
                <strong className="block truncate text-sm font-black text-slate-900 dark:text-slate-100">
                  当前扮演：{playerCharacter?.name ?? '未选择'}
                </strong>
                <span className="mt-0.5 block text-xs font-semibold text-slate-400 dark:text-slate-300">切换玩家角色</span>
              </span>
              <span className="rounded-full bg-violet-50 px-2.5 py-1 text-xs font-black text-violet-700 dark:bg-violet-500/15 dark:text-violet-200">
                切换
              </span>
            </button>
            <button
              type="button"
              onClick={() => onToggleSide('left')}
              className="grid w-full grid-cols-[34px_minmax(0,1fr)_42px] items-center gap-3 rounded-lg px-3 py-3 text-left transition hover:bg-slate-50 dark:hover:bg-slate-800"
            >
              <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-violet-50 text-violet-700 dark:bg-violet-500/15 dark:text-violet-200">
                <PanelLeftClose size={16} />
              </span>
              <span className="min-w-0">
                <strong className="block text-sm font-black text-slate-900 dark:text-slate-100">左侧栏</strong>
                <span className="mt-0.5 block text-xs font-semibold text-slate-400 dark:text-slate-300">场景与角色信息</span>
              </span>
              <span className={cn('h-5 w-10 rounded-full p-0.5 transition', leftCollapsed ? 'bg-slate-200 dark:bg-slate-700' : 'bg-teal-500')}>
                <span className={cn('block h-4 w-4 rounded-full bg-white transition', leftCollapsed ? 'translate-x-0' : 'translate-x-5')} />
              </span>
            </button>
            <button
              type="button"
              onClick={() => onToggleSide('right')}
              className="grid w-full grid-cols-[34px_minmax(0,1fr)_42px] items-center gap-3 rounded-lg px-3 py-3 text-left transition hover:bg-slate-50 dark:hover:bg-slate-800"
            >
              <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-sky-50 text-sky-700 dark:bg-sky-500/15 dark:text-sky-200">
                <PanelRightClose size={16} />
              </span>
              <span className="min-w-0">
                <strong className="block text-sm font-black text-slate-900 dark:text-slate-100">右侧栏</strong>
                <span className="mt-0.5 block text-xs font-semibold text-slate-400 dark:text-slate-300">状态表</span>
              </span>
              <span className={cn('h-5 w-10 rounded-full p-0.5 transition', rightCollapsed ? 'bg-slate-200 dark:bg-slate-700' : 'bg-teal-500')}>
                <span className={cn('block h-4 w-4 rounded-full bg-white transition', rightCollapsed ? 'translate-x-0' : 'translate-x-5')} />
              </span>
            </button>
          </div>
        </section>
      ) : null}
    </div>
  )
}
