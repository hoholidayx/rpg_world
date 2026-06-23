<template>
  <div class="character-mgmt">
    <!-- Header bar -->
    <div class="page-header">
      <h2>角色卡管理</h2>
      <a-button type="primary" @click="openCreate">
        <template #icon><PlusOutlined /></template>
        新增角色
      </a-button>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="loading-container">
      <a-spin size="large" />
    </div>

    <!-- Table -->
    <a-table
      v-else
      :data-source="items"
      :columns="columns"
      :pagination="false"
      row-key="name"
      :scroll="{ x: 600 }"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'enable'">
          <a-switch
            :checked="!!record.enable"
            @change="(v) => toggleEnable(record, v)"
          />
        </template>

        <template v-if="column.key === 'detailCount'">
          <a-tag v-if="record.details?.length" color="blue">
            {{ record.details.length }} 条
          </a-tag>
          <span v-else class="no-data">-</span>
        </template>

        <template v-if="column.key === 'actions'">
          <a-space>
            <a-button type="link" size="small" @click="openEdit(record)">
              编辑
            </a-button>
            <a-button type="link" size="small" @click="openDetailsDrawer(record)">
              设定详情
            </a-button>
            <a-popconfirm
              title="确定删除此角色卡？"
              @confirm="handleDelete(record)"
            >
              <a-button type="link" danger size="small">删除</a-button>
            </a-popconfirm>
          </a-space>
        </template>
      </template>

      <template #emptyText>
        <a-empty description="暂无角色卡，点击「新增角色」创建" />
      </template>
    </a-table>

    <!-- Create / Edit Modal -->
    <a-modal
      v-model:open="modalVisible"
      :title="editing ? '编辑角色卡' : '新增角色卡'"
      :confirm-loading="saving"
      @ok="handleSave"
      @cancel="resetForm"
      :destroy-on-close="true"
      :width="560"
    >
      <a-form
        ref="formRef"
        :model="form"
        :rules="rules"
        layout="vertical"
      >
        <a-form-item label="名称" name="name">
          <a-input
            v-model:value="form.name"
            placeholder="角色名称"
          />
        </a-form-item>

        <a-form-item label="启用状态" name="enable">
          <a-switch v-model:checked="form.enable" />
          <span class="form-hint">
            {{ form.enable ? '已启用（参与上下文渲染）' : '已禁用' }}
          </span>
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
            size="extra-small"
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
            placeholder="角色描述 / 背景故事"
          />
        </a-form-item>
      </a-form>
    </a-modal>

    <!-- ==================== L2 Detail Drawer ==================== -->
    <a-drawer
      v-model:open="drawerVisible"
      :title="`${targetCharacter?.name || ''} — 设定详情`"
      :width="720"
      :destroy-on-close="false"
      placement="right"
    >
      <!-- Toolbar -->
      <div class="detail-toolbar">
        <a-input-search
          v-model:value="detailSearch"
          placeholder="搜索名称或内容"
          allow-clear
          style="max-width: 260px"
        />
        <a-button type="primary" @click="openDetailCreate">
          <template #icon><PlusOutlined /></template>
          新增设定
        </a-button>
      </div>

      <!-- Detail loading -->
      <a-spin :spinning="detailsLoading">
        <!-- Detail list as expandable cards -->
        <div v-if="filteredDetails.length" class="detail-list">
          <div
            v-for="detail in filteredDetails"
            :key="detail.name"
            class="detail-card"
          >
            <!-- Card header (always visible) -->
            <div class="detail-card-header">
              <div class="detail-title-area">
                <span class="detail-name">{{ detail.name }}</span>
                <a-switch
                  :checked="!!detail.enable"
                  size="small"
                  @change="(v) => toggleDetailEnable(detail, v)"
                />
              </div>
              <div class="detail-actions">
                <a-button type="text" size="small" @click="openDetailEdit(detail)">
                  <EditOutlined /> 编辑
                </a-button>
                <a-popconfirm
                  title="确定删除此设定？"
                  @confirm="handleDeleteDetail(detail)"
                >
                  <a-button type="text" danger size="small">
                    <DeleteOutlined /> 删除
                  </a-button>
                </a-popconfirm>
              </div>
            </div>

            <!-- Tags -->
            <div v-if="detail.tags?.length" class="detail-tags">
              <a-tag v-for="tag in detail.tags" :key="tag" color="blue">
                {{ tag }}
              </a-tag>
            </div>

            <!-- Expandable content -->
            <a-collapse :bordered="false" ghost>
              <a-collapse-panel header="查看内容" key="content">
                <div class="detail-content">{{ detail.content }}</div>
              </a-collapse-panel>
            </a-collapse>
          </div>
        </div>

        <!-- Empty state -->
        <a-empty
          v-else
          :description="detailSearch ? '无匹配的设定' : '暂无设定详情'"
        />
      </a-spin>
    </a-drawer>

    <!-- Detail Create / Edit Modal (inside drawer flow) -->
    <a-modal
      v-model:open="detailModalVisible"
      :title="detailEditing ? '编辑设定' : '新增设定'"
      :confirm-loading="detailSaving"
      @ok="handleSaveDetail"
      @cancel="resetDetailForm"
      :destroy-on-close="true"
      :width="640"
    >
      <a-form
        ref="detailFormRef"
        :model="detailForm"
        :rules="detailRules"
        layout="vertical"
      >
        <a-form-item label="名称" name="name">
          <a-input
            v-model:value="detailForm.name"
            placeholder="设定名称（如：R18性格、战斗风格）"
            :disabled="!!detailEditing"
          />
        </a-form-item>

        <a-form-item label="启用状态" name="enable">
          <a-switch v-model:checked="detailForm.enable" />
          <span class="form-hint">
            {{ detailForm.enable ? '已启用（参与上下文渲染）' : '已禁用' }}
          </span>
        </a-form-item>

        <!-- Tags -->
        <a-form-item label="标签">
          <a-space wrap>
            <a-tag
              v-for="(tag, i) in detailForm.tags"
              :key="i"
              closable
              @close="detailForm.tags.splice(i, 1)"
            >
              {{ tag }}
            </a-tag>
            <a-input
              v-if="detailTagInputVisible"
              ref="detailTagInputRef"
              v-model:value="detailTagInput"
              type="text"
              size="small"
              style="width: 90px"
              @press-enter="addDetailTag"
              @blur="addDetailTag"
            />
            <a-button
              v-else
              size="small"
              type="dashed"
              @click="detailTagInputVisible = true; nextTick(() => detailTagInputRef?.focus())"
            >
              <PlusOutlined /> 添加标签
            </a-button>
          </a-space>
        </a-form-item>

        <a-form-item label="内容" name="content">
          <a-textarea
            v-model:value="detailForm.content"
            :rows="8"
            placeholder="详细的角色设定描述，支持多行文本"
          />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, nextTick } from 'vue'
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
} from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { useCRUD } from '@/composables/useCRUD'
import {
  listCharacters,
  createCharacter,
  updateCharacter,
  deleteCharacter,
  listDetails,
  createDetail,
  updateDetail,
  deleteDetail,
} from '@/api/character'

