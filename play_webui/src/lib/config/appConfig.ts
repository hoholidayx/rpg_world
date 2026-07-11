import rawConfig from '../../../play_webui.config.json'

type HistoryPaginationConfig = {
  pageTurnLimit: number
  maxCachedPages: number
}

type ContextUsageConfig = {
  inputBlockThresholdRatio: number
}

type AppConfig = {
  session: {
    contextUsage: ContextUsageConfig
    historyPagination: HistoryPaginationConfig
  }
}

const DEFAULT_CONFIG: AppConfig = {
  session: {
    contextUsage: {
      inputBlockThresholdRatio: 0.9,
    },
    historyPagination: {
      pageTurnLimit: 50,
      maxCachedPages: 2,
    },
  },
}

function boundedRatio(value: unknown, fallback: number) {
  const parsed = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(parsed) || parsed <= 0 || parsed > 1) return fallback
  return parsed
}

function boundedInt(value: unknown, fallback: number, min: number, max: number) {
  const parsed = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(parsed)) return fallback
  return Math.min(max, Math.max(min, Math.trunc(parsed)))
}

function normalizeConfig(value: typeof rawConfig): AppConfig {
  return {
    session: {
      contextUsage: {
        inputBlockThresholdRatio: boundedRatio(
          value.session?.contextUsage?.inputBlockThresholdRatio,
          DEFAULT_CONFIG.session.contextUsage.inputBlockThresholdRatio,
        ),
      },
      historyPagination: {
        pageTurnLimit: boundedInt(
          value.session?.historyPagination?.pageTurnLimit,
          DEFAULT_CONFIG.session.historyPagination.pageTurnLimit,
          1,
          200,
        ),
        maxCachedPages: boundedInt(
          value.session?.historyPagination?.maxCachedPages,
          DEFAULT_CONFIG.session.historyPagination.maxCachedPages,
          2,
          5,
        ),
      },
    },
  }
}

export const appConfig = normalizeConfig(rawConfig)
export const sessionContextUsageConfig = appConfig.session.contextUsage
export const sessionHistoryPaginationConfig = appConfig.session.historyPagination
