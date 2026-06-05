<template>
  <div class="overview">
    <a-card>
      <template #title>
        <DashboardOutlined /> RPG World
      </template>
      <a-result
        status="success"
        title="欢迎使用 RPG World"
      >
        <template #icon>
          <DashboardOutlined />
        </template>
        <template #extra>
          <a-button type="primary" size="large" @click="$router.push('/chat')">
            <MessageOutlined /> 进入聊天
          </a-button>
        </template>
      </a-result>
    </a-card>
  </div>
</template>

<script setup>
import { DashboardOutlined, MessageOutlined } from '@ant-design/icons-vue'
</script>

<style scoped>
.overview {
  max-width: 800px;
  margin: 0 auto;
}
</style>
