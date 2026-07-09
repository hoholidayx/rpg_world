import type { CharacterCard } from '@/types/characters'
import type { SessionSummary } from '@/types/session'
import type { StatusTable } from '@/types/statusTables'

export function formatDate(value?: string | null) {
  if (!value) return '暂无'
  return value.replace('T', ' ').slice(0, 16)
}

export function characterLabelByMountId(characters: CharacterCard[], mountId?: number | null) {
  if (!mountId) return '无绑定'
  const character = characters.find((item) => item.mountId === mountId)
  return character ? character.name : `角色挂载 #${mountId}`
}

export function templateNameById(templates: StatusTable[], templateId: number) {
  return templates.find((template) => template.id === templateId)?.name ?? '源模板'
}

export function selectedSessionLabel(session: SessionSummary | null) {
  if (!session) return '暂无'
  return session.title || session.id
}
