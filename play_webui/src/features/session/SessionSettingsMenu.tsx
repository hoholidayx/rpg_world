import type { ReactNode } from 'react'
import { Boxes, Brain, CaseSensitive, PanelLeftClose, PanelRightClose, Settings, UserRound, Wrench } from 'lucide-react'
import { cn } from '@/lib/utils/cn'
import {
  SESSION_FONT_SCALE_DEFAULT,
  SESSION_FONT_SCALE_MAX,
  SESSION_FONT_SCALE_MIN,
  SESSION_FONT_SCALE_STEP,
  type SessionFontScale,
} from '@/stores/sessionUiStore'
import type { SessionPlayerCharacter } from '@/types/session'

function ToggleSetting({
  icon,
  title,
  description,
  checked,
  onChange,
}: {
  icon: ReactNode
  title: string
  description: string
  checked: boolean
  onChange: (checked: boolean) => void
}) {
  return (
    <button
      type="button"
      onClick={() => onChange(!checked)}
      className="grid w-full grid-cols-[34px_minmax(0,1fr)_42px] items-center gap-3 rounded-lg px-3 py-3 text-left transition hover:bg-slate-50 dark:hover:bg-slate-800"
    >
      {icon}
      <span className="min-w-0">
        <strong className="block text-sm font-black text-slate-900 dark:text-slate-100">{title}</strong>
        <span className="mt-0.5 block text-xs font-semibold text-slate-400 dark:text-slate-300">{description}</span>
      </span>
      <span className={cn('h-5 w-10 rounded-full p-0.5 transition', checked ? 'bg-teal-500' : 'bg-slate-200 dark:bg-slate-700')}>
        <span className={cn('block h-4 w-4 rounded-full bg-white transition', checked ? 'translate-x-5' : 'translate-x-0')} />
      </span>
    </button>
  )
}

export function SessionSettingsMenu({
  open,
  leftCollapsed,
  rightCollapsed,
  fontScale,
  showThinking,
  showTools,
  onToggleOpen,
  onToggleSide,
  onFontScaleChange,
  onResetFontScale,
  onShowThinkingChange,
  onShowToolsChange,
  playerCharacter,
  onOpenRoleDialog,
  onOpenRPModulesDialog,
}: {
  open: boolean
  leftCollapsed: boolean
  rightCollapsed: boolean
  fontScale: SessionFontScale
  showThinking: boolean
  showTools: boolean
  onToggleOpen: () => void
  onToggleSide: (side: 'left' | 'right') => void
  onFontScaleChange: (fontScale: number) => void
  onResetFontScale: () => void
  onShowThinkingChange: (show: boolean) => void
  onShowToolsChange: (show: boolean) => void
  playerCharacter?: SessionPlayerCharacter | null
  onOpenRoleDialog: () => void
  onOpenRPModulesDialog: () => void
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
              onClick={onOpenRPModulesDialog}
              className="mb-1 grid w-full grid-cols-[34px_minmax(0,1fr)_auto] items-center gap-3 rounded-lg px-3 py-3 text-left transition hover:bg-violet-50 dark:hover:bg-violet-500/10"
            >
              <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-violet-50 text-violet-700 dark:bg-violet-500/15 dark:text-violet-200">
                <Boxes size={16} />
              </span>
              <span className="min-w-0">
                <strong className="block text-sm font-black text-slate-900 dark:text-slate-100">RP Modules</strong>
                <span className="mt-0.5 block text-xs font-semibold text-slate-400 dark:text-slate-300">覆盖模块开关与会话配置</span>
              </span>
              <span className="rounded-full bg-violet-50 px-2.5 py-1 text-xs font-black text-violet-700 dark:bg-violet-500/15 dark:text-violet-200">
                编辑
              </span>
            </button>
            <div className="mb-1 rounded-lg px-3 py-3">
              <div className="grid grid-cols-[34px_minmax(0,1fr)_auto] items-center gap-3">
                <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-amber-50 text-amber-700 dark:bg-amber-500/15 dark:text-amber-200">
                  <CaseSensitive size={17} />
                </span>
                <span className="min-w-0">
                  <strong className="block text-sm font-black text-slate-900 dark:text-slate-100">字体大小</strong>
                  <span className="mt-0.5 block text-xs font-semibold text-slate-400 dark:text-slate-300">时间线与输入区</span>
                </span>
                <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-black text-slate-600 dark:bg-slate-800 dark:text-slate-200">
                  {fontScale}%
                </span>
              </div>
              <div className="mt-3 flex items-center gap-3">
                <input
                  type="range"
                  aria-label="调整字体大小"
                  min={SESSION_FONT_SCALE_MIN}
                  max={SESSION_FONT_SCALE_MAX}
                  step={SESSION_FONT_SCALE_STEP}
                  value={fontScale}
                  onChange={(event) => onFontScaleChange(Number(event.target.value))}
                  className="h-2 min-w-0 flex-1 cursor-pointer accent-violet-600"
                />
                <button
                  type="button"
                  onClick={onResetFontScale}
                  disabled={fontScale === SESSION_FONT_SCALE_DEFAULT}
                  className="h-8 rounded-lg border border-slate-200 bg-white px-3 text-xs font-black text-slate-600 transition hover:border-violet-200 hover:text-violet-700 disabled:cursor-not-allowed disabled:text-slate-300 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:border-violet-500/60 dark:hover:text-violet-200 dark:disabled:text-slate-600"
                >
                  默认
                </button>
              </div>
            </div>
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
                <span className="mt-0.5 block text-xs font-semibold text-slate-400 dark:text-slate-300">场景与固定状态</span>
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
                <span className="mt-0.5 block text-xs font-semibold text-slate-400 dark:text-slate-300">会话速览与故事归纳</span>
              </span>
              <span className={cn('h-5 w-10 rounded-full p-0.5 transition', rightCollapsed ? 'bg-slate-200 dark:bg-slate-700' : 'bg-teal-500')}>
                <span className={cn('block h-4 w-4 rounded-full bg-white transition', rightCollapsed ? 'translate-x-0' : 'translate-x-5')} />
              </span>
            </button>
            <div className="my-2 border-t border-slate-200 dark:border-slate-800" />
            <div className="px-3 pb-1 pt-2">
              <strong className="block text-xs font-black uppercase text-slate-400 dark:text-slate-500">诊断显示</strong>
            </div>
            <ToggleSetting
              title="展示思考"
              description="显示当前流式思考"
              checked={showThinking}
              onChange={onShowThinkingChange}
              icon={(
                <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-amber-50 text-amber-700 dark:bg-amber-500/15 dark:text-amber-200">
                  <Brain size={16} />
                </span>
              )}
            />
            <ToggleSetting
              title="展示工具"
              description="显示工具调用记录"
              checked={showTools}
              onChange={onShowToolsChange}
              icon={(
                <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-cyan-50 text-cyan-700 dark:bg-cyan-500/15 dark:text-cyan-200">
                  <Wrench size={16} />
                </span>
              )}
            />
          </div>
        </section>
      ) : null}
    </div>
  )
}
