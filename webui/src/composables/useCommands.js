/**
 * useCommands — 斜杠命令业务逻辑。
 *
 * 维护命令白名单，提供命令检测、过滤、发送等功能。
 * 与 ChatView 解耦，集中管理前端侧的命令相关状态。
 */

import { ref, computed } from 'vue'
import api from '@/api/index'

/**
 * 命令定义列表。
 * 新增 / 修改命令时只需编辑此数组，前端自动适配。
 */
const COMMAND_DEFS = [
  {
    command: '/clear',
    description: '清空当前会话的对话历史',
    detail: '重置对话上下文，清除所有已发送的消息记录。',
  },
  {
    command: '/compact',
    description: '压缩最老的对话轮次为摘要',
    detail: '可传参：/compact [压缩轮数] [保留轮数]，如 /compact 10 5',
  },
  {
    command: '/reload',
    description: '重新加载 RPG 数据（角色卡、世界书）',
    detail: '从磁盘重新读取角色卡和世界书文件变更。',
  },
  {
    command: '/context',
    description: '查看当前上下文结构和 token 用量',
    detail: '显示 5 层 RPG 上下文的每层信息。',
  },
]

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
 * useCommands — Vue composable。
 *
 * 用法：:
 *
 *     const cmd = useCommands(inputText)
 *     cmd.showPopup  // ref<boolean>
 *     cmd.filtered   // computed<CommandDef[]>
 *     cmd.highlightIndex  // ref<number>
 *     cmd.isCommand(text) // 判断是否为已知命令
 *     cmd.select(cmdDef)  // 选中命令
 *     cmd.close()         // 关闭弹窗
 *
 * @param {import('vue').Ref<string>} inputText - 绑定到输入框的 ref
 */
export function useCommands(inputText) {
  const showPopup = ref(false)
  const highlightIndex = ref(0)

  /** 根据输入前缀过滤命令列表 */
  const filtered = computed(() => {
    const text = inputText.value
    if (!text || !text.startsWith('/')) return COMMAND_DEFS
    const parts = text.split(/\s+/)
    if (parts.length <= 1) return COMMAND_DEFS
    const typed = parts[0].toLowerCase()
    if (COMMAND_DEFS.some((c) => c.command === typed)) return []
    return COMMAND_DEFS.filter((c) => c.command.startsWith(typed))
  })

  /** 判断一段文本是否为前端已知的斜杠命令 */
  function isCommand(text) {
    if (!text || !text.startsWith('/')) return false
    const name = text.split(/\s+/)[0].toLowerCase()
    return COMMAND_DEFS.some((c) => c.command === name)
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
    const text = inputText.value
    if (text === '/') {
      showPopup.value = true
      highlightIndex.value = 0
    } else if (!text.startsWith('/')) {
      showPopup.value = false
    } else {
      const parts = text.split(/\s+/)
      const typed = parts[0].toLowerCase()
      if (typed === '/') {
        showPopup.value = true
      } else if (COMMAND_DEFS.some((c) => c.command.startsWith(typed))) {
        showPopup.value = true
        highlightIndex.value = 0
      } else {
        showPopup.value = false
      }
    }
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