// ==================== L1 Character CRUD (useCRUD) ====================

const columns = [
  { title: '名称', dataIndex: 'name', key: 'name', width: 150 },
  { title: '启用', key: 'enable', width: 70, align: 'center' },
  { title: '设定数', key: 'detailCount', width: 90, align: 'center' },
  { title: '内容', dataIndex: 'content', key: 'content', ellipsis: true },
  { title: '操作', key: 'actions', width: 200, fixed: 'right' },
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
  loadData,
  openCreate,
  openEdit,
  resetForm,
  handleSave,
  handleDelete,
  toggleEnable,
  addField,
  removeField,
} = useCRUD({
  listFn: listCharacters,
  createFn: createCharacter,
  updateFn: updateCharacter,
  deleteFn: deleteCharacter,
  fixedFields: ['name', 'enable', 'content', 'details'],
})

// ==================== L2 Detail Management ====================

const drawerVisible = ref(false)
const targetCharacter = ref(null)
const detailsLoading = ref(false)
const detailItems = ref([])
const detailSearch = ref('')

const filteredDetails = computed(() => {
  const keyword = detailSearch.value.trim().toLowerCase()
  if (!keyword) return detailItems.value
  return detailItems.value.filter(
    (d) =>
      d.name.toLowerCase().includes(keyword) ||
      (d.content || '').toLowerCase().includes(keyword) ||
      (d.tags || []).some((t) => t.toLowerCase().includes(keyword))
  )
})

