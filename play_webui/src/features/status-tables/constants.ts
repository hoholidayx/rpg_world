import {
  STATUS_KIND,
  STATUS_ORIGIN,
  type StatusKind,
  type StatusOrigin,
} from '@/types/statusTables'

export const STATUS_TABLE_VIEW = {
  STORY: 'story',
  RUNTIME: 'runtime',
} as const

export type StatusTableView = (typeof STATUS_TABLE_VIEW)[keyof typeof STATUS_TABLE_VIEW]

export const DEFAULT_KEY_COLUMN = '属性'
export const DEFAULT_VALUE_COLUMN = '值'

export const STATUS_TABLE_NAMES: Record<StatusKind, string> = {
  [STATUS_KIND.SCENE]: '未命名场景',
  [STATUS_KIND.NORMAL]: '未命名状态表',
}

export const STATUS_KIND_LABELS: Record<StatusKind, string> = {
  [STATUS_KIND.SCENE]: '场景',
  [STATUS_KIND.NORMAL]: '普通状态',
}

export const STATUS_KIND_HINTS: Record<StatusKind, string> = {
  [STATUS_KIND.SCENE]: '场景前缀',
  [STATUS_KIND.NORMAL]: '结构化上下文',
}

export const STATUS_ORIGIN_LABELS: Record<StatusOrigin, string> = {
  [STATUS_ORIGIN.STORY_COPY]: 'Story 副本',
  [STATUS_ORIGIN.SESSION_NATIVE]: '会话新建',
}

export function defaultStatusTableName(kind: StatusKind) {
  return STATUS_TABLE_NAMES[kind]
}

export function statusKindLabel(kind: StatusKind) {
  return STATUS_KIND_LABELS[kind]
}

export function statusKindHint(kind: StatusKind) {
  return STATUS_KIND_HINTS[kind]
}

export function originLabel(origin?: StatusOrigin | null) {
  return origin ? STATUS_ORIGIN_LABELS[origin] ?? '未知来源' : '未知来源'
}
