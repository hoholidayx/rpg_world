import type { MainLLMProviderCatalog, MainLLMSelection } from '@/types/mainLLM'
import { playApiFetch } from './client'

export function getMainLLMOptions() {
  return playApiFetch<MainLLMProviderCatalog>('/llm/main-agent/options')
}

export function getStoryMainLLM(workspace: string, storyId: number) {
  return playApiFetch<MainLLMSelection>(
    `/workspaces/${encodeURIComponent(workspace)}/stories/${encodeURIComponent(storyId)}/main-llm`,
  )
}

export function setStoryMainLLM(workspace: string, storyId: number, providerKey: string | null) {
  return playApiFetch<MainLLMSelection>(
    `/workspaces/${encodeURIComponent(workspace)}/stories/${encodeURIComponent(storyId)}/main-llm`,
    {
      method: 'PATCH',
      body: JSON.stringify({ providerKey }),
    },
  )
}

export function getSessionMainLLM(sessionId: string) {
  return playApiFetch<MainLLMSelection>(`/sessions/${encodeURIComponent(sessionId)}/main-llm`)
}

export function setSessionMainLLM(sessionId: string, providerKey: string | null) {
  return playApiFetch<MainLLMSelection>(`/sessions/${encodeURIComponent(sessionId)}/main-llm`, {
    method: 'PATCH',
    body: JSON.stringify({ providerKey }),
  })
}
