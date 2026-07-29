'use client'

import dynamic from 'next/dynamic'
import React, {
  type ComponentType,
  useCallback,
  useEffect,
  useState,
} from 'react'
import {
  SessionOptionalPanelBoundary,
  SessionOptionalPanelLoading,
} from './SessionOptionalPanelBoundary'

type WorldPanelProps = Parameters<
  (typeof import('./SessionWorldPanel'))['SessionWorldPanel']
>[0]
type StoryPanelProps = Parameters<
  (typeof import('./SessionStoryPanel'))['SessionStoryPanel']
>[0]
type PlotPanelProps = Parameters<
  (typeof import('./SessionPlotStoryPanel'))['SessionPlotStoryPanel']
>[0]
type MediaPanelProps = Parameters<
  (typeof import('./SessionMediaGallery'))['SessionMediaGallery']
>[0]

type ReadyProps<Props> = Props & {
  onModuleReady: () => void
}

function withModuleReady<Props extends object>(ComponentToRender: ComponentType<Props>) {
  function ModuleReadyPanel({
    onModuleReady,
    ...componentProps
  }: ReadyProps<Props>) {
    useEffect(() => {
      onModuleReady()
    }, [onModuleReady])

    return <ComponentToRender {...componentProps as Props} />
  }

  return ModuleReadyPanel
}

const DynamicWorldPanel = dynamic<ReadyProps<WorldPanelProps>>(
  () => import('./SessionWorldPanel').then(
    (module) => withModuleReady(module.SessionWorldPanel),
  ),
  { ssr: false },
)
const DynamicStoryPanel = dynamic<ReadyProps<StoryPanelProps>>(
  () => import('./SessionStoryPanel').then(
    (module) => withModuleReady(module.SessionStoryPanel),
  ),
  { ssr: false },
)
const DynamicPlotPanel = dynamic<ReadyProps<PlotPanelProps>>(
  () => import('./SessionPlotStoryPanel').then(
    (module) => withModuleReady(module.SessionPlotStoryPanel),
  ),
  { ssr: false },
)
const DynamicMediaPanel = dynamic<ReadyProps<MediaPanelProps>>(
  () => import('./SessionMediaGallery').then(
    (module) => withModuleReady(module.SessionMediaGallery),
  ),
  { ssr: false },
)

function usePanelReady() {
  const [ready, setReady] = useState(false)
  const markReady = useCallback(() => setReady(true), [])
  return { ready, markReady }
}

export function LazySessionWorldPanel({
  activated,
  panelSessionId,
  ...props
}: WorldPanelProps & { activated: boolean; panelSessionId: string }) {
  const moduleState = usePanelReady()
  if (!activated) return null

  return (
    <>
      <SessionOptionalPanelLoading
        open={props.open && !moduleState.ready}
        title="角色与状态"
        onClose={props.onClose}
      />
      <SessionOptionalPanelBoundary
        open={props.open}
        title="角色与状态"
        resetKey={panelSessionId}
        onClose={props.onClose}
        onError={moduleState.markReady}
      >
        <DynamicWorldPanel {...props} onModuleReady={moduleState.markReady} />
      </SessionOptionalPanelBoundary>
    </>
  )
}

export function LazySessionStoryPanel({
  activated,
  ...props
}: StoryPanelProps & { activated: boolean }) {
  const moduleState = usePanelReady()
  if (!activated) return null

  return (
    <>
      <SessionOptionalPanelLoading
        open={props.open && !moduleState.ready}
        title="故事与记忆"
        onClose={props.onClose}
      />
      <SessionOptionalPanelBoundary
        open={props.open}
        title="故事与记忆"
        resetKey={props.sessionId}
        onClose={props.onClose}
        onError={moduleState.markReady}
      >
        <DynamicStoryPanel {...props} onModuleReady={moduleState.markReady} />
      </SessionOptionalPanelBoundary>
    </>
  )
}

export function LazySessionPlotPanel({
  activated,
  ...props
}: PlotPanelProps & { activated: boolean }) {
  const moduleState = usePanelReady()
  if (!activated) return null

  return (
    <>
      <SessionOptionalPanelLoading
        open={props.open && !moduleState.ready}
        title="剧情故事"
        onClose={props.onClose}
      />
      <SessionOptionalPanelBoundary
        open={props.open}
        title="剧情故事"
        resetKey={props.sessionId}
        onClose={props.onClose}
        onError={moduleState.markReady}
      >
        <DynamicPlotPanel {...props} onModuleReady={moduleState.markReady} />
      </SessionOptionalPanelBoundary>
    </>
  )
}

export function LazySessionMediaPanel({
  activated,
  ...props
}: MediaPanelProps & { activated: boolean }) {
  const moduleState = usePanelReady()
  if (!activated) return null

  return (
    <>
      <SessionOptionalPanelLoading
        open={props.open && !moduleState.ready}
        title="Session 图像工作室"
        onClose={props.onClose}
      />
      <SessionOptionalPanelBoundary
        open={props.open}
        title="Session 图像工作室"
        resetKey={props.sessionId}
        onClose={props.onClose}
        onError={moduleState.markReady}
      >
        <DynamicMediaPanel {...props} onModuleReady={moduleState.markReady} />
      </SessionOptionalPanelBoundary>
    </>
  )
}
