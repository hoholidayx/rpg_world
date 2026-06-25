'use client'

import { PointerEvent, useState } from 'react'
import { Bug, GripHorizontal, Settings, X } from 'lucide-react'

const debugEvents = [
  ['23:42:01', 'round_start'],
  ['23:42:01', 'thinking'],
  ['23:42:02', 'tool_call'],
  ['23:42:03', 'tool_result'],
  ['23:42:06', 'message_done'],
]

type PanelPosition = {
  x: number
  y: number
}

type DragState = {
  startX: number
  startY: number
  originX: number
  originY: number
}

export function DebugEventLauncher() {
  const [menuOpen, setMenuOpen] = useState(false)
  const [panelOpen, setPanelOpen] = useState(false)
  const [position, setPosition] = useState<PanelPosition>({ x: 1540, y: 150 })
  const [dragState, setDragState] = useState<DragState | null>(null)

  const startDrag = (event: PointerEvent<HTMLDivElement>) => {
    event.currentTarget.setPointerCapture(event.pointerId)
    setDragState({
      startX: event.clientX,
      startY: event.clientY,
      originX: position.x,
      originY: position.y,
    })
  }

  const movePanel = (event: PointerEvent<HTMLDivElement>) => {
    if (!dragState) return
    setPosition({
      x: Math.max(12, dragState.originX + event.clientX - dragState.startX),
      y: Math.max(12, dragState.originY + event.clientY - dragState.startY),
    })
  }

  const stopDrag = () => {
    setDragState(null)
  }

  return (
    <>
      <div className="relative">
        <button
          type="button"
          aria-expanded={menuOpen}
          aria-label="设置"
          onClick={() => setMenuOpen((current) => !current)}
          className="flex h-10 w-10 items-center justify-center rounded-xl border border-slate-200 text-slate-500 transition hover:border-violet-200 hover:text-violet-700"
        >
          <Settings size={17} />
        </button>

        {menuOpen ? (
          <div className="absolute right-0 top-12 z-40 w-44 rounded-xl border border-slate-200 bg-white p-2 shadow-xl shadow-slate-200/60">
            <button
              type="button"
              onClick={() => {
                setPosition({ x: Math.max(12, window.innerWidth - 360), y: 120 })
                setPanelOpen(true)
                setMenuOpen(false)
              }}
              className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm font-semibold text-slate-700 transition hover:bg-violet-50 hover:text-violet-700"
            >
              <Bug size={16} />
              调试事件
            </button>
          </div>
        ) : null}
      </div>

      {panelOpen ? (
        <section
          className="fixed z-50 w-80 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl shadow-slate-300/60"
          style={{ left: position.x, top: position.y }}
        >
          <div
            onPointerDown={startDrag}
            onPointerMove={movePanel}
            onPointerUp={stopDrag}
            onPointerCancel={stopDrag}
            className="flex cursor-grab touch-none items-center justify-between border-b border-slate-200 px-4 py-3 active:cursor-grabbing"
          >
            <div>
              <h2 className="text-base font-bold text-slate-950">调试事件</h2>
              <p className="text-xs text-slate-400">拖动标题栏移动面板</p>
            </div>
            <div className="flex items-center gap-2">
              <GripHorizontal size={18} className="text-slate-400" />
              <button
                type="button"
                onPointerDown={(event) => event.stopPropagation()}
                onClick={() => setPanelOpen(false)}
                className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 transition hover:bg-slate-100 hover:text-slate-700"
                aria-label="关闭调试事件"
              >
                <X size={16} />
              </button>
            </div>
          </div>
          <div>
            {debugEvents.map(([time, event]) => (
              <div key={`${time}-${event}`} className="flex items-center justify-between border-t border-slate-100 px-4 py-3 text-sm">
                <span className="font-semibold text-slate-600">{time}</span>
                <span className="text-slate-500">{event}</span>
              </div>
            ))}
          </div>
        </section>
      ) : null}
    </>
  )
}
