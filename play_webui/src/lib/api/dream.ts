import type {
  DreamMemory,
  DreamMemoryList,
  DreamProposal,
  DreamProposalCreateInput,
  DreamProposalList,
  DreamProposalPatchInput,
} from '@/types/dream'
import { playApiFetch } from './client'

function dreamPath(sessionId: string) {
  return `/sessions/${encodeURIComponent(sessionId)}/dream`
}

export function createDreamProposal(sessionId: string, input: DreamProposalCreateInput) {
  return playApiFetch<DreamProposal>(`${dreamPath(sessionId)}/proposals`, {
    method: 'POST',
    body: JSON.stringify(input),
  })
}

export function getDreamProposal(sessionId: string, proposalId: string) {
  return playApiFetch<DreamProposal>(
    `${dreamPath(sessionId)}/proposals/${encodeURIComponent(proposalId)}`,
  )
}

export function listDreamProposals(sessionId: string) {
  return playApiFetch<DreamProposalList>(`${dreamPath(sessionId)}/proposals`)
}

export function patchDreamProposal(
  sessionId: string,
  proposalId: string,
  input: DreamProposalPatchInput,
) {
  return playApiFetch<DreamProposal>(
    `${dreamPath(sessionId)}/proposals/${encodeURIComponent(proposalId)}`,
    { method: 'PATCH', body: JSON.stringify(input) },
  )
}

export function applyDreamProposal(sessionId: string, proposalId: string) {
  return playApiFetch<DreamProposal>(
    `${dreamPath(sessionId)}/proposals/${encodeURIComponent(proposalId)}/apply`,
    { method: 'POST' },
  )
}

export function rejectDreamProposal(sessionId: string, proposalId: string) {
  return playApiFetch<DreamProposal>(
    `${dreamPath(sessionId)}/proposals/${encodeURIComponent(proposalId)}/reject`,
    { method: 'POST' },
  )
}

export function listDreamMemories(sessionId: string) {
  return playApiFetch<DreamMemoryList>(`${dreamPath(sessionId)}/memories`)
}

export function restoreDreamMemory(sessionId: string, memoryId: string) {
  return playApiFetch<DreamMemory>(
    `${dreamPath(sessionId)}/memories/${encodeURIComponent(memoryId)}/restore`,
    { method: 'POST' },
  )
}
