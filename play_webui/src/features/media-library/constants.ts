import type { MediaLibraryType } from '@/types/media'

export const MEDIA_TYPE_LABELS: Record<MediaLibraryType, string> = {
  background: '背景',
  avatar: '头像',
  character_sprite: '角色立绘',
  scene_illustration: '场景插画',
  map: '地图',
  item: '物品',
  ui: 'UI 素材',
  reference: '参考图',
  other: '其他',
}

export function parseTags(value: string) {
  const tags = value
    .split(/[,，\n]/)
    .map((tag) => tag.trim())
    .filter(Boolean)
  const seen = new Set<string>()
  return tags.filter((tag) => {
    const key = tag.toLocaleLowerCase()
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
}

export function formatBytes(value: number) {
  if (value < 1024 * 1024) return `${Math.max(1, Math.round(value / 1024))} KB`
  return `${(value / 1024 / 1024).toFixed(1)} MB`
}

export function formatMediaDate(value: string) {
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(parsed)
}
