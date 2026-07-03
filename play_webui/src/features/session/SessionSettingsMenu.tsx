import { PanelLeftClose, PanelRightClose, Settings } from 'lucide-react'
import { cn } from '@/lib/utils/cn'

export function SessionSettingsMenu({
  open,
  leftCollapsed,
  rightCollapsed,
  onToggleOpen,
  onToggleSide,
}: {
  open: boolean
  leftCollapsed: boolean
  rightCollapsed: boolean
  onToggleOpen: () => void
  onToggleSide: (side: 'left' | 'right') => void
}) {
  return (
    <div className="relative">
      <button
        type="button"
        aria-expanded={open}
        aria-label="设置"
        title="设置"
        onClick={onToggleOpen}
        className="flex h-10 w-10 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-600 shadow-sm transition hover:border-violet-200 hover:bg-violet-50 hover:text-violet-700"
      >
        <Settings size={18} />
      </button>

      {open ? (
        <section className="absolute right-0 top-full z-30 mt-2 w-72 overflow-hidden rounded-lg border border-slate-200 bg-white shadow-2xl shadow-slate-200/80" aria-label="会话设置菜单">
          <div className="border-b border-slate-200 px-4 py-3">
            <strong className="block text-sm font-black text-slate-950">会话设置</strong>
            <span className="mt-1 block text-xs font-semibold text-slate-400">布局与输入偏好</span>
          </div>
          <div className="p-2">
            <button
              type="button"
              onClick={() => onToggleSide('left')}
              className="grid w-full grid-cols-[34px_minmax(0,1fr)_42px] items-center gap-3 rounded-lg px-3 py-3 text-left transition hover:bg-slate-50"
            >
              <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-violet-50 text-violet-700">
                <PanelLeftClose size={16} />
              </span>
              <span className="min-w-0">
                <strong className="block text-sm font-black text-slate-900">左侧栏</strong>
                <span className="mt-0.5 block text-xs font-semibold text-slate-400">场景与角色信息</span>
              </span>
              <span className={cn('h-5 w-10 rounded-full p-0.5 transition', leftCollapsed ? 'bg-slate-200' : 'bg-teal-500')}>
                <span className={cn('block h-4 w-4 rounded-full bg-white transition', leftCollapsed ? 'translate-x-0' : 'translate-x-5')} />
              </span>
            </button>
            <button
              type="button"
              onClick={() => onToggleSide('right')}
              className="grid w-full grid-cols-[34px_minmax(0,1fr)_42px] items-center gap-3 rounded-lg px-3 py-3 text-left transition hover:bg-slate-50"
            >
              <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-sky-50 text-sky-700">
                <PanelRightClose size={16} />
              </span>
              <span className="min-w-0">
                <strong className="block text-sm font-black text-slate-900">右侧栏</strong>
                <span className="mt-0.5 block text-xs font-semibold text-slate-400">状态表</span>
              </span>
              <span className={cn('h-5 w-10 rounded-full p-0.5 transition', rightCollapsed ? 'bg-slate-200' : 'bg-teal-500')}>
                <span className={cn('block h-4 w-4 rounded-full bg-white transition', rightCollapsed ? 'translate-x-0' : 'translate-x-5')} />
              </span>
            </button>
          </div>
        </section>
      ) : null}
    </div>
  )
}
