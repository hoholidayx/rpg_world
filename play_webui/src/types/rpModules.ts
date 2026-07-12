import type { NarrativeOutcomeDefinition, NarrativeOutcomeWeights } from './narrativeOutcome'

export const RP_MODULE_NAME = {
  NARRATIVE_OUTCOME: 'narrative_outcome',
  DICE: 'dice',
} as const

export type RPModuleName = (typeof RP_MODULE_NAME)[keyof typeof RP_MODULE_NAME]

export type RPModuleConfigValues = {
  auto_adjudication_enabled?: boolean
  weights?: NarrativeOutcomeWeights
  default_dc?: number
}

export type RPModuleConfig = {
  moduleName: string
  displayName: string
  description: string
  sortOrder: number
  globalEnabled: boolean
  systemEnabled: boolean
  storyMounted: boolean
  storyEnabled: boolean
  sessionEnabledOverride: boolean | null
  effectiveEnabled: boolean
  systemConfig: RPModuleConfigValues
  storyConfig: RPModuleConfigValues
  sessionConfig: RPModuleConfigValues
  effectiveConfig: RPModuleConfigValues
  configSources: Record<string, 'config' | 'story' | 'session'>
  outcomeDefinitions: NarrativeOutcomeDefinition[] | null
}

export type RPModuleList = { modules: RPModuleConfig[] }

export type RPModuleCatalogItem = {
  moduleName: string
  displayName: string
  description: string
  sortOrder: number
  configVersion: number
  defaultStoryEnabled: boolean
  configurableFields: string[]
  outcomeDefinitions: NarrativeOutcomeDefinition[] | null
}

export type RPModuleCatalog = { modules: RPModuleCatalogItem[] }
