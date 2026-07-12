import type {
  NarrativeStyle,
  NarrativeStyleInput,
  QuickReplyInput,
  SessionComposerConfig,
  StoryNarrativeStyle,
  StoryQuickReply,
  WorkspaceTurnMode,
} from '@/types/sessionComposer'
import type { InputMode } from '@/types/command'
import { playApiFetch, playApiFetchNoContent } from './client'

function workspacePath(workspaceId: string) {
  return `/workspaces/${encodeURIComponent(workspaceId)}`
}

function storyPath(workspaceId: string, storyId: number) {
  return `${workspacePath(workspaceId)}/stories/${encodeURIComponent(storyId)}`
}

export function getSessionComposer(sessionId: string) {
  return playApiFetch<SessionComposerConfig>(`/sessions/${encodeURIComponent(sessionId)}/composer`)
}

export function listWorkspaceTurnModes(workspaceId: string) {
  return playApiFetch<WorkspaceTurnMode[]>(`${workspacePath(workspaceId)}/turn-modes`)
}

export function updateWorkspaceTurnMode(
  workspaceId: string,
  mode: InputMode,
  input: { shortName: string; prompt: string },
) {
  return playApiFetch<WorkspaceTurnMode>(`${workspacePath(workspaceId)}/turn-modes/${mode}`, {
    method: 'PATCH',
    body: JSON.stringify(input),
  })
}

export function listNarrativeStyles(workspaceId: string) {
  return playApiFetch<NarrativeStyle[]>(`${workspacePath(workspaceId)}/narrative-styles`)
}

export function createNarrativeStyle(workspaceId: string, input: NarrativeStyleInput) {
  return playApiFetch<NarrativeStyle>(`${workspacePath(workspaceId)}/narrative-styles`, {
    method: 'POST',
    body: JSON.stringify(input),
  })
}

export function updateNarrativeStyle(
  workspaceId: string,
  styleId: number,
  input: Partial<NarrativeStyleInput>,
) {
  return playApiFetch<NarrativeStyle>(`${workspacePath(workspaceId)}/narrative-styles/${styleId}`, {
    method: 'PATCH',
    body: JSON.stringify(input),
  })
}

export function deleteNarrativeStyle(workspaceId: string, styleId: number) {
  return playApiFetchNoContent(`${workspacePath(workspaceId)}/narrative-styles/${styleId}`, {
    method: 'DELETE',
  })
}

export function listStoryNarrativeStyles(workspaceId: string, storyId: number) {
  return playApiFetch<StoryNarrativeStyle[]>(`${storyPath(workspaceId, storyId)}/narrative-styles`)
}

export function mountStoryNarrativeStyle(workspaceId: string, storyId: number, narrativeStyleId: number) {
  return playApiFetch<StoryNarrativeStyle>(`${storyPath(workspaceId, storyId)}/narrative-styles`, {
    method: 'POST',
    body: JSON.stringify({ narrativeStyleId }),
  })
}

export function unmountStoryNarrativeStyle(workspaceId: string, storyId: number, mountId: number) {
  return playApiFetchNoContent(`${storyPath(workspaceId, storyId)}/narrative-styles/${mountId}`, {
    method: 'DELETE',
  })
}

export function setStoryBaseNarrativeStyle(workspaceId: string, storyId: number, mountId: number | null) {
  return playApiFetch<StoryNarrativeStyle | null>(`${storyPath(workspaceId, storyId)}/narrative-styles/base`, {
    method: 'PATCH',
    body: JSON.stringify({ mountId }),
  })
}

export function listStoryQuickReplies(workspaceId: string, storyId: number) {
  return playApiFetch<StoryQuickReply[]>(`${storyPath(workspaceId, storyId)}/quick-replies`)
}

export function createStoryQuickReply(workspaceId: string, storyId: number, input: QuickReplyInput) {
  return playApiFetch<StoryQuickReply>(`${storyPath(workspaceId, storyId)}/quick-replies`, {
    method: 'POST',
    body: JSON.stringify(input),
  })
}

export function updateStoryQuickReply(
  workspaceId: string,
  storyId: number,
  replyId: number,
  input: Partial<QuickReplyInput>,
) {
  return playApiFetch<StoryQuickReply>(`${storyPath(workspaceId, storyId)}/quick-replies/${replyId}`, {
    method: 'PATCH',
    body: JSON.stringify(input),
  })
}

export function deleteStoryQuickReply(workspaceId: string, storyId: number, replyId: number) {
  return playApiFetchNoContent(`${storyPath(workspaceId, storyId)}/quick-replies/${replyId}`, {
    method: 'DELETE',
  })
}
