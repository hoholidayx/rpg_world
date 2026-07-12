import { playApiFetch } from './client'
import type { RPModuleCatalog, RPModuleConfig, RPModuleConfigValues, RPModuleList } from '@/types/rpModules'

export function getRPModuleCatalog() {
  return playApiFetch<RPModuleCatalog>('/rp-modules/catalog')
}

export function getStoryRPModules(workspace: string, storyId: number) {
  return playApiFetch<RPModuleList>(
    `/workspaces/${encodeURIComponent(workspace)}/stories/${encodeURIComponent(storyId)}/rp-modules`,
  )
}

export function patchStoryRPModule(
  workspace: string,
  storyId: number,
  moduleName: string,
  payload: { enabled?: boolean; config?: RPModuleConfigValues },
) {
  return playApiFetch<RPModuleConfig>(
    `/workspaces/${encodeURIComponent(workspace)}/stories/${encodeURIComponent(storyId)}/rp-modules/${encodeURIComponent(moduleName)}`,
    { method: 'PATCH', body: JSON.stringify(payload) },
  )
}

export function getSessionRPModules(sessionId: string) {
  return playApiFetch<RPModuleList>(`/sessions/${encodeURIComponent(sessionId)}/rp-modules`)
}

export function patchSessionRPModule(
  sessionId: string,
  moduleName: string,
  payload: { enabled?: boolean | null; config?: RPModuleConfigValues },
) {
  return playApiFetch<RPModuleConfig>(
    `/sessions/${encodeURIComponent(sessionId)}/rp-modules/${encodeURIComponent(moduleName)}`,
    { method: 'PATCH', body: JSON.stringify(payload) },
  )
}

export function clearSessionRPModuleOverride(sessionId: string, moduleName: string) {
  return playApiFetch<RPModuleConfig>(
    `/sessions/${encodeURIComponent(sessionId)}/rp-modules/${encodeURIComponent(moduleName)}`,
    { method: 'DELETE' },
  )
}
