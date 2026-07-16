export const MEDIA_ASPECT_RATIOS = ['16:9', '3:2', '4:3', '1:1', '3:4', '9:16'] as const

export type MediaAspectRatio = (typeof MEDIA_ASPECT_RATIOS)[number]

export type VisualBrief = {
  sceneDescription: string
  subjects: string[]
  environment: string
  action: string
  composition: string
  moodLighting: string
  style: string
  negativeConstraints: string
  aspectRatio: MediaAspectRatio
}

export type MediaProvider = {
  key: string
  displayName: string
  kind: string
  available: boolean
  reason: string
}

export type MediaProviderCatalog = {
  defaultKey: string
  providers: MediaProvider[]
}

export type MediaSourceTurn = {
  turnId: number
  roles: string[]
  preview: string
  messageCount: number
}

export type MediaSourceTurns = {
  turns: MediaSourceTurn[]
  shortcuts: number[]
  maxTurns: number
}

export type MediaBrief = {
  startTurnId: number
  endTurnId: number
  sourceFingerprint: string
  brief: VisualBrief
}

export type MediaJobStatus =
  | 'queued'
  | 'running'
  | 'cancelling'
  | 'succeeded'
  | 'failed'
  | 'cancelled'
  | 'interrupted'

export type MediaJob = {
  jobId: string
  sessionId: string
  providerKey: string
  status: MediaJobStatus
  startTurnId: number
  endTurnId: number
  sourceFingerprint: string
  visualBrief: VisualBrief
  generationParams: Record<string, unknown>
  outputAssetId: string | null
  retryOfJobId: string | null
  errorCode: string
  errorMessage: string
  createdAt: string
  updatedAt: string
  startedAt: string
  finishedAt: string
}

export type MediaSourceReference = {
  startTurnId: number
  endTurnId: number
  fingerprint: string
  stale: boolean
}

export type MediaGalleryItem = {
  assetId: string
  jobId: string | null
  providerKey: string
  sha256: string
  mimeType: string
  byteSize: number
  visualBrief: VisualBrief
  source: MediaSourceReference
  createdAt: string
}

export type MediaGallery = {
  items: MediaGalleryItem[]
  activeJobs: MediaJob[]
  recentJobs: MediaJob[]
}

export type MediaBackground = {
  background: MediaDisplayAsset | null
  sourceMode: 'none' | 'manual' | 'auto' | 'story_default'
  manualLocked: boolean
  revisionToken: string
  lastDecision: string
  lastReason: string
  latestEvaluation: MediaBackgroundEvaluation | null
}

export type MediaDisplayAsset = {
  assetId: string
  libraryItemId: string | null
  origin: 'generated' | 'upload'
  mimeType: string
  byteSize: number
  title: string
  tags: string[]
  createdAt: string
}

export type MediaBackgroundEvaluationStatus =
  | 'queued'
  | 'running'
  | 'succeeded'
  | 'failed'
  | 'superseded'
  | 'skipped_manual'
  | 'interrupted'

export type MediaBackgroundEvaluation = {
  evaluationId: string
  sessionId: string
  status: MediaBackgroundEvaluationStatus
  targetTurnId: number
  decision: '' | 'keep' | 'switch'
  selectedAssetId: string | null
  reason: string
  errorCode: string
  errorMessage: string
  createdAt: string
  updatedAt: string
  startedAt: string
  finishedAt: string
}

export type MediaLibraryScope = 'story' | 'workspace_fallback'

export type MediaLibraryItem = {
  itemId: string
  assetId: string
  workspaceId: string
  scope: MediaLibraryScope
  storyId: number | null
  title: string
  description: string
  tags: string[]
  isDefault: boolean
  origin: 'generated' | 'upload'
  mimeType: string
  byteSize: number
  createdAt: string
  updatedAt: string
}

export type MediaLibrary = {
  items: MediaLibraryItem[]
}

export type MediaImageMetadata = {
  title: string
  description: string
  tags: string[]
}

export type MediaLibraryReconcileResult = {
  workspaceId: string
  scannedBlobs: number
  removedBlobs: number
  removedAssets: number
  removedLibraryItems: number
  removedGalleryItems: number
  clearedBackgrounds: number
}

export type MediaLibraryMetadataInput = {
  scope: MediaLibraryScope
  storyId: number | null
  title: string
  description: string
  tags: string[]
  isDefault: boolean
}

export type CreateMediaJobInput = {
  providerKey: string | null
  startTurnId: number
  endTurnId: number
  sourceFingerprint: string
  visualBrief: VisualBrief
  generationParams?: Record<string, unknown>
}
