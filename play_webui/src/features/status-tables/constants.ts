import {
  STATUS_KIND,
  STATUS_ORIGIN,
  STORY_STATUS_MOUNT_ORIGIN,
  type StatusKind,
  type StatusOrigin,
  type StoryStatusMountOrigin,
} from '@/types/statusTables'

export const STATUS_TABLE_VIEW = {
  SYSTEM: 'templates',
  STORY: 'storyTemplates',
  RUNTIME: 'runtime',
} as const

export type StatusTableView = (typeof STATUS_TABLE_VIEW)[keyof typeof STATUS_TABLE_VIEW]

export const DEFAULT_KEY_COLUMN = '属性'
export const DEFAULT_VALUE_COLUMN = '值'
export const DEFAULT_TEMPLATE_METADATA = { ui: {} } as const

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
  [STATUS_ORIGIN.TEMPLATE_COPY]: '模板副本',
  [STATUS_ORIGIN.SESSION_NATIVE]: '会话新建',
}

export const STORY_STATUS_MOUNT_ORIGIN_LABELS: Record<StoryStatusMountOrigin, string> = {
  [STORY_STATUS_MOUNT_ORIGIN.SYSTEM]: '系统挂载',
  [STORY_STATUS_MOUNT_ORIGIN.STORY_TEMPLATE]: '故事模板',
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

export function storyMountOriginLabel(origin: StoryStatusMountOrigin) {
  return STORY_STATUS_MOUNT_ORIGIN_LABELS[origin]
}
