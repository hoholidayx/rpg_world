'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  applyDreamProposal,
  createDreamProposal,
  getDreamProposal,
  listDreamMemories,
  listDreamProposals,
  patchDreamProposal,
  rejectDreamProposal,
  restoreDreamMemory,
} from '@/lib/api/dream'
import { getSession, getSessionHistory } from '@/lib/api/sessions'
import type {
  DreamDepth,
  DreamMemoryLifecycle,
  DreamProposal,
  DreamProposalList,
  DreamProposalItemPatch,
  DreamScope,
} from '@/types/dream'

function proposalKey(sessionId: string, proposalId: string) {
  return ['play-session-dream-proposal', sessionId, proposalId] as const
}

function proposalListKey(sessionId: string) {
  return ['play-session-dream-proposals', sessionId] as const
}

function operationErrorMessage(error: unknown) {
  return error instanceof Error ? error.message : 'Dream 操作失败'
}

export function useDreamMemoryController(sessionId: string) {
  const queryClient = useQueryClient()
  const [depth, setDepth] = useState<DreamDepth>('shallow')
  const [scope, setScope] = useState<DreamScope>('incremental')
  const [proposalId, setProposalId] = useState('')
  const [proposalSelectionReady, setProposalSelectionReady] = useState(false)
  const [draftItems, setDraftItems] = useState<DreamProposalItemPatch[]>([])
  const [lifecycle, setLifecycle] = useState<DreamMemoryLifecycle>('active')
  const [notice, setNotice] = useState('')
  const [operationError, setOperationError] = useState('')

  useEffect(() => {
    const candidate = new URLSearchParams(window.location.search).get('proposalId')?.trim() ?? ''
    if (candidate) setProposalId(candidate)
    setProposalSelectionReady(true)
  }, [])

  const sessionQuery = useQuery({
    queryKey: ['play-session', sessionId],
    queryFn: () => getSession(sessionId),
    retry: false,
  })
  const memoriesQuery = useQuery({
    queryKey: ['play-session-dream-memories', sessionId],
    queryFn: () => listDreamMemories(sessionId),
    retry: false,
    refetchOnWindowFocus: false,
  })
  const proposalsQuery = useQuery({
    queryKey: proposalListKey(sessionId),
    queryFn: () => listDreamProposals(sessionId),
    retry: false,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  })
  const proposalQuery = useQuery({
    queryKey: proposalKey(sessionId, proposalId),
    queryFn: () => getDreamProposal(sessionId, proposalId),
    enabled: Boolean(proposalId),
    retry: false,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  })
  const evidenceHistoryQuery = useQuery({
    queryKey: ['play-session-dream-evidence-history', sessionId],
    queryFn: () => getSessionHistory(sessionId),
    enabled: false,
    retry: false,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  })

  useEffect(() => {
    if (!proposalQuery.data) return
    setDraftItems(proposalQuery.data.items.map((item) => {
      const targetRevision = memoriesQuery.data?.items.find(
        (memory) => memory.memoryId === item.targetMemoryId,
      )?.currentRevision
      return {
        itemId: item.itemId,
        selected: item.selected,
        text: item.text ?? targetRevision?.text ?? '',
        memoryKind: item.memoryKind ?? targetRevision?.memoryKind ?? 'event',
        epistemicStatus: item.epistemicStatus ?? targetRevision?.epistemicStatus ?? 'confirmed',
        salience: item.salience ?? targetRevision?.salience ?? 0.5,
      }
    }))
  }, [memoriesQuery.data?.items, proposalQuery.data])

  const selectProposal = useCallback((
    nextProposalId: string,
    proposal?: DreamProposal,
  ) => {
    if (proposal) {
      queryClient.setQueryData(proposalKey(sessionId, nextProposalId), proposal)
    }
    setProposalId(nextProposalId)
    const params = new URLSearchParams(window.location.search)
    if (nextProposalId) params.set('proposalId', nextProposalId)
    else params.delete('proposalId')
    const query = params.toString()
    window.history.replaceState(null, '', `${window.location.pathname}${query ? `?${query}` : ''}`)
  }, [queryClient, sessionId])

  const updateProposalList = useCallback((proposal: DreamProposal, prepend = false) => {
    queryClient.setQueryData<DreamProposalList>(proposalListKey(sessionId), (current) => {
      const items = current?.items ?? []
      const exists = items.some((item) => item.proposalId === proposal.proposalId)
      if (prepend) {
        return {
          items: [
            proposal,
            ...items.filter((item) => item.proposalId !== proposal.proposalId),
          ],
        }
      }
      return {
        items: exists ? items.map((item) => (
          item.proposalId === proposal.proposalId ? proposal : item
        )) : [...items, proposal],
      }
    })
  }, [queryClient, sessionId])

  useEffect(() => {
    if (!proposalSelectionReady) return
    const proposals = proposalsQuery.data?.items
    if (!proposals) return
    const selected = proposals.find((item) => item.proposalId === proposalId)
    if (selected) {
      if (queryClient.getQueryData(proposalKey(sessionId, selected.proposalId)) === undefined) {
        queryClient.setQueryData(proposalKey(sessionId, selected.proposalId), selected)
      }
      return
    }
    const recovered = proposals.find((item) => (
      item.status === 'generating' || item.status === 'ready'
    )) ?? proposals.find((item) => (
      item.status === 'interrupted' || item.status === 'failed' || item.status === 'stale'
    )) ?? proposals[0]
    selectProposal(recovered?.proposalId ?? '', recovered)
  }, [
    proposalId,
    proposalSelectionReady,
    proposalsQuery.data?.items,
    queryClient,
    selectProposal,
    sessionId,
  ])

  const reconcileProposalQueries = useCallback(async () => {
    const tasks = [
      queryClient.invalidateQueries({
        queryKey: proposalListKey(sessionId),
        exact: true,
      }),
    ]
    if (proposalId) {
      tasks.push(queryClient.invalidateQueries({
        queryKey: proposalKey(sessionId, proposalId),
        exact: true,
      }))
    }
    await Promise.all(tasks)
  }, [proposalId, queryClient, sessionId])

  const createMutation = useMutation({
    mutationFn: () => createDreamProposal(sessionId, { depth, scope }),
    onMutate: () => {
      setOperationError('')
      setNotice('')
    },
    onSuccess: (proposal) => {
      setOperationError('')
      updateProposalList(proposal, true)
      selectProposal(proposal.proposalId, proposal)
      setNotice('Dream 已提交。生成期间不会自动轮询，请稍后手动刷新状态。')
    },
    onError: async (error) => {
      setOperationError(operationErrorMessage(error))
      await reconcileProposalQueries()
    },
  })
  const saveMutation = useMutation({
    mutationFn: () => {
      if (!proposalId) throw new Error('尚未选择 Dream proposal')
      return patchDreamProposal(sessionId, proposalId, { items: draftItems })
    },
    onMutate: () => {
      setOperationError('')
      setNotice('')
    },
    onSuccess: (proposal) => {
      setOperationError('')
      queryClient.setQueryData(proposalKey(sessionId, proposal.proposalId), proposal)
      updateProposalList(proposal)
      setNotice('已保存本地选择与编辑。')
    },
    onError: async (error) => {
      setOperationError(operationErrorMessage(error))
      await reconcileProposalQueries()
    },
  })
  const applyMutation = useMutation({
    mutationFn: async () => {
      if (!proposalId) throw new Error('尚未选择 Dream proposal')
      if (draftItems.length) {
        await patchDreamProposal(sessionId, proposalId, { items: draftItems })
      }
      return applyDreamProposal(sessionId, proposalId)
    },
    onMutate: () => {
      setOperationError('')
      setNotice('')
    },
    onSuccess: (proposal) => {
      setOperationError('')
      queryClient.setQueryData(proposalKey(sessionId, proposal.proposalId), proposal)
      updateProposalList(proposal)
      void queryClient.invalidateQueries({ queryKey: ['play-session-context-preview', sessionId] })
      setNotice('Dream 已应用，正在刷新持久记忆账本。')
      void listDreamMemories(sessionId).then((memories) => {
        queryClient.setQueryData(['play-session-dream-memories', sessionId], memories)
        setNotice(`Dream 已应用，当前共有 ${memories.activeCount} 条生效记忆。`)
      }).catch(() => {
        void queryClient.invalidateQueries({
          queryKey: ['play-session-dream-memories', sessionId],
        })
        setNotice('Dream 已成功应用，但账本刷新失败；请稍后手动刷新。')
      })
    },
    onError: async (error) => {
      setOperationError(operationErrorMessage(error))
      await reconcileProposalQueries()
    },
  })
  const rejectMutation = useMutation({
    mutationFn: () => {
      if (!proposalId) throw new Error('尚未选择 Dream proposal')
      return rejectDreamProposal(sessionId, proposalId)
    },
    onMutate: () => {
      setOperationError('')
      setNotice('')
    },
    onSuccess: (proposal) => {
      setOperationError('')
      queryClient.setQueryData(proposalKey(sessionId, proposal.proposalId), proposal)
      updateProposalList(proposal)
      setNotice('已拒绝整份 proposal；增量 checkpoint 未推进。')
    },
    onError: async (error) => {
      setOperationError(operationErrorMessage(error))
      await reconcileProposalQueries()
    },
  })
  const restoreMutation = useMutation({
    mutationFn: (memoryId: string) => restoreDreamMemory(sessionId, memoryId),
    onMutate: () => {
      setOperationError('')
      setNotice('')
    },
    onSuccess: () => {
      setOperationError('')
      void memoriesQuery.refetch()
      void queryClient.invalidateQueries({ queryKey: ['play-session-context-preview', sessionId] })
      setLifecycle('active')
      setNotice('记忆已恢复并重新进入主 Agent Context。')
    },
    onError: async (error) => {
      setOperationError(operationErrorMessage(error))
      await Promise.all([
        memoriesQuery.refetch(),
        reconcileProposalQueries(),
      ])
    },
  })

  const updateDraftItem = useCallback((itemId: string, patch: Partial<DreamProposalItemPatch>) => {
    setDraftItems((current) => current.map((item) => (
      item.itemId === itemId ? { ...item, ...patch, itemId } : item
    )))
  }, [])

  const refresh = useCallback(async () => {
    setOperationError('')
    setNotice('')
    const tasks: Promise<unknown>[] = [memoriesQuery.refetch(), proposalsQuery.refetch()]
    if (proposalId) tasks.push(proposalQuery.refetch())
    if (evidenceHistoryQuery.data !== undefined) {
      tasks.push(evidenceHistoryQuery.refetch())
    }
    await Promise.all(tasks)
    setNotice('状态已刷新。')
  }, [evidenceHistoryQuery, memoriesQuery, proposalId, proposalQuery, proposalsQuery])

  const proposal = proposalQuery.data ?? null
  const visibleMemories = useMemo(
    () => (memoriesQuery.data?.items ?? []).filter((memory) => memory.lifecycle === lifecycle),
    [lifecycle, memoriesQuery.data?.items],
  )
  const evidenceMessagesById = useMemo(() => new Map(
    (evidenceHistoryQuery.data ?? []).flatMap((turn) => turn.messages).map(
      (message) => [message.messageId, message] as const,
    ),
  ), [evidenceHistoryQuery.data])
  const selectedItemCount = draftItems.filter((item) => item.selected).length
  const currentError = proposalsQuery.error
    ?? proposalQuery.error
    ?? memoriesQuery.error
    ?? evidenceHistoryQuery.error
    ?? sessionQuery.error

  return {
    sessionId,
    sessionQuery,
    memoriesQuery,
    proposalsQuery,
    proposalQuery,
    proposal,
    proposalId,
    selectProposal,
    depth,
    setDepth,
    scope,
    setScope,
    lifecycle,
    setLifecycle,
    draftItems,
    updateDraftItem,
    visibleMemories,
    evidenceMessagesById,
    evidenceHistoryLoaded: Boolean(evidenceHistoryQuery.data),
    loadEvidenceHistory: evidenceHistoryQuery.refetch,
    selectedItemCount,
    notice,
    setNotice,
    errorMessage: operationError
      || (currentError instanceof Error ? currentError.message : ''),
    refreshing: proposalQuery.isFetching
      || proposalsQuery.isFetching
      || memoriesQuery.isFetching
      || evidenceHistoryQuery.isFetching,
    mutating: createMutation.isPending
      || saveMutation.isPending
      || applyMutation.isPending
      || rejectMutation.isPending
      || restoreMutation.isPending,
    createProposal: createMutation.mutate,
    saveProposal: saveMutation.mutate,
    applyProposal: applyMutation.mutate,
    rejectProposal: rejectMutation.mutate,
    restoreMemory: restoreMutation.mutate,
    refresh,
  }
}

export type DreamMemoryController = ReturnType<typeof useDreamMemoryController>
