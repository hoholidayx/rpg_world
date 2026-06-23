import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  listSessions,
  createSession,
  deleteSession,
  cloneSession,
} from '@/api/session'
import { useWorkspaceStore } from '@/stores/workspace'

export const useSessionStore = defineStore('session', () => {
  const workspaceStore = useWorkspaceStore()

  const sessions = ref([])
  const activeSession = ref('default')
  const loaded = ref(false)
  const loading = ref(false)
  const switching = ref(false)
  const error = ref('')

  function sessionIdOf(item) {
    return item?.session_id || item
  }

  function normalizeActiveSession(preferredSession) {
    const ids = sessions.value.map(sessionIdOf).filter(Boolean)
    if (preferredSession && ids.includes(preferredSession)) {
      activeSession.value = preferredSession
      return
    }
    if (ids.includes(activeSession.value)) return
    activeSession.value = ids.includes('default') ? 'default' : (ids[0] || 'default')
  }

  async function load(preferredSession = null) {
    loading.value = true
    error.value = ''
    try {
      const data = await listSessions(workspaceStore.current)
      sessions.value = data
      normalizeActiveSession(preferredSession)
      loaded.value = true
    } catch (err) {
      error.value = err?.message || '会话加载失败'
      throw err
    } finally {
      loading.value = false
    }
  }

  async function switchSession(id) {
    if (id === activeSession.value) return
    switching.value = true
    error.value = ''
    try {
      activeSession.value = id
    } catch (err) {
      error.value = err?.message || '会话切换失败'
      throw err
    } finally {
      switching.value = false
    }
  }

  async function createNewSession(id) {
    const result = await createSession(workspaceStore.current, id)
    await load()
    return result
  }

  async function removeSession(id) {
    const wasActive = id === activeSession.value
    await deleteSession(workspaceStore.current, id)
    if (wasActive) {
      activeSession.value = 'default'
    }
    await load()
  }

  async function syncActiveSession(id) {
    if (id) {
      activeSession.value = id
    }
    await load(id || activeSession.value)
  }

  async function duplicateSession(sourceId, targetId) {
    await cloneSession(workspaceStore.current, sourceId, targetId)
    await load()
  }

  return {
    sessions,
    activeSession,
    loaded,
    loading,
    switching,
    error,
    load,
    switchSession,
    syncActiveSession,
    createNewSession,
    removeSession,
    duplicateSession,
  }
})
