<template>
  <div class="chat-page">
    <!-- ── Top bar ──────────────────────────────────────── -->
    <header class="chat-header">
      <div class="header-left">
        <a-button type="text" class="back-btn" @click="goBack">
          <ArrowLeftOutlined /> 返回
        </a-button>
      </div>
      <div class="header-center">
        <span class="header-title">RPG Chat</span>
      </div>
      <div class="header-right">
        <!-- Workspace selector -->
        <a-select
          v-model:value="workspaceStore.activeWorkspace"
          :options="workspaceOptions"
          style="width: 140px;"
          size="small"
          @change="onWorkspaceChange"
          :loading="workspaceStore.switching"
        />
        <!-- Session selector -->
        <a-select
          v-model:value="sessionStore.activeSession"
          :options="sessionOptions"
          style="width: 140px;"
          size="small"
          @change="onSessionChange"
        />
        <a-button size="small" type="dashed" @click="openCreateSession">
          <PlusOutlined />
        </a-button>
        <a-popconfirm
          title="确定删除当前会话？此操作不可恢复。"
          @confirm="handleDeleteSession"
          ok-text="确认删除"
          cancel-text="取消"
        >
          <a-button size="small" danger :disabled="isDefaultSession">
            <DeleteOutlined />
          </a-button>
        </a-popconfirm>
        <!-- Settings -->
        <a-tooltip :title="hasApiKey ? 'API Key 已配置' : '点击配置 API Key'">
          <a-button size="small" @click="openSettings" :type="hasApiKey ? 'default' : 'primary'">
            <SettingOutlined />
          </a-button>
        </a-tooltip>
      </div>
    </header>

    <!-- ── Message list ──────────────────────────────────── -->
    <div class="message-container" ref="messageContainer">
      <div v-if="messages.length === 0 && !loadingHistory" class="empty-state">
        <a-empty description="开始一段新的冒险吧">
          <template #image>
            <MessageOutlined style="font-size: 48px; color: var(--text-secondary);" />
          </template>
        </a-empty>
      </div>

      <div v-if="loadingHistory" class="loading-history">
        <a-spin size="small" /> 加载历史消息...
      </div>

      <div
        v-for="(msg, idx) in messages"
        :key="idx"
        class="message-row"
        :class="{ 'is-user': msg.role === 'user', 'is-assistant': msg.role === 'assistant' }"
      >
        <div class="message-bubble">
          <!-- Role label -->
          <div class="msg-role">{{ msg.role === 'user' ? 'User' : 'Assistant' }}</div>

          <!-- Thinking content -->
          <div v-if="msg.thinking" class="msg-thinking">
            <a-collapse ghost size="small">
              <a-collapse-panel key="thinking" header="思考过程">
                <pre class="thinking-text">{{ msg.thinking }}</pre>
              </a-collapse-panel>
            </a-collapse>
          </div>

          <!-- Main content -->
          <div class="msg-content" v-html="renderContent(msg.content)"></div>

          <!-- Streaming indicator -->
          <div v-if="msg.streaming" class="streaming-indicator">
            <a-spin size="small" />
          </div>

          <!-- Tool calls -->
          <div v-if="msg.tool_calls && msg.tool_calls.length" class="msg-tools">
            <a-collapse ghost size="small">
              <a-collapse-panel key="tools" :header="`工具调用 (${msg.tool_calls.length})`">
                <div v-for="(tc, tci) in msg.tool_calls" :key="tci" class="tool-item">
                  <code>{{ tc.tool_name }}({{ tc.tool_arguments }})</code>
                  <div v-if="tc.tool_result_preview" class="tool-result">{{ tc.tool_result_preview }}</div>
                </div>
              </a-collapse-panel>
            </a-collapse>
          </div>

          <!-- Stats (on done) -->
          <div v-if="msg.stats" class="msg-stats">
            tokens: {{ msg.stats.total_tokens || '-' }} |
            {{ msg.stats.total_duration_ms ? (msg.stats.total_duration_ms / 1000).toFixed(1) + 's' : '-' }}
            <template v-if="msg.stats.total_cached_tokens">
              | cache: {{ msg.stats.total_cached_tokens }}
            </template>
          </div>
        </div>
      </div>
    </div>

    <!-- ── Slash-command popup ──────────────────────────── -->
    <div v-if="showCommandPopup" class="command-popup" ref="commandPopupRef">
      <div class="command-popup-title">命令</div>
      <div
        v-for="(cmd, ci) in filteredCommands"
        :key="cmd.command"
        class="command-item"
        :class="{ active: ci === commandHighlightIndex }"
        @click="selectCommand(cmd)"
        @mouseenter="commandHighlightIndex = ci"
      >
        <span class="cmd-name">{{ cmd.command }}</span>
        <span class="cmd-desc">{{ cmd.description }}</span>
      </div>
    </div>

    <!-- ── Input area ────────────────────────────────────── -->
    <div class="input-area">
      <div class="input-wrapper">
        <div class="input-relative">
          <a-textarea
            v-model:value="inputText"
            placeholder="输入消息... (/ 查看命令, Enter 发送, Shift+Enter 换行)"
            :rows="2"
            :disabled="sending"
            @keydown.enter.prevent="onSendKeydown"
            @keydown.escape="closeCommandPopup"
            @keydown.up.prevent="onCommandArrowUp"
            @keydown.down.prevent="onCommandArrowDown"
            @keydown.tab.exact.prevent="onCommandTab"
            @input="onInputChange"
            class="chat-input"
            ref="inputRef"
          />
        </div>
        <div class="input-actions">
          <span class="input-hint">/ 查看命令 · Enter 发送 · Shift+Enter 换行</span>
          <div class="input-buttons">
            <a-button
              v-if="sending"
              danger
              @click="handleStop"
            >
              <StopOutlined /> 停止
            </a-button>
            <a-button
              v-else
              type="primary"
              @click="handleSend"
              :disabled="!inputText.trim()"
            >
              <SendOutlined /> 发送
            </a-button>
          </div>
        </div>
      </div>
    </div>

    <!-- ── Settings modal ──────────────────────────── -->
    <a-modal
      v-model:open="settingsVisible"
      title="设置"
      @ok="handleSaveSettings"
      :confirm-loading="false"
      :width="420"
      :destroy-on-close="true"
    >
      <a-form layout="vertical">
        <a-form-item
          label="OpenAI API Key"
          :validate-status="apiKeyError ? 'error' : undefined"
          :help="apiKeyError || '保存后自动通过 HTTP Header 传入后端，仅存储在你浏览器本地。'"
        >
          <a-input-password
            v-model:value="apiKeyInput"
            placeholder="sk-..."
          />
        </a-form-item>
      </a-form>
    </a-modal>

    <!-- ── Create session modal ──────────────────────────── -->
    <a-modal
      v-model:open="createSessionVisible"
      title="新建会话"
      :confirm-loading="createSessionSaving"
      @ok="handleCreateSession"
      @cancel="resetCreateSessionForm"
      :destroy-on-close="true"
      :width="400"
    >
      <a-form layout="vertical">
        <a-form-item label="会话 ID" :required="true">
          <a-input v-model:value="newSessionId" placeholder="如：campaign-2" />
        </a-form-item>
        <a-form-item label="从现有会话克隆（可选）">
          <a-checkbox v-model:checked="cloneEnabled">克隆数据</a-checkbox>
          <a-select
            v-if="cloneEnabled"
            v-model:value="cloneSourceId"
            :options="sessionOptions"
            style="width: 100%; margin-top: 8px;"
            placeholder="选择源会话"
          />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import {
  ArrowLeftOutlined,
  PlusOutlined,
  DeleteOutlined,
  SendOutlined,
  StopOutlined,
  MessageOutlined,
  SettingOutlined,
} from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { useWorkspaceStore } from '@/stores/workspace'
import { useSessionStore } from '@/stores/session'
import { getHistory, streamMessage } from '@/api/chat'

