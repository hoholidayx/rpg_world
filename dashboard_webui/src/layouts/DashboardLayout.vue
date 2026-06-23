<template>
  <a-layout class="dashboard-layout">
    <!-- Mobile header -->
    <a-layout-header class="mobile-header">
      <a-button type="text" class="menu-trigger" @click="drawerVisible = true">
        <MenuOutlined />
      </a-button>
      <span class="header-title">RPG World</span>
      <div class="header-actions">
        <ThemeToggle />
      </div>
    </a-layout-header>

    <!-- Desktop sidebar -->
    <a-layout-sider
      v-if="!isMobile"
      v-model:collapsed="collapsed"
      :trigger="null"
      collapsible
      class="desktop-sider"
      :width="220"
      :collapsed-width="64"
      :theme="siderTheme"
    >
      <div class="logo">{{ collapsed ? 'RPG' : 'RPG World' }}</div>

      <!-- Workspace selector -->
      <div v-if="!collapsed" class="workspace-section">
        <div class="workspace-row">
          <a-select
            :value="workspaceStore.current"
            :options="workspaceOptions"
            size="small"
            style="flex: 1;"
            :loading="workspaceStore.loading || workspaceStore.switching"
            :disabled="workspaceStore.loading || workspaceStore.switching"
            @change="onWorkspaceChange"
          />
          <a-tooltip title="新建工作区">
            <a-button size="small" type="text" @click="showWorkspaceModal('create')" class="ws-action-btn">
              <PlusOutlined />
            </a-button>
          </a-tooltip>
          <template v-if="workspaceStore.current">
            <a-tooltip title="重命名">
              <a-button size="small" type="text" @click="showWorkspaceModal('rename', workspaceStore.current)" class="ws-action-btn">
                <EditOutlined />
              </a-button>
            </a-tooltip>
            <a-tooltip title="删除">
              <a-button size="small" type="text" @click="showWorkspaceModal('delete', workspaceStore.current)" class="ws-action-btn">
                <DeleteOutlined />
              </a-button>
            </a-tooltip>
          </template>
        </div>
      </div>


      <a-menu
        v-model:selectedKeys="selectedKeys"
        mode="inline"
        :theme="siderTheme"
        @click="onMenuClick"
      >
        <a-menu-item key="/overview">
          <DashboardOutlined />
          <span>概览</span>
        </a-menu-item>
        <a-menu-item key="/chat">
          <MessageOutlined />
          <span>聊天</span>
        </a-menu-item>
        <a-menu-item key="/characters">
          <UserOutlined />
          <span>角色卡管理</span>
        </a-menu-item>
        <a-menu-item key="/lorebook">
          <BookOutlined />
          <span>世界书管理</span>
        </a-menu-item>
        <a-menu-item key="/status">
          <ProfileOutlined />
          <span>状态管理</span>
        </a-menu-item>
      </a-menu>
      <div class="sider-footer">
        <ThemeToggle />
        <a-button
          type="text"
          size="small"
          class="collapse-btn"
          @click="collapsed = !collapsed"
        >
          <LeftOutlined v-if="!collapsed" />
          <RightOutlined v-else />
        </a-button>
      </div>
    </a-layout-sider>

    <!-- Mobile drawer -->
    <a-drawer
      v-else
      v-model:open="drawerVisible"
      placement="left"
      :width="260"
      :closable="false"
      :body-style="{ padding: 0 }"
    >
      <div class="drawer-header">
        <span class="drawer-title">RPG World</span>
      </div>
      <!-- Workspace selector (mobile) -->
      <div class="drawer-workspace">
        <span class="drawer-ws-label"><FolderOutlined /> 工作区</span>
        <a-select
          :value="workspaceStore.current"
          :options="workspaceOptions"
          size="small"
          style="width: 100%; margin-top: 8px;"
          :loading="workspaceStore.loading || workspaceStore.switching"
          :disabled="workspaceStore.loading || workspaceStore.switching"
          @change="onWorkspaceChange"
        />
      </div>

      <a-menu
        v-model:selectedKeys="selectedKeys"
        mode="inline"
        @click="onMenuClick"
      >
        <a-menu-item key="/overview">
          <DashboardOutlined />
          <span>概览</span>
        </a-menu-item>
        <a-menu-item key="/chat">
          <MessageOutlined />
          <span>聊天</span>
        </a-menu-item>
        <a-menu-item key="/characters">
          <UserOutlined />
          <span>角色卡管理</span>
        </a-menu-item>
        <a-menu-item key="/lorebook">
          <BookOutlined />
          <span>世界书管理</span>
        </a-menu-item>
        <a-menu-item key="/status">
          <ProfileOutlined />
          <span>状态管理</span>
        </a-menu-item>
      </a-menu>
      <div style="padding: 16px; border-top: 1px solid #f0f0f0; margin-top: 16px;">
        <ThemeToggle />
      </div>
    </a-drawer>

    <!-- Content -->
    <a-layout>
      <a-layout-content class="content-area">
        <router-view :key="workspaceStore.current" />
      </a-layout-content>
    </a-layout>

    <!-- Workspace management modal -->
    <a-modal
      v-model:open="wsModalVisible"
      :title="wsModalTitle"
      :confirm-loading="wsModalSaving"
      @ok="handleWsModalOk"
      @cancel="resetWsModal"
      :destroy-on-close="true"
      :width="400"
      :ok-button-props="wsModalMode === 'delete' ? { danger: true } : undefined"
      :ok-text="wsModalMode === 'delete' ? '确认删除' : undefined"
    >
      <a-form layout="vertical">
        <template v-if="wsModalMode === 'delete'">
          <p>确定要删除工作区 <strong>{{ wsFormTarget }}</strong> 吗？</p>
          <p style="color: var(--text-secondary); font-size: 13px;">
            此操作不可恢复，工作区内的所有数据（角色卡、世界书、会话等）将被永久删除。
          </p>
        </template>
        <template v-else>
          <a-form-item label="工作区名称" :required="true">
            <a-input
              v-model:value="wsFormName"
              :placeholder="wsModalMode === 'create' ? '如：我的世界' : ''"
            />
          </a-form-item>
        </template>
      </a-form>
    </a-modal>
  </a-layout>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import {
  MenuOutlined,
  MessageOutlined,
  LeftOutlined,
  RightOutlined,
  DashboardOutlined,
  UserOutlined,
  BookOutlined,
  ProfileOutlined,
  FolderOutlined,
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
} from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import ThemeToggle from '@/components/ThemeToggle.vue'
import { extractApiError } from '@/api/index'
import { useThemeStore } from '@/stores/theme'
import { useWorkspaceStore } from '@/stores/workspace'

