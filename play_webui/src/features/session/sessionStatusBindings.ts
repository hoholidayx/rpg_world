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

function storyStatusMount(table: StatusTable) {
  const mount = table.metadata.storyStatusMount
  return mount && typeof mount === 'object' && !Array.isArray(mount)
    ? mount as Record<string, unknown>
    : null
}

export function resolveStatusBinding(
  table: StatusTable,
  characters: CharacterCard[],
): ResolvedStatusBinding {
  const mount = storyStatusMount(table)
  if (!mount) return { kind: 'global' }

  const mountId = positiveInt(mount.characterMountId)
  const characterId = positiveInt(mount.characterId)
  const characterName = typeof mount.characterName === 'string'
    ? mount.characterName.trim()
    : ''
  const explicit = mountId !== null || characterId !== null || Boolean(characterName)
  if (!explicit) return { kind: 'global' }

  const character = (
    (mountId !== null
      ? characters.find((item) => item.mountId === mountId)
      : undefined)
    ?? (characterId !== null
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