const router = useRouter()
const workspaceStore = useWorkspaceStore()
const sessionStore = useSessionStore()

// ── State ─────────────────────────────────────────────────
const messages = ref([])
const inputText = ref('')
const sending = ref(false)
const abortStream = ref(null)
const messageContainer = ref(null)
const loadingHistory = ref(false)

// Create session modal
const createSessionVisible = ref(false)
const createSessionSaving = ref(false)
const newSessionId = ref('')
const cloneEnabled = ref(false)
const cloneSourceId = ref(null)

// Settings modal
const settingsVisible = ref(false)
const apiKeyInput = ref('')
const apiKeyError = ref('')

// ── Computed ──────────────────────────────────────────────

const isDefaultSession = computed(() => sessionStore.activeSession === 'default')

const hasApiKey = computed(() => !!localStorage.getItem('rpg_openai_api_key'))

const workspaceOptions = computed(() =>
  workspaceStore.workspaces.map((w) => ({
    value: w.name,
    label: w.label,
  })),
)

const sessionOptions = computed(() =>
  sessionStore.sessions.map((s) => ({
    value: s.session_id || s,
    label: s.session_id || s,
  })),
)

// ── Lifecycle ─────────────────────────────────────────────

onMounted(async () => {
  await Promise.all([workspaceStore.load(), sessionStore.load()])
  await loadHistory()
})

