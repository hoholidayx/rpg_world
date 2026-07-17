export const DREAM_DEPTHS = ['shallow', 'deep'] as const
export const DREAM_SCOPES = ['incremental', 'full'] as const
export const DREAM_PROPOSAL_STATUSES = [
  'generating',
  'ready',
  'applied',
  'rejected',
  'failed',
  'interrupted',
  'stale',
] as const
export const DREAM_ITEM_ACTIONS = ['add', 'revise', 'supersede', 'retire'] as const
export const DREAM_MEMORY_LIFECYCLES = ['active', 'retired', 'superseded'] as const
export const DREAM_MEMORY_KINDS = [
  'character',
  'event',
  'relationship',
  'commitment',
  'clue',
  'world_fact',
  'state_change',
] as const
export const DREAM_EPISTEMIC_STATUSES = [
  'confirmed',
  'reported',
  'inferred',
  'uncertain',
  'contradicted',
] as const
export const DREAM_MAX_MEMORY_TEXT_CHARS = 1000

export type DreamDepth = (typeof DREAM_DEPTHS)[number]
export type DreamScope = (typeof DREAM_SCOPES)[number]
export type DreamProposalStatus = (typeof DREAM_PROPOSAL_STATUSES)[number]
export type DreamProposalItemAction = (typeof DREAM_ITEM_ACTIONS)[number]
export type DreamMemoryLifecycle = (typeof DREAM_MEMORY_LIFECYCLES)[number]
export type DreamMemoryKind = (typeof DREAM_MEMORY_KINDS)[number]
export type DreamEpistemicStatus = (typeof DREAM_EPISTEMIC_STATUSES)[number]

export type DreamEvidence = {
  messageId: number
  turnId: number
  messageVersion: number
  contentHash: string
}

export type DreamProposalItem = {
  itemId: string
  action: DreamProposalItemAction
  targetMemoryId: string | null
  baseRevisionNumber: number | null
  selected: boolean
  text: string | null
  memoryKind: DreamMemoryKind | null
  epistemicStatus: DreamEpistemicStatus | null
  salience: number | null
  reason: string
  evidence: DreamEvidence[]
}

export type DreamProposal = {
  proposalId: string
  sessionId: string
  depth: DreamDepth
  scope: DreamScope
  status: DreamProposalStatus
  ledgerRevision: number
  items: DreamProposalItem[]
  errorCode: string
  errorMessage: string
  createdAt: string
  updatedAt: string
  finishedAt: string
}

export type DreamProposalList = {
  items: DreamProposal[]
}

export type DreamProposalCreateInput = {
  depth: DreamDepth
  scope: DreamScope
  recoverProposalId?: string
}

export type DreamProposalItemPatch = {
  itemId: string
  selected: boolean
  text: string
  memoryKind: DreamMemoryKind
  epistemicStatus: DreamEpistemicStatus
  salience: number
}

export type DreamProposalPatchInput = {
  items: DreamProposalItemPatch[]
}

export type DreamMemoryRevision = {
  revisionNumber: number
  text: string
  memoryKind: DreamMemoryKind
  epistemicStatus: DreamEpistemicStatus
  salience: number
  dedupeKey: string
  proposalId: string | null
  createdAt: string
}

export type DreamMemory = {
  memoryId: string
  sessionId: string
  lifecycle: DreamMemoryLifecycle
  currentRevisionNumber: number
  supersededByMemoryId: string | null
  evidenceValid: boolean
  currentRevision: DreamMemoryRevision
  revisions: DreamMemoryRevision[]
  evidence: DreamEvidence[]
  createdAt: string
  updatedAt: string
}

export type DreamMemoryList = {
  items: DreamMemory[]
  activeCount: number
  activeLimit: number
}
