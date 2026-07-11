import { useCallback } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  getMainLLMOptions,
  getSessionMainLLM,
  setSessionMainLLM,
} from '@/lib/api/mainLLM'
import type { MainLLMSelection } from '@/types/mainLLM'
import type { SessionRoomLogger } from '../sessionRoomLogger'

export function useSessionMainLLM({
  sessionId,
  enabled,
  showToast,
  logger,
}: {
  sessionId: string
  enabled: boolean
  showToast: (message: string) => void
  logger: SessionRoomLogger
}) {
  const queryClient = useQueryClient()
  const optionsQuery = useQuery({
    queryKey: ['main-llm-options'],
    queryFn: getMainLLMOptions,
  })
  const selectionQuery = useQuery({
    queryKey: ['session-main-llm', sessionId],
    queryFn: () => getSessionMainLLM(sessionId),
    enabled,
  })

  const mutation = useMutation({
    mutationFn: (providerKey: string | null) => setSessionMainLLM(sessionId, providerKey),
    onSuccess: async (selection: MainLLMSelection, providerKey) => {
      queryClient.setQueryData(['session-main-llm', sessionId], selection)
      await queryClient.invalidateQueries({ queryKey: ['play-session-context-preview', sessionId] })
      logger.info('main llm selection updated', {
        status: 'success',
        providerKey,
        effectiveProviderKey: selection.effectiveProviderKey,
        effectiveSource: selection.effectiveSource,
      })
      showToast(`主 Agent LLM 已切换为 ${selection.effective.model}`)
    },
    onError: async (error, providerKey) => {
      logger.warn('main llm selection update failed', {
        status: 'error',
        providerKey,
        error,
      })
      showToast(error instanceof Error ? error.message : '主 Agent LLM 切换失败')
      await Promise.all([optionsQuery.refetch(), selectionQuery.refetch()])
    },
  })

  const selectProvider = useCallback((providerKey: string | null) => {
    if (mutation.isPending) return
    mutation.mutate(providerKey)
  }, [mutation])

  const queryError = optionsQuery.error ?? selectionQuery.error

  return {
    catalog: optionsQuery.data,
    selection: selectionQuery.data,
    loading: optionsQuery.isLoading || selectionQuery.isLoading,
    fetching: optionsQuery.isFetching || selectionQuery.isFetching,
    updating: mutation.isPending,
    error: queryError instanceof Error ? queryError.message : queryError ? 'LLM 配置加载失败' : null,
    selectProvider,
  }
}
