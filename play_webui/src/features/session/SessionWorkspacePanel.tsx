'use client'

import type { ReactNode } from 'react'
import { SideDrawer } from '@/components/common/SideDrawer'
import { cn } from '@/lib/utils/cn'

export type SessionWorkspaceTab<T extends string> = {
  id: T
  label: string
  shortLabel?: string
  icon: ReactNode
  badge?: string | number
}

export function SessionWorkspacePanel<T extends string>({
  open,
  eyebrow,
  title,
  description,
  tabs,
  activeTab,
  onTabChange,
  onClose,
  children,
  suspended = false,
}: {
  open: boolean
  eyebrow: string
  title: string
  description: string
  tabs: SessionWorkspaceTab<T>[]
  activeTab: T
  onTabChange: (tab: T) => void
  onClose: () => void
  children: ReactNode
  suspended?: boolean
}) {
  return (
    <SideDrawer
      open={open}
      side="right"
      eyebrow={eyebrow}
      title={title}
      description={description}
      onClose={onClose}
      panelClassName="!max-w-none lg:!w-[72vw] lg:!max-w-[1320px]"
      contentClassName="!overflow-hidden !p-0"
      overlayClassName="z-[65]"
      suspended={suspended}
    >
      <div className="flex h-full min-h-0 flex-col">
        <div
          role="tablist"
          aria-label={`${title}视图`}
          className="flex shrink-0 gap-2 overflow-x-auto border-b border-slate-200 bg-white px-4 py-3 dark:border-slate-800 dark:bg-slate-950 sm:px-6"
        >
          {tabs.map((tab) => (
            <button
              key={tab.id}
              type="button"
              role="tab"
              aria-selected={activeTab === tab.id}
              onClick={() => onTabChange(tab.id)}
              className={cn(
                'inline-flex h-11 shrink-0 items-center gap-2 rounded-xl px-4 text-sm font-black transition',
                activeTab === tab.id
                  ? 'bg-slate-950 text-white shadow-lg shadow-slate-200 dark:bg-violet-600 dark:shadow-violet-950/30'
                  : 'bg-slate-100 text-slate-500 hover:bg-violet-50 hover:text-violet-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-violet-500/10 dark:hover:text-violet-200',
              )}
            >
              {tab.icon}
              <span className="hidden min-[420px]:inline">{tab.label}</span>
              <span className="min-[420px]:hidden">{tab.shortLabel ?? tab.label}</span>
              {tab.badge !== undefined ? (
                <span className={cn(
                  'rounded-full px-2 py-0.5 text-[10px]',
                  activeTab === tab.id
                    ? 'bg-white/15 text-white'
                    : 'bg-white text-slate-500 dark:bg-slate-800 dark:text-slate-300',
                )}>
                  {tab.badge}
                </span>
              ) : null}
            </button>
          ))}
        </div>
        <div role="tabpanel" className="min-h-0 flex-1 overflow-y-auto overscroll-contain bg-[#f7f8fc] p-4 dark:bg-[#0b1020] sm:p-6">
          {children}
        </div>
      </div>
    </SideDrawer>
  )
}
