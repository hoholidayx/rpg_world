import type { CharacterCard } from '@/types/characters'
import type { Scene } from '@/types/scene'

export function firstLetter(value?: string | null) {
  const text = value?.trim()
  return text ? text.slice(0, 1).toUpperCase() : '?'
}

export function getUiString(metadata: Record<string, unknown> | undefined, key: string) {
  const ui = metadata?.ui
  if (ui && typeof ui === 'object' && !Array.isArray(ui) && key in ui) {
    const value = (ui as Record<string, unknown>)[key]
    if (typeof value === 'string' && value) return value
  }
  return ''
}

export function getCharacterAvatarUrl(character?: CharacterCard | null) {
  return character ? getUiString(character.metadata, 'avatarUrl') : ''
}

export function characterSummary(character: CharacterCard) {
  const personality = character.personality?.trim()
  if (personality) return personality
  const content = character.content?.replace(/\s+/g, ' ').trim()
  return content ? content.slice(0, 72) : '已挂载到当前故事。'
}

export function findCharacterByName(characters: CharacterCard[], name?: string | null) {
  const target = name?.trim()
  if (!target) return null
  return characters.find((character) => character.name === target || character.name.includes(target) || target.includes(character.name)) ?? null
}

export function pickPlayerCharacter(characters: CharacterCard[]) {
  return characters[0] ?? null
}

export function formatDateTime(value?: string | null) {
  if (!value) return ''
  return value.replace('T', ' ').slice(0, 16)
}

export function formatMessageTime(value?: string | null) {
  if (!value) return '刚刚'
  const normalized = value.replace('T', ' ')
  return normalized.length >= 16 ? normalized.slice(11, 16) : normalized
}

export function stripLeadingSceneBlock(content: string) {
  return content.replace(/^\s*\[scene\][\s\S]*?\[\/scene\][\t ]*(?:\r?\n)*/i, '')
}

export function sceneRows(scene?: Scene | null) {
  if (!scene) return []
  return [
    ['地点', scene.location ?? ''],
    ['时间', scene.time ?? ''],
    ['氛围', scene.mood ?? ''],
    ['在场', scene.presentCharacters?.join('、') ?? ''],
    ...Object.entries(scene.attrs ?? {}),
  ].filter(([, value]) => value)
}
