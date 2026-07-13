import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import { listStoryCharacters } from '@/lib/api/characters'
import { listSessions } from '@/lib/api/sessions'
import {
  createSessionStatusTable,
  createStatusTemplate,
  createStoryStatusTemplate,
  deleteSessionStatusTable,
  deleteStatusTemplate,
  deleteStoryStatusTemplate,
  listSessionStatusTables,
  listStatusTemplates,
  listStoryStatusMounts,
  mountStatusTemplate,
  unmountStatusTemplate,
  updateSessionStatusTable,
  updateStatusTemplate,
  updateStoryStatusMount,
} from '@/lib/api/statusTables'
import { listStories } from '@/lib/api/stories'
import { STORY_STATUS_MOUNT_ORIGIN, type StatusKind, type StatusTable } from '@/types/statusTables'
import {
  DEFAULT_KEY_COLUMN,
  DEFAULT_TEMPLATE_METADATA,
  DEFAULT_VALUE_COLUMN,
  STATUS_TABLE_VIEW,
  type StatusTableView,
  defaultStatusTableName,
} from './constants'
import {
  createEmptyDraft,
  draftFromTable,
  uniqueStatusTableName,
  validateRows,
  type TableDraft,
} from './draft'
import { statusTableQueryKeys } from './queryKeys'

