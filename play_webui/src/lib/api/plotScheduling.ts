import { playApiFetch, playApiFetchNoContent } from './client'
import type {
  PlotEvent,
  PlotEventInput,
  PlotEventPool,
  PlotNodeInput,
  PlotOutline,
  PlotOutlineInput,
  PlotOutlineNode,
  PlotOverrides,
  PlotPoolInput,
  PlotSchedule,
  SessionPlotSchedule,
} from '@/types/plotScheduling'

function storyPath(workspaceId: string, storyId: number) {
  return `/workspaces/${encodeURIComponent(workspaceId)}/stories/${encodeURIComponent(storyId)}/plot-scheduling`
}

function sessionPath(sessionId: string) {
  return `/sessions/${encodeURIComponent(sessionId)}/plot-scheduling`
}

export function getStoryPlotSchedule(workspaceId: string, storyId: number) {
  return playApiFetch<PlotSchedule>(storyPath(workspaceId, storyId))
}

export function createPlotPool(workspaceId: string, storyId: number, input: PlotPoolInput) {
  return playApiFetch<PlotEventPool>(`${storyPath(workspaceId, storyId)}/pools`, {
    method: 'POST', body: JSON.stringify(input),
  })
}

export function updatePlotPool(workspaceId: string, storyId: number, poolId: number, input: Partial<PlotPoolInput>) {
  return playApiFetch<PlotEventPool>(`${storyPath(workspaceId, storyId)}/pools/${poolId}`, {
    method: 'PATCH', body: JSON.stringify(input),
  })
}

export function deletePlotPool(workspaceId: string, storyId: number, poolId: number) {
  return playApiFetchNoContent(`${storyPath(workspaceId, storyId)}/pools/${poolId}`, { method: 'DELETE' })
}

export function createPlotEvent(workspaceId: string, storyId: number, input: PlotEventInput) {
  return playApiFetch<PlotEvent>(`${storyPath(workspaceId, storyId)}/events`, {
    method: 'POST', body: JSON.stringify(input),
  })
}

export function updatePlotEvent(workspaceId: string, storyId: number, eventId: number, input: Partial<PlotEventInput>) {
  return playApiFetch<PlotEvent>(`${storyPath(workspaceId, storyId)}/events/${eventId}`, {
    method: 'PATCH', body: JSON.stringify(input),
  })
}

export function deletePlotEvent(workspaceId: string, storyId: number, eventId: number) {
  return playApiFetchNoContent(`${storyPath(workspaceId, storyId)}/events/${eventId}`, { method: 'DELETE' })
}

export function reorderPlotEvents(workspaceId: string, storyId: number, poolId: number, ids: number[]) {
  return playApiFetch<PlotEvent[]>(`${storyPath(workspaceId, storyId)}/pools/${poolId}/event-order`, {
    method: 'PUT', body: JSON.stringify({ ids }),
  })
}

export function createPlotOutline(workspaceId: string, storyId: number, input: PlotOutlineInput) {
  return playApiFetch<PlotOutline>(`${storyPath(workspaceId, storyId)}/outlines`, {
    method: 'POST', body: JSON.stringify(input),
  })
}

export function updatePlotOutline(workspaceId: string, storyId: number, outlineId: number, input: Partial<PlotOutlineInput>) {
  return playApiFetch<PlotOutline>(`${storyPath(workspaceId, storyId)}/outlines/${outlineId}`, {
    method: 'PATCH', body: JSON.stringify(input),
  })
}

export function deletePlotOutline(workspaceId: string, storyId: number, outlineId: number) {
  return playApiFetchNoContent(`${storyPath(workspaceId, storyId)}/outlines/${outlineId}`, { method: 'DELETE' })
}

export function createPlotNode(workspaceId: string, storyId: number, outlineId: number, input: PlotNodeInput) {
  return playApiFetch<PlotOutlineNode>(`${storyPath(workspaceId, storyId)}/outlines/${outlineId}/nodes`, {
    method: 'POST', body: JSON.stringify(input),
  })
}

export function updatePlotNode(workspaceId: string, storyId: number, outlineId: number, nodeId: number, input: Partial<PlotNodeInput>) {
  return playApiFetch<PlotOutlineNode>(`${storyPath(workspaceId, storyId)}/outlines/${outlineId}/nodes/${nodeId}`, {
    method: 'PATCH', body: JSON.stringify(input),
  })
}

export function deletePlotNode(workspaceId: string, storyId: number, outlineId: number, nodeId: number) {
  return playApiFetchNoContent(`${storyPath(workspaceId, storyId)}/outlines/${outlineId}/nodes/${nodeId}`, { method: 'DELETE' })
}

export function reorderPlotNodes(workspaceId: string, storyId: number, outlineId: number, ids: number[]) {
  return playApiFetch<PlotOutlineNode[]>(`${storyPath(workspaceId, storyId)}/outlines/${outlineId}/node-order`, {
    method: 'PUT', body: JSON.stringify({ ids }),
  })
}

export function getSessionPlotSchedule(sessionId: string, options: { beforeId?: number; limit?: number } = {}) {
  const params = new URLSearchParams()
  if (options.beforeId !== undefined) params.set('beforeId', String(options.beforeId))
  if (options.limit !== undefined) params.set('limit', String(options.limit))
  const query = params.toString()
  return playApiFetch<SessionPlotSchedule>(`${sessionPath(sessionId)}${query ? `?${query}` : ''}`)
}

export function setPlotEventOverride(sessionId: string, eventId: number, disabled: boolean) {
  return playApiFetch<PlotOverrides>(`${sessionPath(sessionId)}/event-overrides/${eventId}`, {
    method: 'PUT', body: JSON.stringify({ disabled }),
  })
}

export function setPlotNodeOverride(sessionId: string, nodeId: number, disabled: boolean) {
  return playApiFetch<PlotOverrides>(`${sessionPath(sessionId)}/node-overrides/${nodeId}`, {
    method: 'PUT', body: JSON.stringify({ disabled }),
  })
}