// Detail form state
const detailModalVisible = ref(false)
const detailSaving = ref(false)
const detailEditing = ref(null)
const detailFormRef = ref(null)
const detailForm = reactive({
  name: '',
  enable: true,
  content: '',
  tags: [],
})
const detailRules = {
  name: [{ required: true, message: '请输入设定名称' }],
}
const detailTagInputVisible = ref(false)
const detailTagInput = ref('')
const detailTagInputRef = ref(null)

function openDetailsDrawer(record) {
  targetCharacter.value = record
  detailSearch.value = ''
  loadDetails(record.name)
  drawerVisible.value = true
}

async function loadDetails(characterName) {
  detailsLoading.value = true
  try {
    detailItems.value = await listDetails(characterName)
  } catch (e) {
    message.error('加载设定详情失败: ' + e.message)
    detailItems.value = []
  } finally {
    detailsLoading.value = false
  }
}

function openDetailCreate() {
  detailEditing.value = null
  detailForm.name = ''
  detailForm.enable = true
  detailForm.content = ''
  detailForm.tags = []
  detailModalVisible.value = true
}

function openDetailEdit(record) {
  detailEditing.value = record.name
  detailForm.name = record.name
  detailForm.enable = !!record.enable
  detailForm.content = record.content || ''
  detailForm.tags = [...(record.tags || [])]
  detailModalVisible.value = true
}

function resetDetailForm() {
  detailEditing.value = null
  detailForm.name = ''
  detailForm.enable = true
  detailForm.content = ''
  detailForm.tags = []
}

async function handleSaveDetail() {
  try {
    await detailFormRef.value.validate()
  } catch {
    return
  }
  detailSaving.value = true
  try {
    const payload = {
      name: detailForm.name,
      enable: detailForm.enable,
      content: detailForm.content,
      tags: detailForm.tags,
    }
    if (detailEditing.value) {
      await updateDetail(targetCharacter.value.name, detailEditing.value, payload)
      message.success('已更新设定')
    } else {
      await createDetail(targetCharacter.value.name, payload)
      message.success('已创建设定')
    }
    detailModalVisible.value = false
    await loadDetails(targetCharacter.value.name)
    // Also refresh L1 list so detailCount updates
    await loadData()
  } catch (e) {
    message.error('操作失败: ' + e.message)
    resetDetailForm()
  } finally {
    detailSaving.value = false
  }
}

async function handleDeleteDetail(record) {
  try {
    await deleteDetail(targetCharacter.value.name, record.name)
    message.success('已删除设定')
    await loadDetails(targetCharacter.value.name)
    await loadData()
  } catch (e) {
    message.error('删除失败: ' + e.message)
  }
}

async function toggleDetailEnable(record, val) {
  const prev = record.enable
  record.enable = val
  try {
    await updateDetail(targetCharacter.value.name, record.name, {
      name: record.name,
      enable: val,
    })
    message.success(val ? '已启用' : '已禁用')
  } catch (e) {
    record.enable = prev
    message.error('操作失败: ' + e.message)
  }
}

function addDetailTag() {
  const t = detailTagInput.value.trim()
  if (t && !detailForm.tags.includes(t)) {
    detailForm.tags.push(t)
  }
  detailTagInput.value = ''
  detailTagInputVisible.value = false
}

onMounted(loadData)
</script>

<style scoped>
.character-mgmt {
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
.no-data {
  color: var(--text-tertiary, #bbb);
}

/* ==================== Detail Drawer ==================== */
.detail-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  gap: 8px;
}

.detail-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.detail-card {
  border: 1px solid var(--border-color, #f0f0f0);
  border-radius: 8px;
  padding: 16px;
  transition: box-shadow 0.2s;
}

.detail-card:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}

.detail-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.detail-title-area {
  display: flex;
  align-items: center;
  gap: 12px;
}

.detail-name {
  font-weight: 600;
  font-size: 15px;
}

.detail-actions {
  display: flex;
  gap: 4px;
}

.detail-tags {
  margin-bottom: 8px;
}

.detail-content {
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.7;
  color: var(--text-color, #333);
  padding: 8px 0;
}
</style>