export function useStatusTablesController(currentWorkspace?: string | null) {
  const queryClient = useQueryClient()
  const [view, setView] = useState<StatusTableView>(STATUS_TABLE_VIEW.SYSTEM)
  const [selectedTemplateId, setSelectedTemplateId] = useState<number | null>(null)
  const [selectedStoryId, setSelectedStoryId] = useState<number | null>(null)
  const [selectedStoryMountId, setSelectedStoryMountId] = useState<number | null>(null)
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null)
  const [selectedRuntimeTableId, setSelectedRuntimeTableId] = useState<number | null>(null)
  const [templateDraft, setTemplateDraft] = useState<TableDraft>(() => createEmptyDraft())
  const [storyTemplateDraft, setStoryTemplateDraft] = useState<TableDraft>(() => createEmptyDraft())
  const [runtimeDraft, setRuntimeDraft] = useState<TableDraft>(() => createEmptyDraft())
  const [formError, setFormError] = useState('')
  const [createTemplateOpen, setCreateTemplateOpen] = useState(false)
  const [createStoryTemplateOpen, setCreateStoryTemplateOpen] = useState(false)
  const [createRuntimeOpen, setCreateRuntimeOpen] = useState(false)
  const [mountDialogOpen, setMountDialogOpen] = useState(false)
  const [copyTargetStoryId, setCopyTargetStoryId] = useState<number | null>(null)
  const [copySessionId, setCopySessionId] = useState<string | null>(null)
  const [deleteTemplateOpen, setDeleteTemplateOpen] = useState(false)
  const [deleteStoryTemplateOpen, setDeleteStoryTemplateOpen] = useState(false)
  const [deleteRuntimeOpen, setDeleteRuntimeOpen] = useState(false)

  const storiesQuery = useQuery({
    queryKey: statusTableQueryKeys.stories(currentWorkspace),
    queryFn: () => listStories(currentWorkspace ?? ''),
    enabled: Boolean(currentWorkspace),
  })
  const templatesQuery = useQuery({
    queryKey: statusTableQueryKeys.statusTemplates(currentWorkspace),
    queryFn: () => listStatusTemplates(currentWorkspace ?? ''),
    enabled: Boolean(currentWorkspace),
  })
  const sessionsQuery = useQuery({
    queryKey: statusTableQueryKeys.sessions(currentWorkspace, selectedStoryId),
    queryFn: () => listSessions(currentWorkspace ?? '', selectedStoryId ?? 0),
    enabled: Boolean(currentWorkspace && selectedStoryId),
  })
  const runtimeTablesQuery = useQuery({
    queryKey: statusTableQueryKeys.sessionStatusTables(selectedSessionId),
    queryFn: () => listSessionStatusTables(selectedSessionId ?? ''),
    enabled: Boolean(selectedSessionId),
  })
  const storyCharactersQuery = useQuery({
    queryKey: statusTableQueryKeys.storyCharacters(currentWorkspace, selectedStoryId),
    queryFn: () => listStoryCharacters(currentWorkspace ?? '', selectedStoryId ?? 0),
    enabled: Boolean(currentWorkspace && selectedStoryId),
  })

  const stories = storiesQuery.data ?? []
  const templates = templatesQuery.data ?? []
  const sessions = sessionsQuery.data ?? []
  const runtimeTables = runtimeTablesQuery.data ?? []
  const storyCharacters = storyCharactersQuery.data ?? []
  const copyTargetStory = stories.find((story) => story.id === copyTargetStoryId) ?? null

  const copySessionsQuery = useQuery({
    queryKey: statusTableQueryKeys.sessions(currentWorkspace, copyTargetStory?.id),
    queryFn: () => listSessions(currentWorkspace ?? '', copyTargetStory?.id ?? 0),
    enabled: Boolean(currentWorkspace && copyTargetStory),
  })
  const copySessions = copySessionsQuery.data ?? []

  const storyMountQueries = useQueries({
    queries: stories.map((story) => ({
      queryKey: statusTableQueryKeys.storyStatusMounts(currentWorkspace, story.id),
      queryFn: () => listStoryStatusMounts(currentWorkspace ?? '', story.id),
      enabled: Boolean(currentWorkspace),
    })),
  })

  const storyMountGroups = useMemo(
    () => stories.map((story, index) => ({ story, mounts: storyMountQueries[index]?.data ?? [] })),
    [stories, storyMountQueries],
  )
  const storyTemplateIds = useMemo(() => {
    const ids = new Set<number>()
    storyMountGroups.forEach((group) => {
      group.mounts.forEach((mount) => {
        if (mount.mountOrigin === STORY_STATUS_MOUNT_ORIGIN.STORY_TEMPLATE) ids.add(mount.statusTableId)
      })
    })
    return ids
  }, [storyMountGroups])
  const systemTemplates = useMemo(
    () => templates.filter((table) => !storyTemplateIds.has(table.id)),
    [storyTemplateIds, templates],
  )
  const mountedTemplateIds = useMemo(() => {
    const ids = new Set<number>()
    storyMountGroups.forEach((group) => {
      group.mounts.forEach((mount) => ids.add(mount.statusTableId))
    })
    return ids
  }, [storyMountGroups])
  const selectedTemplate = systemTemplates.find((table) => table.id === selectedTemplateId) ?? null
  const selectedTemplateMounts = useMemo(
    () => storyMountGroups.flatMap((group) => (
      group.mounts
        .filter((mount) => selectedTemplate && mount.statusTableId === selectedTemplate.id)
        .map((mount) => ({ story: group.story, mount }))
    )),
    [selectedTemplate, storyMountGroups],
  )
  const selectedTemplateMountedStoryIds = useMemo(
    () => new Set(selectedTemplateMounts.map(({ story }) => story.id)),
    [selectedTemplateMounts],
  )
  const selectedStoryMounts = useMemo(
    () => storyMountGroups.find((group) => group.story.id === selectedStoryId)?.mounts ?? [],
    [selectedStoryId, storyMountGroups],
  )
  const selectedStoryMount = selectedStoryMounts.find((mount) => mount.id === selectedStoryMountId) ?? null
  const selectedStoryTemplate = templates.find((table) => selectedStoryMount && table.id === selectedStoryMount.statusTableId) ?? null
  const selectedStory = stories.find((story) => story.id === selectedStoryId) ?? null
  const selectedRuntimeTable = runtimeTables.find((table) => table.id === selectedRuntimeTableId) ?? null
  const selectedSession = sessions.find((session) => session.id === selectedSessionId) ?? null

  useEffect(() => {
    if (!selectedTemplateId && systemTemplates.length) setSelectedTemplateId(systemTemplates[0].id)
    if (selectedTemplateId && systemTemplates.length && !systemTemplates.some((table) => table.id === selectedTemplateId)) {
      setSelectedTemplateId(systemTemplates[0].id)
    }
    if (!systemTemplates.length && selectedTemplateId !== null) setSelectedTemplateId(null)
  }, [selectedTemplateId, systemTemplates])

  useEffect(() => {
    setTemplateDraft(draftFromTable(selectedTemplate))
    setFormError('')
  }, [selectedTemplate])

  useEffect(() => {
    if (!selectedStoryId && stories.length) setSelectedStoryId(stories[0].id)
    if (selectedStoryId && stories.length && !stories.some((story) => story.id === selectedStoryId)) {
      setSelectedStoryId(stories[0].id)
    }
  }, [selectedStoryId, stories])

  useEffect(() => {
    if (!selectedStoryMountId && selectedStoryMounts.length) setSelectedStoryMountId(selectedStoryMounts[0].id)
    if (selectedStoryMountId && selectedStoryMounts.length && !selectedStoryMounts.some((mount) => mount.id === selectedStoryMountId)) {
      setSelectedStoryMountId(selectedStoryMounts[0].id)
    }
    if (!selectedStoryMounts.length) setSelectedStoryMountId(null)
  }, [selectedStoryMountId, selectedStoryMounts])

  useEffect(() => {
    setStoryTemplateDraft(draftFromTable(selectedStoryTemplate))
    setFormError('')
  }, [selectedStoryTemplate])

  useEffect(() => {
    if (!selectedSessionId && sessions.length) setSelectedSessionId(sessions[0].id)
    if (selectedSessionId && sessions.length && !sessions.some((session) => session.id === selectedSessionId)) {
      setSelectedSessionId(sessions[0].id)
    }
    if (!sessions.length) setSelectedSessionId(null)
  }, [selectedSessionId, sessions])

  useEffect(() => {
    if (!selectedRuntimeTableId && runtimeTables.length) setSelectedRuntimeTableId(runtimeTables[0].id)
    if (selectedRuntimeTableId && runtimeTables.length && !runtimeTables.some((table) => table.id === selectedRuntimeTableId)) {
      setSelectedRuntimeTableId(runtimeTables[0].id)
    }
    if (!runtimeTables.length) setSelectedRuntimeTableId(null)
  }, [runtimeTables, selectedRuntimeTableId])

  useEffect(() => {
    setRuntimeDraft(draftFromTable(selectedRuntimeTable))
    setFormError('')
  }, [selectedRuntimeTable])

  useEffect(() => {
    if (!copyTargetStory) {
      if (copySessionId !== null) setCopySessionId(null)
      return
    }
    if (!copySessions.length) {
      if (copySessionId !== null) setCopySessionId(null)
      return
    }
    if (!copySessionId || !copySessions.some((session) => session.id === copySessionId)) {
      setCopySessionId(copySessions[0].id)
    }
  }, [copyTargetStory, copySessionId, copySessions])

  const invalidateTemplates = () => {
    queryClient.invalidateQueries({ queryKey: statusTableQueryKeys.statusTemplates(currentWorkspace) })
    storyMountGroups.forEach((group) => {
      queryClient.invalidateQueries({ queryKey: statusTableQueryKeys.storyStatusMounts(currentWorkspace, group.story.id) })
    })
  }

  const invalidateRuntimeTables = () => {
    queryClient.invalidateQueries({ queryKey: statusTableQueryKeys.sessionStatusTables(selectedSessionId) })
  }

  const upsertTemplateCache = (table: StatusTable) => {
    if (!currentWorkspace) return
    queryClient.setQueryData<StatusTable[]>(statusTableQueryKeys.statusTemplates(currentWorkspace), (current) => {
      if (!current) return [table]
      if (current.some((item) => item.id === table.id)) {
        return current.map((item) => (item.id === table.id ? table : item))
      }
      return [...current, table]
    })
  }

  const createTemplateMutation = useMutation({
    mutationFn: (kind: StatusKind) => {
      if (!currentWorkspace) throw new Error('workspace missing')
      return createStatusTemplate(currentWorkspace, {
        name: defaultStatusTableName(kind),
        statusKind: kind,
        description: '',
        keyColumn: DEFAULT_KEY_COLUMN,
        valueColumn: DEFAULT_VALUE_COLUMN,
        rows: [],
        metadata: DEFAULT_TEMPLATE_METADATA,
      })
    },
    onSuccess: (table) => {
      upsertTemplateCache(table)
      setSelectedTemplateId(table.id)
      setCreateTemplateOpen(false)
      invalidateTemplates()
    },
    onError: (error) => setFormError(error instanceof Error ? error.message : '新增模板失败'),
  })

  const createStoryTemplateMutation = useMutation({
    mutationFn: ({ kind, characterMountId }: { kind: StatusKind; characterMountId: number | null }) => {
      if (!currentWorkspace || !selectedStoryId) throw new Error('story missing')
      const nextSortOrder = selectedStoryMounts.reduce((max, mount) => Math.max(max, mount.sortOrder), 0) + 10
      return createStoryStatusTemplate(currentWorkspace, selectedStoryId, {
        name: defaultStatusTableName(kind),
        statusKind: kind,
        description: '',
        keyColumn: DEFAULT_KEY_COLUMN,
        valueColumn: DEFAULT_VALUE_COLUMN,
        rows: [],
        metadata: DEFAULT_TEMPLATE_METADATA,
        sortOrder: nextSortOrder,
        characterMountId,
      })
    },
    onSuccess: (mount) => {
      setSelectedStoryMountId(mount.id)
      setCreateStoryTemplateOpen(false)
      invalidateTemplates()
    },
    onError: (error) => setFormError(error instanceof Error ? error.message : '新增故事状态模板失败'),
  })

  const saveTemplateMutation = useMutation({
    mutationFn: () => {
      if (!currentWorkspace || !selectedTemplate) throw new Error('template missing')
      const result = validateRows(templateDraft.rows)
      if (result.error) throw new Error(result.error)
      return updateStatusTemplate(currentWorkspace, selectedTemplate.id, {
        name: templateDraft.name.trim(),
        description: templateDraft.description,
        keyColumn: templateDraft.keyColumn.trim() || DEFAULT_KEY_COLUMN,
        valueColumn: templateDraft.valueColumn.trim() || DEFAULT_VALUE_COLUMN,
        rows: result.rows,
      })
    },
    onSuccess: (table) => {
      upsertTemplateCache(table)
      setSelectedTemplateId(table.id)
      setFormError('')
      invalidateTemplates()
    },
    onError: (error) => setFormError(error instanceof Error ? error.message : '保存模板失败'),
  })

  const saveStoryTemplateMutation = useMutation({
    mutationFn: () => {
      if (!currentWorkspace || !selectedStoryTemplate) throw new Error('story template missing')
      const result = validateRows(storyTemplateDraft.rows)
      if (result.error) throw new Error(result.error)
      return updateStatusTemplate(currentWorkspace, selectedStoryTemplate.id, {
        name: storyTemplateDraft.name.trim(),
        description: storyTemplateDraft.description,
        keyColumn: storyTemplateDraft.keyColumn.trim() || DEFAULT_KEY_COLUMN,
        valueColumn: storyTemplateDraft.valueColumn.trim() || DEFAULT_VALUE_COLUMN,
        rows: result.rows,
      })
    },
    onSuccess: (table) => {
      upsertTemplateCache(table)
      setFormError('')
      invalidateTemplates()
    },
    onError: (error) => setFormError(error instanceof Error ? error.message : '保存故事状态模板失败'),
  })

  const deleteTemplateMutation = useMutation({
    mutationFn: () => {
      if (!currentWorkspace || !selectedTemplate) throw new Error('template missing')
      return deleteStatusTemplate(currentWorkspace, selectedTemplate.id)
    },
    onSuccess: () => {
      setDeleteTemplateOpen(false)
      setSelectedTemplateId(null)
      invalidateTemplates()
    },
    onError: (error) => setFormError(error instanceof Error ? error.message : '删除模板失败'),
  })

  const deleteStoryTemplateMutation = useMutation({
    mutationFn: () => {
      if (!currentWorkspace || !selectedStoryId || !selectedStoryMount) throw new Error('story template missing')
      return deleteStoryStatusTemplate(currentWorkspace, selectedStoryId, selectedStoryMount.id)
    },
    onSuccess: () => {
      setDeleteStoryTemplateOpen(false)
      setSelectedStoryMountId(null)
      invalidateTemplates()
    },
    onError: (error) => setFormError(error instanceof Error ? error.message : '删除故事状态模板失败'),
  })

  const mountMutation = useMutation({
    mutationFn: (storyId: number) => {
      if (!currentWorkspace || !selectedTemplate) throw new Error('template missing')
      return mountStatusTemplate(currentWorkspace, storyId, selectedTemplate.id, selectedTemplateMounts.length * 10)
    },
    onSuccess: () => {
      setMountDialogOpen(false)
      invalidateTemplates()
    },
    onError: (error) => setFormError(error instanceof Error ? error.message : '挂载失败'),
  })

  const copyTemplateToSessionMutation = useMutation({
    mutationFn: async () => {
      if (!selectedTemplate || !copyTargetStory || !copySessionId) throw new Error('copy target missing')
      const targetSessionId = copySessionId
      const targetTables = await queryClient.fetchQuery({
        queryKey: statusTableQueryKeys.sessionStatusTables(targetSessionId),
        queryFn: () => listSessionStatusTables(targetSessionId),
      })
      const nextSortOrder = targetTables.reduce((max, table) => Math.max(max, table.sortOrder), 0) + 10
      return createSessionStatusTable(targetSessionId, {
        name: uniqueStatusTableName(selectedTemplate.name, targetTables),
        statusKind: selectedTemplate.statusKind,
        description: selectedTemplate.description,
        keyColumn: selectedTemplate.keyColumn,
        valueColumn: selectedTemplate.valueColumn,
        rows: selectedTemplate.rows.map((row) => ({
          key: row.key,
          value: row.value,
          runtimeKeyLocked: row.runtimeKeyLocked,
          metadata: row.metadata ?? {},
          updateFrequency: row.updateFrequency,
          updateRule: row.updateRule,
          deferredIntervalTurns: row.deferredIntervalTurns,
        })),
        metadata: selectedTemplate.metadata ?? DEFAULT_TEMPLATE_METADATA,
        sortOrder: nextSortOrder,
      })
    },
    onSuccess: (table) => {
      const targetSessionId = copySessionId
      setCopyTargetStoryId(null)
      setCopySessionId(null)
      if (targetSessionId) {
        queryClient.invalidateQueries({ queryKey: statusTableQueryKeys.sessionStatusTables(targetSessionId) })
      }
      if (targetSessionId && targetSessionId === selectedSessionId) {
        setSelectedRuntimeTableId(table.id)
      }
    },
    onError: (error) => setFormError(error instanceof Error ? error.message : '复制到会话失败'),
  })

  const unmountMutation = useMutation({
    mutationFn: ({ storyId, mountId }: { storyId: number; mountId: number }) => {
      if (!currentWorkspace) throw new Error('workspace missing')
      return unmountStatusTemplate(currentWorkspace, storyId, mountId)
    },
    onSuccess: () => invalidateTemplates(),
    onError: (error) => setFormError(error instanceof Error ? error.message : '解除挂载失败'),
  })

  const updateStoryMountMutation = useMutation({
    mutationFn: (characterMountId: number | null) => {
      if (!currentWorkspace || !selectedStoryId || !selectedStoryMount) throw new Error('status mount missing')
      return updateStoryStatusMount(currentWorkspace, selectedStoryId, selectedStoryMount.id, { characterMountId })
    },
    onSuccess: (mount) => {
      setSelectedStoryMountId(mount.id)
      invalidateTemplates()
    },
    onError: (error) => setFormError(error instanceof Error ? error.message : '绑定角色失败'),
  })

  const createRuntimeMutation = useMutation({
    mutationFn: (kind: StatusKind) => {
      if (!selectedSessionId) throw new Error('session missing')
      const nextSortOrder = runtimeTables.reduce((max, table) => Math.max(max, table.sortOrder), 0) + 10
      return createSessionStatusTable(selectedSessionId, {
        name: defaultStatusTableName(kind),
        statusKind: kind,
        description: '',
        keyColumn: DEFAULT_KEY_COLUMN,
        valueColumn: DEFAULT_VALUE_COLUMN,
        rows: [],
        metadata: DEFAULT_TEMPLATE_METADATA,
        sortOrder: nextSortOrder,
      })
    },
    onSuccess: (table) => {
      setSelectedRuntimeTableId(table.id)
      setCreateRuntimeOpen(false)
      invalidateRuntimeTables()
    },
    onError: (error) => setFormError(error instanceof Error ? error.message : '新增状态表失败'),
  })

  const saveRuntimeMutation = useMutation({
    mutationFn: () => {
      if (!selectedSessionId || !selectedRuntimeTable) throw new Error('status table missing')
      const result = validateRows(runtimeDraft.rows)
      if (result.error) throw new Error(result.error)
      return updateSessionStatusTable(selectedSessionId, selectedRuntimeTable.id, {
        name: runtimeDraft.name.trim(),
        description: runtimeDraft.description,
        keyColumn: runtimeDraft.keyColumn.trim() || DEFAULT_KEY_COLUMN,
        valueColumn: runtimeDraft.valueColumn.trim() || DEFAULT_VALUE_COLUMN,
        rows: result.rows,
      })
    },
    onSuccess: (table) => {
      setSelectedRuntimeTableId(table.id)
      setFormError('')
      invalidateRuntimeTables()
    },
    onError: (error) => setFormError(error instanceof Error ? error.message : '保存状态表失败'),
  })

  const deleteRuntimeMutation = useMutation({
    mutationFn: () => {
      if (!selectedSessionId || !selectedRuntimeTable) throw new Error('status table missing')
      return deleteSessionStatusTable(selectedSessionId, selectedRuntimeTable.id)
    },
    onSuccess: () => {
      setDeleteRuntimeOpen(false)
      setSelectedRuntimeTableId(null)
      invalidateRuntimeTables()
    },
    onError: (error) => setFormError(error instanceof Error ? error.message : '删除状态表失败'),
  })

  const templateDeleteDisabled = !selectedTemplate || Boolean(selectedTemplateMounts.length) || deleteTemplateMutation.isPending
  const activeTemplateAction = view === STATUS_TABLE_VIEW.SYSTEM
  const activeStoryTemplateAction = view === STATUS_TABLE_VIEW.STORY
  const activeRuntimeAction = view === STATUS_TABLE_VIEW.RUNTIME
  const storyTemplateOwned = selectedStoryMount?.mountOrigin === STORY_STATUS_MOUNT_ORIGIN.STORY_TEMPLATE

  return {
    currentWorkspace,
    view,
    setView,
    formError,
    storiesQuery,
    templatesQuery,
    sessionsQuery,
    runtimeTablesQuery,
    storyCharactersQuery,
    copySessionsQuery,
    storyMountQueries,
    stories,
    templates,
    sessions,
    runtimeTables,
    storyCharacters,
    copySessions,
    storyMountGroups,
    systemTemplates,
    mountedTemplateIds,
    selectedTemplate,
    selectedTemplateId,
    setSelectedTemplateId,
    selectedTemplateMounts,
    selectedTemplateMountedStoryIds,
    selectedStory,
    selectedStoryId,
    setSelectedStoryId,
    selectedStoryMount,
    selectedStoryMountId,
    setSelectedStoryMountId,
    selectedStoryMounts,
    selectedStoryTemplate,
    selectedSession,
    selectedSessionId,
    setSelectedSessionId,
    selectedRuntimeTable,
    selectedRuntimeTableId,
    setSelectedRuntimeTableId,
    templateDraft,
    setTemplateDraft,
    storyTemplateDraft,
    setStoryTemplateDraft,
    runtimeDraft,
    setRuntimeDraft,
    createTemplateOpen,
    setCreateTemplateOpen,
    createStoryTemplateOpen,
    setCreateStoryTemplateOpen,
    createRuntimeOpen,
    setCreateRuntimeOpen,
    mountDialogOpen,
    setMountDialogOpen,
    copyTargetStory,
    setCopyTargetStoryId,
    copySessionId,
    setCopySessionId,
    deleteTemplateOpen,
    setDeleteTemplateOpen,
    deleteStoryTemplateOpen,
    setDeleteStoryTemplateOpen,
    deleteRuntimeOpen,
    setDeleteRuntimeOpen,
    createTemplateMutation,
    createStoryTemplateMutation,
    saveTemplateMutation,
    saveStoryTemplateMutation,
    deleteTemplateMutation,
    deleteStoryTemplateMutation,
    mountMutation,
    copyTemplateToSessionMutation,
    unmountMutation,
    updateStoryMountMutation,
    createRuntimeMutation,
    saveRuntimeMutation,
    deleteRuntimeMutation,
    templateDeleteDisabled,
    activeTemplateAction,
    activeStoryTemplateAction,
    activeRuntimeAction,
    storyTemplateOwned,
  }
}

export type StatusTablesController = ReturnType<typeof useStatusTablesController>
