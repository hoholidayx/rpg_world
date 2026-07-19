import { useCallback, useEffect, useRef, useState } from 'react'
import {
  bindSessionPlayerCharacter,
  getSessionOpeningOptions,
  type getSession,
} from '@/lib/api/sessions'
import type { CharacterCard } from '@/types/characters'
import {
  PLAYER_CHARACTER_STATUS,
  type SessionOpeningOption,
  type SessionPlayerCharacter,
} from '@/types/session'
import type { ConfirmRequest, RefreshSessionDataOptions } from '../sessionRoomTypes'
import type { SessionRoomLogger } from '../sessionRoomLogger'

type SessionPayload = Awaited<ReturnType<typeof getSession>>

export function useSessionRoleBinding({
  sessionId,
  session,
  characters,
  playerCharacter,
  refreshSessionData,
  requestConfirm,
  showToast,
  logger,
  closeSettings,
}: {
  sessionId: string
  session: SessionPayload | undefined
  characters: CharacterCard[]
  playerCharacter: SessionPlayerCharacter | null
  refreshSessionData: (options?: RefreshSessionDataOptions) => Promise<boolean>
  requestConfirm: (request: ConfirmRequest) => void
  showToast: (message: string) => void
  logger: SessionRoomLogger
  closeSettings: () => void
}) {
  const [roleDialogOpen, setRoleDialogOpen] = useState(false)
  const [roleDialogRequired, setRoleDialogRequired] = useState(false)
  const [selectedRoleCharacterId, setSelectedRoleCharacterId] = useState<number | null>(null)
  const [roleBindError, setRoleBindError] = useState<string | null>(null)
  const [bindingRole, setBindingRole] = useState(false)
  const [openingDialogOpen, setOpeningDialogOpen] = useState(false)
  const [openingOptions, setOpeningOptions] = useState<SessionOpeningOption[]>([])
  const [selectedOpeningId, setSelectedOpeningId] = useState<number | null>(null)
  const [pendingRoleCharacterId, setPendingRoleCharacterId] = useState<number | null>(null)
  const flowVersionRef = useRef(0)

  const clearOpeningStep = useCallback(() => {
    setOpeningDialogOpen(false)
    setOpeningOptions([])
    setSelectedOpeningId(null)
    setPendingRoleCharacterId(null)
  }, [])

  useEffect(() => {
    flowVersionRef.current += 1
    setRoleDialogOpen(false)
    setRoleDialogRequired(false)
    setSelectedRoleCharacterId(null)
    setRoleBindError(null)
    setBindingRole(false)
    setOpeningDialogOpen(false)
    setOpeningOptions([])
    setSelectedOpeningId(null)
    setPendingRoleCharacterId(null)
  }, [sessionId])

  useEffect(() => {
    if (!session) return
    if (session.playerCharacterStatus === PLAYER_CHARACTER_STATUS.INVALID) {
      setRoleDialogRequired(true)
      if (!openingDialogOpen) {
        setRoleDialogOpen(true)
        setSelectedRoleCharacterId((current) => current ?? characters[0]?.id ?? null)
      }
      logger.info('role dialog required', { status: 'invalid_player_character' })
      return
    }
    if (roleDialogRequired) {
      setRoleDialogRequired(false)
      setRoleDialogOpen(false)
      setRoleBindError(null)
      clearOpeningStep()
      logger.info('role dialog cleared', { status: 'bound' })
    }
  }, [characters, clearOpeningStep, logger, openingDialogOpen, roleDialogRequired, session])

  const requireRoleSelection = useCallback(() => {
    setRoleDialogRequired(true)
    if (!openingDialogOpen) setRoleDialogOpen(true)
    logger.info('role selection required', { status: 'blocked_send' })
    showToast(openingDialogOpen ? '请先选择会话开局' : '请先选择你要扮演的角色')
  }, [logger, openingDialogOpen, showToast])

  const bindPlayerRole = useCallback(async (
    characterId: number,
    storyOpeningId: number | undefined,
    initialBinding: boolean,
  ) => {
    const flowVersion = ++flowVersionRef.current
    setBindingRole(true)
    setRoleBindError(null)
    logger.info('role bind started', {
      characterId,
      storyOpeningId: storyOpeningId ?? null,
      status: 'pending',
    })
    try {
      const updated = await bindSessionPlayerCharacter(
        sessionId,
        characterId,
        storyOpeningId,
      )
      if (flowVersion !== flowVersionRef.current) return
      await refreshSessionData({ silent: true })
      if (flowVersion !== flowVersionRef.current) return
      setRoleDialogOpen(false)
      setRoleDialogRequired(false)
      setSelectedRoleCharacterId(null)
      clearOpeningStep()
      logger.info('role bind completed', {
        characterId,
        storyOpeningId: updated.storyOpeningId ?? null,
        status: 'success',
      })
      showToast(`${initialBinding ? '已开始扮演' : '已切换为'} ${updated.playerCharacter?.name ?? '所选角色'}`)
    } catch (error) {
      if (flowVersion !== flowVersionRef.current) return
      const message = error instanceof Error ? error.message : '角色绑定失败'
      setRoleBindError(message)
      logger.warn('role bind failed', { characterId, status: 'error', error })
      showToast(message)
    } finally {
      if (flowVersion === flowVersionRef.current) setBindingRole(false)
    }
  }, [clearOpeningStep, logger, refreshSessionData, sessionId, showToast])

  const prepareInitialBinding = useCallback(async (characterId: number) => {
    const flowVersion = ++flowVersionRef.current
    setBindingRole(true)
    setRoleBindError(null)
    logger.info('opening options requested', { characterId, status: 'pending' })
    try {
      const result = await getSessionOpeningOptions(sessionId, characterId)
      if (flowVersion !== flowVersionRef.current) return
      if (!result.canSelectOpening || result.items.length <= 1) {
        const storyOpeningId = result.canSelectOpening
          ? result.items[0]?.id
          : undefined
        await bindPlayerRole(characterId, storyOpeningId, true)
        return
      }
      setPendingRoleCharacterId(characterId)
      setOpeningOptions(result.items)
      setSelectedOpeningId(result.defaultOpeningId ?? result.items[0]?.id ?? null)
      setRoleDialogOpen(false)
      setOpeningDialogOpen(true)
      logger.info('opening dialog required', {
        characterId,
        openingCount: result.items.length,
        status: 'ready',
      })
    } catch (error) {
      if (flowVersion !== flowVersionRef.current) return
      const message = error instanceof Error ? error.message : '开局选项加载失败'
      setRoleBindError(message)
      logger.warn('opening options failed', { characterId, status: 'error', error })
      showToast(message)
    } finally {
      if (flowVersion === flowVersionRef.current) setBindingRole(false)
    }
  }, [bindPlayerRole, logger, sessionId, showToast])

  const openRoleDialog = useCallback(() => {
    flowVersionRef.current += 1
    closeSettings()
    clearOpeningStep()
    setBindingRole(false)
    setRoleDialogRequired(false)
    setRoleDialogOpen(true)
    setRoleBindError(null)
    setSelectedRoleCharacterId(playerCharacter?.characterId ?? characters[0]?.id ?? null)
    logger.info('role dialog opened', { status: 'manual' })
  }, [characters, clearOpeningStep, closeSettings, logger, playerCharacter])

  const closeRoleDialog = useCallback(() => {
    if (roleDialogRequired) return
    flowVersionRef.current += 1
    setRoleDialogOpen(false)
    setRoleBindError(null)
    setSelectedRoleCharacterId(null)
    logger.info('role dialog closed', { status: 'manual' })
  }, [logger, roleDialogRequired])

  const submitRoleDialog = useCallback(() => {
    const characterId = selectedRoleCharacterId
    if (!characterId) {
      setRoleBindError('请选择一个角色')
      return
    }
    if (!roleDialogRequired && playerCharacter?.characterId === characterId) {
      showToast('已经是当前扮演角色')
      return
    }
    if (!roleDialogRequired && playerCharacter) {
      const next = characters.find((character) => character.id === characterId)
      requestConfirm({
        title: '确认切换角色',
        heading: '切换玩家扮演角色',
        body: `将当前扮演角色从 ${playerCharacter.name} 切换为 ${next?.name ?? '所选角色'}。历史消息保持原样，只影响后续 user 身份。`,
        confirmLabel: '确认切换',
        onConfirm: () => {
          void bindPlayerRole(characterId, undefined, false)
        },
      })
      return
    }
    void prepareInitialBinding(characterId)
  }, [bindPlayerRole, characters, playerCharacter, prepareInitialBinding, requestConfirm, roleDialogRequired, selectedRoleCharacterId, showToast])

  const submitOpeningDialog = useCallback(() => {
    if (!pendingRoleCharacterId || !selectedOpeningId) {
      setRoleBindError('请选择一个会话开局')
      return
    }
    void bindPlayerRole(pendingRoleCharacterId, selectedOpeningId, true)
  }, [bindPlayerRole, pendingRoleCharacterId, selectedOpeningId])

  const backToRoleDialog = useCallback(() => {
    if (bindingRole) return
    flowVersionRef.current += 1
    const characterId = pendingRoleCharacterId
    clearOpeningStep()
    setRoleBindError(null)
    setSelectedRoleCharacterId(characterId)
    setRoleDialogOpen(true)
    logger.info('opening dialog returned to role selection', { status: 'back' })
  }, [bindingRole, clearOpeningStep, logger, pendingRoleCharacterId])

  return {
    roleDialogOpen,
    roleDialogRequired,
    selectedRoleCharacterId,
    roleBindError,
    bindingRole,
    openingDialogOpen,
    openingOptions,
    selectedOpeningId,
    pendingRoleCharacterId,
    setSelectedRoleCharacterId,
    setSelectedOpeningId,
    openRoleDialog,
    closeRoleDialog,
    submitRoleDialog,
    submitOpeningDialog,
    backToRoleDialog,
    requireRoleSelection,
  }
}
