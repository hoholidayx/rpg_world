import type { CharacterCard, CharacterDetail, CharacterDetailInput, CharacterInput, StorySummary } from '@/types/characters'
import { getPlayApiBaseUrl } from '@/lib/config/env'
import { playApiFetch } from './client'
import { readApiError } from './errors'

export function listStories(workspace: string) {
  return playApiFetch<StorySummary[]>(`/workspaces/${encodeURIComponent(workspace)}/stories`)
}

export function listCharacters(workspace: string) {
  return playApiFetch<CharacterCard[]>(`/workspaces/${encodeURIComponent(workspace)}/characters`)
}

export function createCharacter(workspace: string, input: CharacterInput) {
  return playApiFetch<CharacterCard>(`/workspaces/${encodeURIComponent(workspace)}/characters`, {
    method: 'POST',
    body: JSON.stringify(input),
  })
}

export function updateCharacter(workspace: string, characterId: number, input: Partial<CharacterInput>) {
  return playApiFetch<CharacterCard>(`/workspaces/${encodeURIComponent(workspace)}/characters/${encodeURIComponent(characterId)}`, {
    method: 'PATCH',
    body: JSON.stringify(input),
  })
}

export async function deleteCharacter(workspace: string, characterId: number) {
  const response = await fetch(
    `${getPlayApiBaseUrl()}/workspaces/${encodeURIComponent(workspace)}/characters/${encodeURIComponent(characterId)}`,
    { method: 'DELETE' },
  )
  if (!response.ok) throw new Error(await readApiError(response))
}

export function createCharacterDetail(workspace: string, characterId: number, input: CharacterDetailInput) {
  return playApiFetch<CharacterDetail>(
    `/workspaces/${encodeURIComponent(workspace)}/characters/${encodeURIComponent(characterId)}/details`,
    {
      method: 'POST',
      body: JSON.stringify(input),
    },
  )
}

export function updateCharacterDetail(
  workspace: string,
  characterId: number,
  detailId: number,
  input: Partial<CharacterDetailInput>,
) {
  return playApiFetch<CharacterDetail>(
    `/workspaces/${encodeURIComponent(workspace)}/characters/${encodeURIComponent(characterId)}/details/${encodeURIComponent(detailId)}`,
    {
      method: 'PATCH',
      body: JSON.stringify(input),
    },
  )
}

export async function deleteCharacterDetail(workspace: string, characterId: number, detailId: number) {
  const response = await fetch(
    `${getPlayApiBaseUrl()}/workspaces/${encodeURIComponent(workspace)}/characters/${encodeURIComponent(characterId)}/details/${encodeURIComponent(detailId)}`,
    { method: 'DELETE' },
  )
  if (!response.ok) throw new Error(await readApiError(response))
}

export function listStoryCharacters(workspace: string, storyId: number) {
  return playApiFetch<CharacterCard[]>(
    `/workspaces/${encodeURIComponent(workspace)}/stories/${encodeURIComponent(storyId)}/characters`,
  )
}

export function mountCharacter(workspace: string, storyId: number, characterId: number) {
  return playApiFetch<CharacterCard>(
    `/workspaces/${encodeURIComponent(workspace)}/stories/${encodeURIComponent(storyId)}/characters/${encodeURIComponent(characterId)}/mount`,
    { method: 'POST' },
  )
}

export async function unmountCharacter(workspace: string, storyId: number, mountId: number) {
  const response = await fetch(
    `${getPlayApiBaseUrl()}/workspaces/${encodeURIComponent(workspace)}/stories/${encodeURIComponent(storyId)}/character-mounts/${encodeURIComponent(mountId)}`,
    { method: 'DELETE' },
  )
  if (!response.ok) throw new Error(await readApiError(response))
}