const router = useRouter()
const route = useRoute()
const themeStore = useThemeStore()
const workspaceStore = useWorkspaceStore()

const collapsed = ref(false)
const drawerVisible = ref(false)
const selectedKeys = ref([route.path])
const isMobile = ref(false)

// ── Workspace management modal state ──────────────────────────────────

const wsModalVisible = ref(false)
const wsModalMode = ref('create') // 'create' | 'rename' | 'delete'
const wsModalSaving = ref(false)
const wsFormName = ref('')
const wsFormTarget = ref('') // current workspace name for rename/delete

function checkMobile() {
  isMobile.value = window.innerWidth < 768
}

onMounted(() => {
  checkMobile()
  window.addEventListener('resize', checkMobile)
  workspaceStore.load().catch((err) => {
    message.error(extractApiError(err, '工作区加载失败'))
  })
})
onUnmounted(() => {
  window.removeEventListener('resize', checkMobile)
})

const siderTheme = computed(() =>
  themeStore.effective === 'dark' ? 'dark' : 'light',
)

const workspaceOptions = computed(() =>
  workspaceStore.workspaces.map((w) => ({
    value: w.name,
    label: w.label,
  })),
)

const wsModalTitle = computed(() => {
  switch (wsModalMode.value) {
    case 'create': return '新建工作区'
    case 'rename': return '重命名工作区'
    case 'delete': return '删除工作区'
    default: return ''
  }
})

watch(
  () => route.path,
  (p) => {
    selectedKeys.value = [p]
  },
)

function onMenuClick({ key }) {
  router.push({ path: key, query: route.query })
  drawerVisible.value = false
}

