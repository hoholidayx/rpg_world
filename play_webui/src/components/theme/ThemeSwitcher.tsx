'use client'

import { useEffect, useRef, useState } from 'react'
import { Check, Monitor, Moon, Sun } from 'lucide-react'
import { cn } from '@/lib/utils/cn'
import { useThemeStore } from '@/stores/themeStore'
import type { ThemePreference } from '@/stores/themeStore'

const themeOptions: Array<{ value: ThemePreference; label: string; description: string; icon: typeof Sun }> = [
  { value: 'light', label: '亮色', description: '经典浅色纸面风格', icon: Sun },
  { value: 'dark', label: '暗色', description: '夜间沉浸式紫蓝色调', icon: Moon },
  { value: 'system', label: '跟随系统', description: '自动匹配设备外观', icon: Monitor },
]

type ThemeSwitcherProps = {
  menuAlign?: 'left' | 'right'
  menuSide?: 'top' | 'bottom'
  triggerSize?: 'default' | 'compact'
}

export function ThemeSwitcher({
  menuAlign = 'left',
  menuSide = 'top',
  triggerSize = 'default',
}: ThemeSwitcherProps) {
  const [open, setOpen] = useState(false)
  const wrapperRef = useRef<HTMLDivElement>(null)
  const theme = useThemeStore((state) => state.theme)
  const setTheme = useThemeStore((state) => state.setTheme)
  const selectedOption = themeOptions.find((option) => option.value === theme) ?? themeOptions[2]
  const SelectedIcon = selectedOption.icon

  useEffect(() => {
    if (!open) return
    const handlePointerDown = (event: PointerEvent) => {
      if (!wrapperRef.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('pointerdown', handlePointerDown)
    return () => document.removeEventListener('pointerdown', handlePointerDown)
  }, [open])

  return (
    <div ref={wrapperRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((isOpen) => !isOpen)}
        className={cn(
          'flex items-center justify-center border border-slate-200 bg-white text-slate-500 shadow-sm transition hover:border-violet-200 hover:bg-violet-50 hover:text-violet-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:border-violet-500/60 dark:hover:bg-violet-500/10 dark:hover:text-violet-200',
          triggerSize === 'compact' ? 'h-10 w-10 rounded-lg' : 'h-11 w-11 rounded-xl',
        )}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="切换主题"
        title="切换主题"
      >
        <SelectedIcon size={19} />
      </button>
      {open ? (
        <div
          className={`absolute z-50 w-64 overflow-hidden rounded-2xl border border-slate-200 bg-white p-2 shadow-2xl shadow-slate-200/70 dark:border-slate-700 dark:bg-slate-950 dark:shadow-black/40 ${
            menuAlign === 'right' ? 'right-0' : 'left-0'
          } ${menuSide === 'bottom' ? 'top-full mt-3' : 'bottom-full mb-3'}`}
          role="menu"
        >
          <p className="px-3 pb-2 pt-1 text-xs font-semibold uppercase tracking-[0.18em] text-slate-400 dark:text-slate-500">主题模式</p>
          {themeOptions.map((option) => {
            const Icon = option.icon
            const selected = option.value === theme
            return (
              <button
                key={option.value}
                type="button"
                onClick={() => {
                  setTheme(option.value)
                  setOpen(false)
                }}
                className={`flex w-full items-center gap-3 rounded-xl px-3 py-3 text-left transition ${
                  selected
                    ? 'bg-violet-50 text-violet-700 dark:bg-violet-500/15 dark:text-violet-100'
                    : 'text-slate-700 hover:bg-slate-50 hover:text-slate-950 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-white'
                }`}
                role="menuitemradio"
                aria-checked={selected}
              >
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-300">
                  <Icon size={17} />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-bold">{option.label}</span>
                  <span className="mt-0.5 block text-xs text-slate-500 dark:text-slate-400">{option.description}</span>
                </span>
                {selected ? <Check size={16} className="shrink-0" /> : null}
              </button>
            )
          })}
        </div>
      ) : null}
    </div>
  )
}
