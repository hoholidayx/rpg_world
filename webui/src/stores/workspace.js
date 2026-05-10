import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  listWorkspaces,
  getActiveWorkspace,
  setActiveWorkspace,
} from '@/api/workspace'

export const useWorkspaceStore = defineStore('workspace', () => {
  const workspaces = ref([])
  const activeWorkspace = ref('')
  const loaded = ref(false)
  const switching = ref(false)

  async function load() {
    const [wsList, active] = await Promise.all([
      listWorkspaces(),
      getActiveWorkspace(),
    ])
    workspaces.value = wsList
    activeWorkspace.value = active.workspace
    loaded.value = true
  }

  async function switchWorkspace(name) {
    switching.value = true
    try {
      await setActiveWorkspace(name)
      // Full reload so all views fetch data from the new workspace
      window.location.reload()
    } catch {
      switching.value = false
    }
  }

  return { workspaces, activeWorkspace, loaded, switching, load, switchWorkspace }
})
