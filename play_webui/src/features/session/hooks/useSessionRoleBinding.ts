import { useCallback, useEffect, useState } from 'react'
import { bindSessionPlayerCharacter, type getSession } from '@/lib/api/sessions'
import type { CharacterCard } from '@/types/characters'
import { PLAYER_CHARACTER_STATUS, type SessionPlayerCharacter } from '@/types/session'
import type { ConfirmRequest } from '../sessionRoomTypes'
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
  refreshSessionData: (options?: { silent?: boolean; clearAccurateUsage?: boolean }) => Promise<boolean>
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

  useEffect(() => {
    setRoleDialogOpen(false)
    setRoleDialogRequired(false)
    setSelectedRoleCharacterId(null)
    setRoleBindError(null)
  }, [sessionId])

  useEffect(() => {
    if (!session) return
    if (session.playerCharacterStatus === PLAYER_CHARACTER_STATUS.INVALID) {
      setRoleDialogRequired(true)
      setRoleDialogOpen(true)
      setSelectedRoleCharacterId((current) => current ?? characters[0]?.id ?? null)
      logger.info('role dialog required', { status: 'invalid_player_character' })
      return
    }
    if (roleDialogRequired) {
      setRoleDialogRequired(false)
      setRoleDialogOpen(false)
      setRoleBindError(null)
      logger.info('role dialog cleared', { status: 'bound' })
    }
  }, [characters, logger, roleDialogRequired, session])

  const requireRoleSelection = useCallback(() => {
    setRoleDialogRequired(true)
    setRoleDialogOpen(true)
    logger.info('role selection required', { status: 'blocked_send' })
    showToast('请先选择你要扮演的角色')
  }, [logger, showToast])

  const bindPlayerRole = useCallback(async (characterId: number) => {
    setBindingRole(true)
    setRoleBindError(null)
    logger.info('role bind started', { characterId, status: 'pending' })
    try {
      const updated = await bindSessionPlayerCharacter(sessionId, characterId)
      await refreshSessionData({ silent: true })
      setRoleDialogOpen(false)
      setRoleDialogRequired(false)
      setSelectedRoleCharacterId(null)
      logger.info('role bind completed', { characterId, status: 'success' })
      showToast(`已切换为 ${updated.playerCharacter?.name ?? '所选角色'}`)
    } catch (error) {
      const message = error instanceof Error ? error.message : '角色绑定失败'
      setRoleBindError(message)
      logger.warn('role bind failed', { characterId, status: 'error', error })
      showToast(message)
    } finally {
      setBindingRole(false)
    }
  }, [logger, refreshSessionData, sessionId, showToast])

  const openRoleDialog = useCallback(() => {
    closeSettings()
    setRoleDialogRequired(false)
    setRoleDialogOpen(true)
    setRoleBindError(null)
    setSelectedRoleCharacterId(playerCharacter?.characterId ?? characters[0]?.id ?? null)
    logger.info('role dialog opened', { status: 'manual' })
  }, [characters, closeSettings, logger, playerCharacter])

  const closeRoleDialog = useCallback(() => {
    if (roleDialogRequired) return
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
          void bindPlayerRole(characterId)
        },
      })
      return
    }
    void bindPlayerRole(characterId)
  }, [bindPlayerRole, characters, playerCharacter, requestConfirm, roleDialogRequired, selectedRoleCharacterId, showToast])

  return {
    roleDialogOpen,
    roleDialogRequired,
    selectedRoleCharacterId,
    roleBindError,
    bindingRole,
    setSelectedRoleCharacterId,
    openRoleDialog,
    closeRoleDialog,
    submitRoleDialog,
    requireRoleSelection,
  }
}
