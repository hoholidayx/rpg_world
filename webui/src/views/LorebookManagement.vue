<template>
  <div class="lorebook-mgmt">
    <!-- Header bar -->
    <div class="page-header">
      <h2>世界书管理</h2>
      <div class="header-actions">
        <a-input-search
          v-model:value="searchText"
          placeholder="搜索名称或内容"
          allow-clear
          style="width: 260px"
        />
        <a-button type="primary" @click="openCreate">
          <template #icon><PlusOutlined /></template>
          新增条目
        </a-button>
      </div>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="loading-container">
      <a-spin size="large" />
    </div>

    <!-- Table -->
    <a-table
      v-else
      :data-source="filteredItems"
      :columns="columns"
      :pagination="{ pageSize: 20, showSizeChanger: true, showTotal: (t) => `共 ${t} 条` }"
      row-key="name"
      :scroll="{ x: 700 }"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'enable'">
          <a-switch
            :checked="!!record.enable"
            @change="(v) => toggleEnable(record, v)"
          />
        </template>

        <template v-if="column.key === 'tags'">
          <a-tag
            v-for="tag in record.tags || []"
            :key="tag"
            color="blue"
          >
            {{ tag }}
          </a-tag>
          <span v-if="!record.tags?.length" class="no-tags">-</span>
        </template>

        <template v-if="column.key === 'actions'">
          <a-space>
            <a-button type="link" size="small" @click="openEdit(record)">
              编辑
            </a-button>
            <a-popconfirm
              title="确定删除此条目？"
              @confirm="handleDelete(record)"
            >
              <a-button type="link" danger size="small">删除</a-button>
            </a-popconfirm>
          </a-space>
        </template>
      </template>

      <template #emptyText>
        <a-empty description="暂无条目，点击「新增条目」创建" />
      </template>
    </a-table>

    <!-- Create / Edit Modal -->
    <a-modal
      v-model:open="modalVisible"
      :title="editing ? '编辑条目' : '新增条目'"
      :confirm-loading="saving"
      @ok="handleSave"
      @cancel="resetForm"
      :destroy-on-close="true"
      :width="560"
    >
      <a-form ref="formRef" :model="form" :rules="rules" layout="vertical">
        <a-form-item label="名称" name="name">
          <a-input
            v-model:value="form.name"
            placeholder="条目名称"
          />
        </a-form-item>

        <a-form-item label="启用状态" name="enable">
          <a-switch v-model:checked="form.enable" />
          <span class="form-hint">
            {{ form.enable ? '已启用（参与上下文渲染）' : '已禁用' }}
          </span>
        </a-form-item>

        <!-- Tags -->
        <a-form-item label="标签">
          <a-space wrap>
            <a-tag
              v-for="(tag, i) in form.tags"
              :key="i"
              closable
              @close="removeTag(i)"
            >
              {{ tag }}
            </a-tag>
            <a-input
              v-if="tagInputVisible"
              ref="tagInputRef"
              v-model:value="tagInput"
              type="text"
              size="small"
              style="width: 90px"
              @press-enter="addTag"
              @blur="addTag"
            />
            <a-button
              v-else
              size="small"
              type="dashed"
              @click="showTagInput"
            >
              <PlusOutlined /> 添加标签
            </a-button>
          </a-space>
        </a-form-item>

        <!-- Dynamic fields -->
        <a-form-item
          v-for="(val, key) in dynamicFields"
          :key="key"
          :label="key"
        >
          <a-input
            :value="val"
            @change="(e) => (dynamicFields[key] = e.target.value)"
            :placeholder="key"
          />
          <a-button
            type="link"
            danger
            size="small"
            class="field-remove"
            @click="removeField(key)"
          >
            移除
          </a-button>
        </a-form-item>

        <a-form-item>
          <a-button type="dashed" block @click="addField">
            <PlusOutlined /> 添加自定义字段
          </a-button>
        </a-form-item>

        <a-form-item label="内容" name="content">
          <a-textarea
            v-model:value="form.content"
            :rows="4"
            placeholder="条目内容"
          />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { PlusOutlined } from '@ant-design/icons-vue'
import { useCRUD } from '@/composables/useCRUD'
import {
  listEntries,
  createEntry,
  updateEntry,
  deleteEntry,
} from '@/api/lorebook'

const searchText = ref('')

const otherNames = computed(() => {
  const current = editing.value
  return items.value
    .filter((item) => item.name !== current)
    .map((item) => item.name.toLowerCase())
})

const filteredItems = computed(() => {
  const keyword = searchText.value.trim().toLowerCase()
  if (!keyword) return items.value
  return items.value.filter(
    (item) =>
      item.name.toLowerCase().includes(keyword) ||
      (item.content || '').toLowerCase().includes(keyword),
  )
})

const columns = [
  { title: '名称', dataIndex: 'name', key: 'name', width: 180 },
  { title: '启用', key: 'enable', width: 80, align: 'center' },
  { title: '标签', key: 'tags', width: 200 },
  { title: '内容', dataIndex: 'content', key: 'content', ellipsis: true },
  { title: '操作', key: 'actions', width: 140, fixed: 'right' },
]

const {
  items,
  loading,
  modalVisible,
  saving,
  editing,
  formRef,
  form,
  dynamicFields,
  rules,
  tagInputVisible,
  tagInput,
  tagInputRef,
  loadData,
  openCreate,
  openEdit,
  resetForm,
  handleSave,
  handleDelete,
  toggleEnable,
  showTagInput,
  addTag,
  removeTag,
  addField,
  removeField,
} = useCRUD({
  listFn: listEntries,
  createFn: createEntry,
  updateFn: updateEntry,
  deleteFn: deleteEntry,
  fixedFields: ['name', 'enable', 'content', 'tags'],
  hasTags: true,
  nameLabel: '条目名称',
})

// Name uniqueness validator (frontend check before backend submit)
const nameValidator = async (_rule, value) => {
  if (!value) return
  if (otherNames.value.includes(value.trim().toLowerCase())) {
    throw new Error('名称已存在，请使用其他名称')
  }
}
rules.name = [
  ...rules.name,
  { validator: nameValidator, trigger: 'change' },
]

onMounted(loadData)
</script>

<style scoped>
.lorebook-mgmt {
  background: var(--card-bg);
  border-radius: 8px;
  padding: 24px;
}
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  flex-wrap: wrap;
  gap: 8px;
}
.header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.page-header h2 {
  margin: 0;
  font-size: 20px;
}
.loading-container {
  text-align: center;
  padding: 48px 0;
}
.form-hint {
  margin-left: 8px;
  color: var(--text-secondary, #999);
  font-size: 12px;
}
.field-remove {
  margin-left: 8px;
}
.no-tags {
  color: var(--text-tertiary, #bbb);
}
</style>
