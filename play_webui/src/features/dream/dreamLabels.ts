import type {
  DreamDepth,
  DreamEpistemicStatus,
  DreamMemoryKind,
  DreamMemoryLifecycle,
  DreamProposalItemAction,
  DreamProposalStatus,
  DreamScope,
} from '@/types/dream'

export const DREAM_DEPTH_LABELS: Record<DreamDepth, string> = {
  shallow: '浅睡',
  deep: '深睡',
}

export const DREAM_SCOPE_LABELS: Record<DreamScope, string> = {
  incremental: '增量',
  full: '全量',
}

export const DREAM_STATUS_LABELS: Record<DreamProposalStatus, string> = {
  generating: '生成中',
  ready: '待确认',
  applied: '已应用',
  rejected: '已拒绝',
  failed: '失败',
  interrupted: '已中断',
  stale: '已过期',
}

export const DREAM_ACTION_LABELS: Record<DreamProposalItemAction, string> = {
  add: '新增',
  revise: '修订',
  supersede: '替代',
  retire: '退休',
}

export const DREAM_KIND_LABELS: Record<DreamMemoryKind, string> = {
  character: '角色',
  event: '事件',
  relationship: '关系',
  commitment: '承诺',
  clue: '线索',
  world_fact: '世界事实',
  state_change: '持续影响',
}

export const DREAM_EPISTEMIC_LABELS: Record<DreamEpistemicStatus, string> = {
  confirmed: '已确认',
  reported: '转述',
  inferred: '推断',
  uncertain: '不确定',
  contradicted: '已矛盾',
}

export const DREAM_LIFECYCLE_LABELS: Record<DreamMemoryLifecycle, string> = {
  active: '生效中',
  retired: '已退休',
  superseded: '已替代',
}
