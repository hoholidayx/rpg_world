export type MainLLMProviderOption = {
  providerKey: string
  backend: string
  model: string
  contextWindow?: number | null
}

export type MainLLMInvalidOverride = {
  source: 'story' | 'session'
  providerKey: string
}

export type MainLLMProviderCatalog = {
  configDefaultProviderKey: string
  options: MainLLMProviderOption[]
}

export type MainLLMSelection = {
  configDefaultProviderKey: string
  storyProviderKey?: string | null
  sessionProviderKey?: string | null
  effectiveProviderKey: string
  effectiveSource: 'config' | 'story' | 'session'
  effective: MainLLMProviderOption
  invalidOverrides: MainLLMInvalidOverride[]
}