// ── Watch session changes ────────────────────────────────

watch(
  () => sessionStore.activeSession,
  () => {
    messages.value = []
    loadHistory()
  },
)

// ── Slash-command definitions ──────────────────────────
const COMMANDS = [
  { command: '/clear', description: '清空当前会话的对话历史', detail: '重置对话上下文，清除所有已发送的消息记录。' },
  { command: '/compact', description: '压缩最老的对话轮次为摘要', detail: '可传参：/compact [压缩轮数] [保留轮数]，如 /compact 10 5' },
  { command: '/reload', description: '重新加载 RPG 数据（角色卡、世界书）', detail: '从磁盘重新读取角色卡和世界书文件变更。' },
  { command: '/history', description: '查看原始对话历史', detail: '显示所有历史消息的 role 和内容预览。' },
  { command: '/context', description: '查看当前上下文结构和 token 用量', detail: '显示 5 层 RPG 上下文的每层信息。' },
  { command: '/sessions', description: '列出所有可用会话', detail: '显示当前工作区下所有会话 ID 列表。' },
  { command: '/session-create', description: '创建新会话', detail: '用法：/session-create <会话ID>' },
  { command: '/session-switch', description: '切换到指定会话', detail: '用法：/session-switch <会话ID>' },
]

const showCommandPopup = ref(false)
const commandHighlightIndex = ref(0)
const inputRef = ref(null)
const commandPopupRef = ref(null)

const filteredCommands = computed(() => {
  const text = inputText.value
  if (!text.startsWith('/')) return COMMANDS
  const parts = text.split(/\s+/)
  if (parts.length <= 1) return COMMANDS
  const typed = parts[0].toLowerCase()
  if (COMMANDS.some(c => c.command === typed)) return []
  return COMMANDS.filter(c => c.command.startsWith(typed))
})

function onInputChange() {
  const text = inputText.value
  if (text === '/') {
    showCommandPopup.value = true
    commandHighlightIndex.value = 0
  } else if (!text.startsWith('/')) {
    showCommandPopup.value = false
  } else {
    const parts = text.split(/\s+/)
    const typed = parts[0].toLowerCase()
    if (typed === '/') {
      showCommandPopup.value = true
    } else if (COMMANDS.some(c => c.command.startsWith(typed))) {
      showCommandPopup.value = true
      commandHighlightIndex.value = 0
    } else {
      showCommandPopup.value = false
    }
  }
}

function closeCommandPopup() {
  showCommandPopup.value = false
}

function selectCommand(cmd) {
  inputText.value = cmd.command + ' '
  showCommandPopup.value = false
  inputRef.value?.focus()
}

function onCommandArrowUp() {
  if (!showCommandPopup.value) return
  const len = filteredCommands.value.length
  if (len === 0) return
  commandHighlightIndex.value = (commandHighlightIndex.value - 1 + len) % len
}

function onCommandArrowDown() {
  if (!showCommandPopup.value) return
  const len = filteredCommands.value.length
  if (len === 0) return
  commandHighlightIndex.value = (commandHighlightIndex.value + 1) % len
}

function onCommandTab() {
  if (!showCommandPopup.value) return
  const cmds = filteredCommands.value
  if (cmds.length === 0) return
  const idx = Math.min(commandHighlightIndex.value, cmds.length - 1)
  selectCommand(cmds[idx])
}

// ── Methods ───────────────────────────────────────────────

function goBack() {
  router.push('/overview')
}

async function loadHistory() {
  loadingHistory.value = true
  try {
    const res = await getHistory(sessionStore.activeSession)
    const history = res.data.history || []
    // Filter out system messages, keep user/assistant pairs
    messages.value = history
      .filter((m) => m.role === 'user' || m.role === 'assistant')
      .map((m) => ({
        role: m.role,
        content: m.content || '',
        thinking: null,
        tool_calls: [],
        stats: null,
        streaming: false,
      }))
    await scrollToBottom()
  } catch (e) {
    // Silent — empty history is fine
  } finally {
    loadingHistory.value = false
  }
}

