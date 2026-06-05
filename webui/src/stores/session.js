import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  listSessions,
  createSession,
  deleteSession,
  cloneSession,
} from '@/api/session'

export const useSessionStore = defineStore('session', () => {
  const sessions = ref([])
  const activeSession = ref('default')
  const loaded = ref(false)
  const switching = ref(false)

  async function load() {
    const data = await listSessions()
    sessions.value = data
    loaded.value = true
  }

  async function switchSession(id) {
    if (id === activeSession.value) return
    switching.value = true
    activeSession.value = id
    switching.value = false
    // Views reactively watch activeSession and reload their data
  }

  async function createNewSession(id) {
    const result = await createSession(id)
    await load()
    return result
  }

  async function removeSession(id) {
    const wasActive = id === activeSession.value
    await deleteSession(id)
    if (wasActive) {
      activeSession.value = 'default'
    }
    await load()
  }

  async function duplicateSession(sourceId, targetId) {
    await cloneSession(sourceId, targetId)
    await load()
  }

  return {
    sessions,
    activeSession,
    loaded,
    switching,
    load,
    switchSession,
    createNewSession,
    removeSession,
    duplicateSession,
  }
})
