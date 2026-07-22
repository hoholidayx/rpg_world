import type { CharacterCard } from '@/types/characters'
import type { StatusTable } from '@/types/statusTables'

type CharacterBinding = {
  kind: 'character'
  character: CharacterCard
  name: string
}

type UnavailableBinding = {
  kind: 'unavailable'
  name: string
}

export type ResolvedStatusBinding =
  | { kind: 'global' }
  | CharacterBinding
  | UnavailableBinding

function positiveInt(value: unknown) {
  const parsed = typeof value === 'number' ? value : Number(value)
  return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : null
}

function storyStatusSource(table: StatusTable) {
  const source = table.metadata.storyStatusSource
  return source && typeof source === 'object' && !Array.isArray(source)
    ? source as Record<string, unknown>
    : null
}

export function resolveStatusBinding(
  table: StatusTable,
  characters: CharacterCard[],
): ResolvedStatusBinding {
  const source = storyStatusSource(table)
  if (!source) return { kind: 'global' }

  const characterId = positiveInt(source.characterId)
  const characterName = typeof source.characterName === 'string'
    ? source.characterName.trim()
    : ''
  const explicit = characterId !== null || Boolean(characterName)
  if (!explicit) return { kind: 'global' }

  const character = (
    (characterId !== null
      ? characters.find((item) => item.id === characterId)
      : undefined)
    ?? (characterName
      ? characters.find((item) => item.name === characterName)
      : undefined)
  )
  if (!character) {
    return { kind: 'unavailable', name: characterName }
  }
  return {
    kind: 'character',
    character,
    name: characterName || character.name,
  }
}

export function tableIsBoundToCharacter(
  table: StatusTable,
  character: CharacterCard,
  characters: CharacterCard[],
) {
  const binding = resolveStatusBinding(table, characters)
  return binding.kind === 'character' && binding.character.id === character.id
}