async function handleSend() {
  const text = inputText.value.trim()
  if (!text || sending.value) return

  inputText.value = ''
  sending.value = true

  // Push user message
  messages.value.push({
    role: 'user',
    content: text,
    thinking: null,
    tool_calls: [],
    stats: null,
    streaming: false,
  })

  // Create empty assistant message for streaming
  const asstMsg = {
    role: 'assistant',
    content: '',
    thinking: null,
    tool_calls: [],
    stats: null,
    streaming: true,
  }
  messages.value.push(asstMsg)
  await scrollToBottom()

  // Accumulate tool calls across rounds
  const toolCallAcc = {}

  abortStream.value = streamMessage(
    text,
    sessionStore.activeSession,
    (event) => {
      switch (event.kind) {
        case 'text':
          asstMsg.content += event.content
          break
        case 'thinking':
          asstMsg.thinking = (asstMsg.thinking || '') + event.content
          break
        case 'tool_call':
          toolCallAcc[event.tool_name] = event
          break
        case 'tool_result':
          // Match tool result to the last tool call with the same name
          if (event.tool_name && toolCallAcc[event.tool_name]) {
            const existing = asstMsg.tool_calls.find(
              (t) => t.tool_name === event.tool_name,
            )
            if (!existing) {
              asstMsg.tool_calls.push({
                tool_name: event.tool_name,
                tool_arguments: toolCallAcc[event.tool_name].tool_arguments || '',
                tool_result_preview: event.tool_result_preview || '',
              })
            } else {
              existing.tool_result_preview = event.tool_result_preview || existing.tool_result_preview
            }
          }
          break
        case 'done':
          asstMsg.streaming = false
          asstMsg.stats = event.usage || null
          sending.value = false
          break
        case 'error':
          asstMsg.streaming = false
          asstMsg.content += `\n\n[错误] ${event.content}`
          sending.value = false
          message.error(event.content)
          break
      }
      scrollToBottom()
    },
  )
}

function handleStop() {
  if (abortStream.value) {
    abortStream.value()
    abortStream.value = null
    sending.value = false
    // Mark the last assistant message as done
    const last = messages.value[messages.value.length - 1]
    if (last && last.role === 'assistant' && last.streaming) {
      last.streaming = false
    }
  }
}

function onSendKeydown(e) {
  if (e.shiftKey) return // Shift+Enter = newline
  handleSend()
}

async function scrollToBottom() {
  await nextTick()
  if (messageContainer.value) {
    messageContainer.value.scrollTop = messageContainer.value.scrollHeight
  }
}

function renderContent(text) {
  if (!text) return ''
  // Escape HTML, then convert newlines to <br>
  const escaped = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
  return escaped.replace(/\n/g, '<br>')
}

// ── Workspace ─────────────────────────────────────────────

function onWorkspaceChange(value) {
  if (value !== workspaceStore.activeWorkspace) {
    workspaceStore.switchWorkspace(value)
  }
}

// ── Session handlers ──────────────────────────────────────

function onSessionChange(value) {
  if (value !== sessionStore.activeSession) {
    sessionStore.switchSession(value)
  }
}

function openCreateSession() {
  newSessionId.value = ''
  cloneEnabled.value = false
  cloneSourceId.value = null
  createSessionVisible.value = true
}

function resetCreateSessionForm() {
  createSessionVisible.value = false
  newSessionId.value = ''
  cloneEnabled.value = false
  cloneSourceId.value = null
}