function onWorkspaceChange(value) {
  const name = typeof value === 'object' ? value.key : value
  if (name !== workspaceStore.current) {
    workspaceStore.switchWorkspace(name).catch((err) => {
      message.error(extractApiError(err, '切换工作区失败'))
    })
  }
}

// ── Workspace CRUD handlers ───────────────────────────────────────────

function showWorkspaceModal(mode, workspaceName) {
  wsModalMode.value = mode
  wsFormName.value = ''
  wsFormTarget.value = workspaceName || ''
  if (mode === 'rename') {
    wsFormName.value = (workspaceName || '').replace(/^data\//, '')
  }
  if (mode === 'create') {
    wsFormTarget.value = ''
  }
  wsModalVisible.value = true
}

function resetWsModal() {
  wsModalVisible.value = false
  wsFormName.value = ''
  wsFormTarget.value = ''
}

async function handleWsModalOk() {
  const name = wsFormName.value.trim()
  if (!name && wsModalMode.value !== 'delete') {
    message.warning('请输入工作区名称')
    return
  }
  wsModalSaving.value = true
  try {
    if (wsModalMode.value === 'create') {
      await workspaceStore.createWorkspace(name)
      message.success('工作区已创建')
    } else if (wsModalMode.value === 'rename') {
      await workspaceStore.renameWorkspace(wsFormTarget.value, name)
      message.success('工作区已重命名')
    } else if (wsModalMode.value === 'delete') {
      await workspaceStore.deleteWorkspace(wsFormTarget.value)
      message.success('工作区已删除')
    }
    wsModalVisible.value = false
    await workspaceStore.load()
  } catch (e) {
    message.error(extractApiError(e, '操作失败'))
  } finally {
    wsModalSaving.value = false
  }
}
</script>

<style scoped>
.dashboard-layout {
  min-height: 100vh;
}

/* ---- Mobile header ---- */
.mobile-header {
  display: none;
  align-items: center;
  padding: 0 16px;
  background: var(--sider-bg);
  height: 48px;
  position: sticky;
  top: 0;
  z-index: 100;
}
.menu-trigger {
  color: #fff;
  font-size: 18px;
  margin-right: 12px;
}
.header-title {
  color: #fff;
  font-size: 16px;
  font-weight: 600;
  flex: 1;
}
.header-actions {
  display: flex;
  align-items: center;
}

/* ---- Desktop sidebar ---- */
.desktop-sider {
  position: sticky;
  top: 0;
  height: 100vh;
  overflow: auto;
  left: 0;
}
.logo {
  height: 48px;
  line-height: 48px;
  text-align: center;
  color: #fff;
  font-weight: 700;
  font-size: 16px;
  white-space: nowrap;
  overflow: hidden;
}
.sider-footer {
  position: absolute;
  bottom: 12px;
  width: 100%;
  display: flex;
  justify-content: center;
  gap: 8px;
  align-items: center;
}
.collapse-btn {
  color: rgba(255, 255, 255, 0.65);
}

/* ---- Drawer ---- */
.drawer-header {
  height: 48px;
  line-height: 48px;
  padding: 0 24px;
  background: var(--sider-bg);
  color: #fff;
  font-weight: 700;
  font-size: 16px;
}

/* ---- Content ---- */
.content-area {
  margin: 16px;
  min-height: calc(100vh - 32px);
}

/* ---- Workspace Selector ---- */
.workspace-section {
  padding: 8px 12px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  margin-bottom: 4px;
}
.workspace-row {
  display: flex;
  align-items: center;
  gap: 4px;
}
.ws-action-btn {
  color: rgba(255, 255, 255, 0.55);
  font-size: 13px;
  flex-shrink: 0;
}
.ws-action-btn:hover {
  color: #fff;
}
.drawer-workspace {
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-color);
}
.drawer-ws-label {
  font-size: 13px;
  color: var(--text-secondary);
}

/* ---- Responsive ---- */
@media (max-width: 767px) {
  .mobile-header {
    display: flex;
  }
  .desktop-sider {
    display: none !important;
  }
  .content-area {
    margin: 8px;
    min-height: calc(100vh - 64px);
  }
}
</style>
