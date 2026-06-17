/**
 * useCommands — 斜杠命令业务逻辑。
 *
 * 命令定义完全以后端 GET /chat/commands 为准，前端不做硬编码。
 * 与 ChatView 解耦，集中管理前端侧的命令相关状态。
 */

import { ref, computed, unref, watch } from 'vue'
import api from '@/api/index'
import { fetchCommands as fetchRemoteCommands } from '@/api/chat'

/**
 * 获取 API key（与 chat.js 保持一致）。
 */
function getApiKey() {
  return localStorage.getItem('rpg_openai_api_key') || ''
}

/**
 * 发送命令到后端执行。
 * @param {string} command - 完整命令字符串（如 "/compact 10 5"）
 * @param {string} sessionId
 * @returns {Promise<object>} 后端返回的命令执行结果
 */
export function sendCommand(command, sessionId = 'default') {
  const headers = {}
  const key = getApiKey()
  if (key) headers['X-OpenAI-Api-Key'] = key
  return api.post('/chat/command', { command, session_id: sessionId }, { headers })
}

/**
 * 从后端加载命令定义列表。
 *
 * @param {string} sessionId
 * @returns {Promise<Array<{command: string, description: string, detail: string}>>}
 */
export async function loadCommands(sessionId = 'default') {
  const commands = await fetchRemoteCommands(sessionId)
  return Array.isArray(commands) ? commands : []
}

/**
 * useCommands — Vue composable。
 *
 * 用法：:
 *
 *     const cmd = useCommands(inputText, commandsList)
 *     cmd.showPopup  // ref<boolean>
 *     cmd.filtered   // computed<CommandDef[]>
 *     cmd.highlightIndex  // ref<number>
 *     cmd.isCommand(text) // 判断是否为已知命令
 *     cmd.select(cmdDef)  // 选中命令
 *     cmd.close()         // 关闭弹窗
 *
 * @param {import('vue').Ref<string>} inputText - 绑定到输入框的 ref
 * @param {import('vue').Ref<Array> | Array} commands - 命令定义列表（Ref 或普通数组）
 */
export function useCommands(inputText, commands = []) {
  // 兼容 ref([]) 和普通数组两种传参方式
  const cmds = computed(() => unref(commands))
  const showPopup = ref(false)
  const highlightIndex = ref(0)

  /** 根据输入前缀过滤命令列表 */
  const filtered = computed(() => {
    const text = inputText.value.trimStart()
    const list = cmds.value
    if (!text || !text.startsWith('/')) return []
    const typed = text.split(/\s+/)[0].toLowerCase()
    if (typed === '/') return list
    const exact = list.find((c) => c.command === typed)
    if (text.includes(' ') && exact) return []
    if (exact) return [exact]
    return list.filter((c) => c.command.startsWith(typed))
  })

  watch(filtered, (list) => {
    if (highlightIndex.value >= list.length) {
      highlightIndex.value = Math.max(0, list.length - 1)
    }
    if (list.length === 0) {
      showPopup.value = false
    }
  })

  watch(inputText, () => {
    syncPopup()
  })

  watch(cmds, () => {
    syncPopup()
  })

  function syncPopup() {
    const text = inputText.value.trimStart()
    if (!text.startsWith('/')) {
      showPopup.value = false
      highlightIndex.value = 0
      return
    }
    const typed = text.split(/\s+/)[0].toLowerCase()
    if (text.includes(' ') && cmds.value.some((c) => c.command === typed)) {
      showPopup.value = false
      highlightIndex.value = 0
      return
    }
    showPopup.value = filtered.value.length > 0
    highlightIndex.value = 0
  }

  /** 判断一段文本是否为前端已知的斜杠命令 */
  function isCommand(text) {
    if (!text || !text.startsWith('/')) return false
    const name = text.split(/\s+/)[0].toLowerCase()
    return cmds.value.some((c) => c.command === name)
  }

  /** 选中一个命令，填入输入框 */
  function select(cmd) {
    inputText.value = cmd.command + ' '
    showPopup.value = false
  }

  function close() {
    showPopup.value = false
  }

  /** 监听输入变化，控制弹窗显隐 */
  function onInputChange() {
    syncPopup()
  }

  return {
    showPopup,
    highlightIndex,
    filtered,
    isCommand,
    select,
    close,
    onInputChange,
  }
}