async function handleCreateSession() {
  if (!newSessionId.value.trim()) return
  createSessionSaving.value = true
  try {
    if (cloneEnabled.value && cloneSourceId.value) {
      await sessionStore.duplicateSession(cloneSourceId.value, newSessionId.value)
    } else {
      await sessionStore.createNewSession(newSessionId.value)
    }
    createSessionVisible.value = false
    sessionStore.switchSession(newSessionId.value)
  } catch (e) {
    message.error('创建会话失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    createSessionSaving.value = false
  }
}

async function handleDeleteSession() {
  try {
    await sessionStore.removeSession(sessionStore.activeSession)
    message.success('会话已删除')
  } catch (e) {
    message.error('删除会话失败: ' + (e.response?.data?.detail || e.message))
  }
}

// ── Settings handlers ─────────────────────────────────────

function openSettings() {
  apiKeyInput.value = localStorage.getItem('rpg_openai_api_key') || ''
  apiKeyError.value = ''
  settingsVisible.value = true
}

function handleSaveSettings() {
  const trimmed = apiKeyInput.value.trim()
  if (!trimmed) {
    localStorage.removeItem('rpg_openai_api_key')
  } else {
    localStorage.setItem('rpg_openai_api_key', trimmed)
  }
  settingsVisible.value = false
  message.success(trimmed ? 'API Key 已保存' : 'API Key 已清除')
  // Reload history so the next request uses the new key
  messages.value = []
  loadHistory()
}
</script>

<style scoped>
/* ── Page layout ───────────────────────────────────────── */
.chat-page {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: var(--bg-color);
  overflow: hidden;
}

/* ── Header ────────────────────────────────────────────── */
.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 16px;
  background: var(--card-bg);
  border-bottom: 1px solid var(--border-color);
  flex-shrink: 0;
  gap: 8px;
  flex-wrap: wrap;
}
.header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}
.header-center {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-color);
}
.header-right {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.back-btn {
  color: var(--text-color);
}

/* ── Message container ─────────────────────────────────── */
.message-container {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
}
.loading-history {
  text-align: center;
  color: var(--text-secondary);
  padding: 24px;
}

/* ── Message bubbles ───────────────────────────────────── */
.message-row {
  display: flex;
  flex-direction: column;
}
.is-user {
  align-items: flex-end;
}
.is-assistant {
  align-items: flex-start;
}
.message-bubble {
  max-width: 75%;
  padding: 10px 14px;
  border-radius: 12px;
  background: var(--card-bg);
  border: 1px solid var(--border-color);
  word-break: break-word;
}
.is-user .message-bubble {
  background: #1677ff;
  color: #fff;
  border-color: #1677ff;
}
.is-assistant .message-bubble {
  background: var(--card-bg);
  color: var(--text-color);
}

.msg-role {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  opacity: 0.7;
  margin-bottom: 4px;
}

.is-user .msg-content {
  color: #fff;
}

/* ── Thinking section ──────────────────────────────────── */
.msg-thinking {
  margin: 4px 0;
  font-size: 13px;
  background: rgba(128, 128, 128, 0.08);
  border-radius: 6px;
  padding: 4px 8px;
}
.is-user .msg-thinking {
  background: rgba(255, 255, 255, 0.12);
}
.thinking-text {
  font-size: 12px;
  color: var(--text-secondary);
  white-space: pre-wrap;
  margin: 0;
  max-height: 120px;
  overflow-y: auto;
}

/* ── Tool calls ────────────────────────────────────────── */
.msg-tools {
  margin-top: 6px;
  font-size: 12px;
}
.is-user .msg-tools {
  display: none;
}
.tool-item {
  padding: 4px 0;
  border-bottom: 1px solid var(--border-color);
}
.tool-item:last-child {
  border-bottom: none;
}
.tool-item code {
  font-size: 12px;
  color: #1677ff;
  word-break: break-all;
}
.tool-result {
  font-size: 11px;
  color: var(--text-secondary);
  margin-top: 2px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ── Stats footer ──────────────────────────────────────── */
.msg-stats {
  margin-top: 6px;
  font-size: 10px;
  opacity: 0.5;
  text-align: right;
}

/* ── Streaming indicator ───────────────────────────────── */
.streaming-indicator {
  display: inline-flex;
  align-items: center;
  margin-top: 4px;
  gap: 4px;
  font-size: 12px;
  opacity: 0.6;
}

/* ── Slash-command popup ──────────────────────────────── */
.command-popup {
  position: absolute;
  bottom: 100%;
  left: 0;
  right: 0;
  max-height: 240px;
  overflow-y: auto;
  background: var(--card-bg);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  margin-bottom: 4px;
  z-index: 100;
}
.command-popup-title {
  padding: 6px 12px;
  font-size: 11px;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  border-bottom: 1px solid var(--border-color);
}
.command-item {
  display: flex;
  align-items: baseline;
  padding: 8px 12px;
  cursor: pointer;
  gap: 8px;
  transition: background 0.15s;
}
.command-item:hover,
.command-item.active {
  background: var(--active-bg);
}
.cmd-name {
  font-family: monospace;
  font-size: 13px;
  font-weight: 600;
  color: #1677ff;
  white-space: nowrap;
  flex-shrink: 0;
}
.cmd-desc {
  font-size: 12px;
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.input-relative {
  position: relative;
}

/* ── Input area ────────────────────────────────────────── */
.input-area {
  flex-shrink: 0;
  padding: 12px 16px;
  background: var(--card-bg);
  border-top: 1px solid var(--border-color);
}
.input-wrapper {
  max-width: 800px;
  margin: 0 auto;
}
.chat-input {
  resize: none;
}
.input-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 6px;
}
.input-hint {
  font-size: 11px;
  color: var(--text-secondary);
}
.input-buttons {
  display: flex;
  gap: 6px;
}
</style>
