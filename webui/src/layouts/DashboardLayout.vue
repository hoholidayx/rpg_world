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
        <a-dropdown :trigger="['click']" placement="bottomLeft">
          <div class="workspace-trigger">
            <FolderOutlined />
            <span class="ws-label">{{ activeWorkspaceLabel }}</span>
            <DownOutlined class="ws-arrow" />
          </div>
          <template #overlay>
            <a-menu @click="onWorkspaceChange" :selectedKeys="[workspaceStore.activeWorkspace]">
              <a-menu-item v-for="ws in workspaceStore.workspaces" :key="ws.name">
                {{ ws.label }}
              </a-menu-item>
            </a-menu>
          </template>
        </a-dropdown>
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
        <a-menu-item key="/characters">
          <UserOutlined />
          <span>角色卡管理</span>
        </a-menu-item>
        <a-menu-item key="/lorebook">
          <BookOutlined />
          <span>世界书管理</span>
        </a-menu-item>
        <a-menu-item key="/milestones">
          <FlagOutlined />
          <span>里程碑管理</span>
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
          v-model:value="workspaceStore.activeWorkspace"
          :options="workspaceOptions"
          size="small"
          style="width: 100%; margin-top: 8px;"
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
        <a-menu-item key="/characters">
          <UserOutlined />
          <span>角色卡管理</span>
        </a-menu-item>
        <a-menu-item key="/lorebook">
          <BookOutlined />
          <span>世界书管理</span>
        </a-menu-item>
        <a-menu-item key="/milestones">
          <FlagOutlined />
          <span>里程碑管理</span>
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
        <router-view />
      </a-layout-content>
    </a-layout>
  </a-layout>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import {
  MenuOutlined,
  LeftOutlined,
  RightOutlined,
  DashboardOutlined,
  UserOutlined,
  BookOutlined,
  FlagOutlined,
  ProfileOutlined,
  FolderOutlined,
  DownOutlined,
} from '@ant-design/icons-vue'
import ThemeToggle from '@/components/ThemeToggle.vue'
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

function checkMobile() {
  isMobile.value = window.innerWidth < 768
}

onMounted(() => {
  checkMobile()
  window.addEventListener('resize', checkMobile)
  workspaceStore.load()
})
onUnmounted(() => {
  window.removeEventListener('resize', checkMobile)
})

const siderTheme = computed(() =>
  themeStore.effective === 'dark' ? 'dark' : 'light',
)

const activeWorkspaceLabel = computed(() => {
  const found = workspaceStore.workspaces.find(
    (w) => w.name === workspaceStore.activeWorkspace,
  )
  return found ? found.label : '默认工作区'
})

const workspaceOptions = computed(() =>
  workspaceStore.workspaces.map((w) => ({
    value: w.name,
    label: w.label,
  })),
)

watch(
  () => route.path,
  (p) => {
    selectedKeys.value = [p]
  },
)

function onMenuClick({ key }) {
  router.push(key)
  drawerVisible.value = false
}

function onWorkspaceChange(value) {
  // Desktop a-menu passes { key }, mobile a-select passes the value directly
  const name = typeof value === 'object' ? value.key : value
  if (name !== workspaceStore.activeWorkspace) {
    workspaceStore.switchWorkspace(name)
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
  padding: 4px 12px 8px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  margin-bottom: 4px;
}
.workspace-trigger {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  border-radius: 6px;
  cursor: pointer;
  color: rgba(255, 255, 255, 0.75);
  font-size: 13px;
  transition: background 0.2s, color 0.2s;
}
.workspace-trigger:hover {
  background: rgba(255, 255, 255, 0.08);
  color: #fff;
}
.ws-label {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ws-arrow {
  font-size: 10px;
  color: rgba(255, 255, 255, 0.45);
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
