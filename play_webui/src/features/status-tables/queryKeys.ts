export const statusTableQueryKeys = {
  stories: (workspace?: string | null) => ['play-stories', workspace] as const,
  statusTemplates: (workspace?: string | null) => ['play-status-templates', workspace] as const,
  sessions: (workspace?: string | null, storyId?: number | null) => ['play-sessions', workspace, storyId] as const,
  sessionStatusTables: (sessionId?: string | null) => ['play-session-status-tables', sessionId] as const,
  storyCharacters: (workspace?: string | null, storyId?: number | null) => ['play-story-characters', workspace, storyId] as const,
  storyStatusMounts: (workspace?: string | null, storyId?: number | null) => ['play-story-status-mounts', workspace, storyId] as const,
}
