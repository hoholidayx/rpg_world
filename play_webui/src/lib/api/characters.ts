import type { CharacterCard, CharacterDetail, CharacterDetailInput, CharacterInput } from '@/types/characters'
import { getPlayApiBaseUrl } from '@/lib/config/env'
import { playApiFetch } from './client'
import { readApiError } from './errors'

function storyCharactersPath(workspace: string, storyId: number) {
  return `/workspaces/${encodeURIComponent(workspace)}/stories/${encodeURIComponent(storyId)}/characters`
}

export function listCharacters(workspace: string, storyId: number) {
  return playApiFetch<CharacterCard[]>(storyCharactersPath(workspace, storyId))
}

export function createCharacter(workspace: string, storyId: number, input: CharacterInput) {
  return playApiFetch<CharacterCard>(storyCharactersPath(workspace, storyId), {
    method: 'POST',
    body: JSON.stringify(input),
  })
}

export function updateCharacter(workspace: string, storyId: number, characterId: number, input: Partial<CharacterInput>) {
  return playApiFetch<CharacterCard>(`${storyCharactersPath(workspace, storyId)}/${encodeURIComponent(characterId)}`, {
    method: 'PATCH',
    body: JSON.stringify(input),
  })
}

export async function deleteCharacter(workspace: string, storyId: number, characterId: number) {
  const response = await fetch(
    `${getPlayApiBaseUrl()}${storyCharactersPath(workspace, storyId)}/${encodeURIComponent(characterId)}`,
    { method: 'DELETE' },
  )
  if (!response.ok) throw new Error(await readApiError(response))
}

export function createCharacterDetail(workspace: string, storyId: number, characterId: number, input: CharacterDetailInput) {
  return playApiFetch<CharacterDetail>(
    `${storyCharactersPath(workspace, storyId)}/${encodeURIComponent(characterId)}/details`,
    { method: 'POST', body: JSON.stringify(input) },
  )
}

export function updateCharacterDetail(
  workspace: string,
  storyId: number,
  characterId: number,
  detailId: number,
  input: Partial<CharacterDetailInput>,
) {
  return playApiFetch<CharacterDetail>(
    `${storyCharactersPath(workspace, storyId)}/${encodeURIComponent(characterId)}/details/${encodeURIComponent(detailId)}`,
    { method: 'PATCH', body: JSON.stringify(input) },
  )
}

export async function deleteCharacterDetail(workspace: string, storyId: number, characterId: number, detailId: number) {
  const response = await fetch(
    `${getPlayApiBaseUrl()}${storyCharactersPath(workspace, storyId)}/${encodeURIComponent(characterId)}/details/${encodeURIComponent(detailId)}`,
    { method: 'DELETE' },
  )
  if (!response.ok) throw new Error(await readApiError(response))
}
