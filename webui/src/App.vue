<template>
  <a-config-provider :theme="themeConfig">
    <DashboardLayout />
  </a-config-provider>
</template>

<script setup>
import { computed } from 'vue'
import { theme } from 'ant-design-vue'
import DashboardLayout from '@/layouts/DashboardLayout.vue'
import { useThemeStore } from '@/stores/theme'

const themeStore = useThemeStore()

const themeConfig = computed(() => ({
  algorithm:
    themeStore.effective === 'dark'
      ? theme.darkAlgorithm
      : theme.defaultAlgorithm,
}))
</script>

<style>
/* Global theme variables */
:root {
  --bg-color: #f0f2f5;
  --card-bg: #fff;
  --text-color: rgba(0, 0, 0, 0.88);
  --text-secondary: #999;
  --text-tertiary: #bbb;
  --sider-bg: #001529;
  --header-bg: #fafafa;
  --border-color: #e8e8e8;
  --hover-bg: rgba(0, 0, 0, 0.04);
  --active-bg: rgba(24, 144, 255, 0.1);
}

[data-theme='dark'] {
  --bg-color: #141414;
  --card-bg: #1f1f1f;
  --text-color: rgba(255, 255, 255, 0.85);
  --text-secondary: rgba(255, 255, 255, 0.45);
  --text-tertiary: rgba(255, 255, 255, 0.3);
  --sider-bg: #141414;
  --header-bg: #2a2a2a;
  --border-color: #303030;
  --hover-bg: rgba(255, 255, 255, 0.04);
  --active-bg: rgba(24, 144, 255, 0.2);
}

body {
  margin: 0;
  background: var(--bg-color);
  color: var(--text-color);
  transition: background 0.3s, color 0.3s;
}
</style>
