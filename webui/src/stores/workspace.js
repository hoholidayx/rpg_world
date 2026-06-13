import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  listWorkspaces,
  createWorkspace as apiCreateWorkspace,
  renameWorkspace as apiRenameWorkspace,
  deleteWorkspace as apiDeleteWorkspace,
} from '@/api/workspace'

export const useWorkspaceStore = defineStore('workspace', () => {
  const router = useRouter()
  const route = useRoute()

  const workspaces = ref([])
  const loaded = ref(false)

  // Current workspace is derived from the route query, not from server state
  const current = computed(() => route.query.workspace || '')

  async function load() {
    const res = await listWorkspaces()
    workspaces.value = res.workspaces
    loaded.value = true
  }

  function switchWorkspace(name) {
    router.push({ query: { ...route.query, workspace: name || undefined } })
  }

  async function createWorkspace(name) {
    await apiCreateWorkspace(name)
    await load()
  }

  async function renameWorkspace(oldName, newName) {
    await apiRenameWorkspace(oldName, newName)
    // If currently viewing the renamed workspace, switch to new name
    if (current.value === oldName) {
      switchWorkspace(`data/${newName}`)
    }
    await load()
  }

  async function deleteWorkspace(name) {
    await apiDeleteWorkspace(name)
    // If currently viewing the deleted workspace, switch to root
    if (current.value === name) {
      switchWorkspace('')
    }
    await load()
  }

  return {
    workspaces,
    loaded,
    current,
    load,
    switchWorkspace,
    createWorkspace,
    renameWorkspace,
    deleteWorkspace,
  }
})
