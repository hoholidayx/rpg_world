'use client'

import React, {
  Component,
  Fragment,
  type ErrorInfo,
  type ReactNode,
} from 'react'
import { AlertTriangle, Loader2, RefreshCw } from 'lucide-react'
import { SideDrawer } from '@/components/common/SideDrawer'

type SessionOptionalPanelBoundaryProps = {
  children: ReactNode
  open: boolean
  title: string
  resetKey: string
  onClose: () => void
  onError?: (error: Error, info: ErrorInfo) => void
}

type SessionOptionalPanelBoundaryState = {
  error: Error | null
  recoveryKey: number
}

export class SessionOptionalPanelBoundary extends Component<
  SessionOptionalPanelBoundaryProps,
  SessionOptionalPanelBoundaryState
> {
  state: SessionOptionalPanelBoundaryState = {
    error: null,
    recoveryKey: 0,
  }

  static getDerivedStateFromError(error: Error) {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    this.props.onError?.(error, info)
  }

  componentDidUpdate(previous: SessionOptionalPanelBoundaryProps) {
    if (previous.resetKey !== this.props.resetKey && this.state.error) {
      this.setState((current) => ({
        error: null,
        recoveryKey: current.recoveryKey + 1,
      }))
    }
  }

  private retry = () => {
    this.setState((current) => ({
      error: null,
      recoveryKey: current.recoveryKey + 1,
    }))
  }

  render() {
    if (this.state.error) {
      return (
        <SideDrawer
          open={this.props.open}
          side="right"
          eyebrow="Optional workspace recovery"
          title={`${this.props.title}暂不可用`}
          description="该工作台发生了局部渲染错误，基础聊天与历史不受影响。"
          onClose={this.props.onClose}
          overlayClassName="z-[70]"
        >
          <div
            role="alert"
            className="rounded-2xl border border-rose-200 bg-rose-50 px-5 py-8 text-center dark:border-rose-500/30 dark:bg-rose-500/10"
          >
            <AlertTriangle size={24} className="mx-auto text-rose-600 dark:text-rose-300" />
            <p className="mt-3 break-words text-sm font-bold text-rose-700 dark:text-rose-200">
              {this.state.error.message || '工作台渲染失败'}
            </p>
            <button
              type="button"
              onClick={this.retry}
              className="mt-5 inline-flex h-10 items-center gap-2 rounded-xl bg-rose-600 px-4 text-sm font-black text-white transition hover:bg-rose-700"
            >
              <RefreshCw size={15} />重新加载工作台
            </button>
          </div>
        </SideDrawer>
      )
    }

    return (
      <Fragment key={this.state.recoveryKey}>
        {this.props.children}
      </Fragment>
    )
  }
}

export function SessionOptionalPanelLoading({
  open,
  title,
  onClose,
}: {
  open: boolean
  title: string
  onClose: () => void
}) {
  return (
    <SideDrawer
      open={open}
      side="right"
      eyebrow="Loading optional workspace"
      title={title}
      description="正在按需载入工作台；基础聊天保持可用。"
      onClose={onClose}
      overlayClassName="z-[70]"
    >
      <div role="status" className="flex min-h-64 items-center justify-center">
        <div className="text-center">
          <Loader2 size={24} className="mx-auto animate-spin text-violet-600" />
          <p className="mt-3 text-sm font-bold text-slate-400">正在加载工作台…</p>
        </div>
      </div>
    </SideDrawer>
  )
}
